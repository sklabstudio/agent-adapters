"""Safe subprocess runner: argv arrays, timeout, redaction, truncation, cleanup."""

from __future__ import annotations

import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from sklab_agent_adapters.core.redaction import collect_sensitive_values, redact_text
from sklab_agent_adapters.execution.environment import build_env
from sklab_agent_adapters.execution.process_tree import spawn, terminate_tree
from sklab_agent_adapters.execution.streaming import StreamEventType, make_event


@dataclass
class RunSpec:
    argv: list[str]
    cwd: str
    env_extra: dict[str, str] | None = None
    timeout_seconds: int = 1800
    max_log_bytes: int = 1048576
    redacted_argv: list[str] | None = None


@dataclass
class CompletedRun:
    exit_code: int | None
    stdout: str
    stderr: str
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    timed_out: bool = False
    cancelled: bool = False
    duration_ms: int = 0
    redacted_argv: list[str] = field(default_factory=list)


class Cancellation:
    """Cooperative cancel flag (set from another thread / signal handler)."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def requested(self) -> bool:
        return self._event.is_set()


def _truncate(text: str, limit_bytes: int) -> tuple[str, bool]:
    raw = text.encode("utf-8", errors="replace")
    if len(raw) <= limit_bytes:
        return text, False
    cut = raw[:limit_bytes].decode("utf-8", errors="ignore")
    return cut + f"\n...[truncated {len(raw) - limit_bytes} bytes]...", True


def _redact_argv(argv: list[str], sensitive: list[str]) -> list[str]:
    return [redact_text(a, sensitive) for a in argv]


def execute(
    spec: RunSpec,
    *,
    cancel: Cancellation | None = None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> CompletedRun:
    """Run argv synchronously with timeout + cooperative cancellation.

    Emits RUN_STARTED / STDOUT / STDERR / RUN_FINISHED dictionaries to
    ``on_event`` when provided. Never uses shell=True.
    """
    sensitive = collect_sensitive_values(spec.env_extra)
    redacted_argv = spec.redacted_argv or _redact_argv(spec.argv, sensitive)
    env = build_env(spec.env_extra)
    started = time.monotonic()

    def emit(kind: StreamEventType, data: dict[str, Any]) -> None:
        if on_event is not None:
            on_event(make_event(kind, data))

    emit(StreamEventType.RUN_STARTED, {"argv": redacted_argv, "cwd": spec.cwd})
    try:
        proc = spawn(spec.argv, cwd=spec.cwd, env=env)
    except FileNotFoundError as exc:
        elapsed = int((time.monotonic() - started) * 1000)
        emit(StreamEventType.ERROR, {"message": f"executable not found: {exc}"})
        return CompletedRun(
            exit_code=None,
            stdout="",
            stderr=redact_text(str(exc), sensitive),
            duration_ms=elapsed,
            redacted_argv=redacted_argv,
        )
    except OSError as exc:
        elapsed = int((time.monotonic() - started) * 1000)
        emit(StreamEventType.ERROR, {"message": f"failed to spawn: {exc}"})
        return CompletedRun(
            exit_code=None,
            stdout="",
            stderr=redact_text(str(exc), sensitive),
            duration_ms=elapsed,
            redacted_argv=redacted_argv,
        )

    timed_out = False
    was_cancelled = False
    deadline = started + spec.timeout_seconds
    # Poll so timeout/cancel are honored even for chatty or silent children.
    while True:
        rc = proc.poll()
        if rc is not None:
            break
        if cancel is not None and cancel.requested:
            was_cancelled = True
            terminate_tree(proc)
            break
        if time.monotonic() >= deadline:
            timed_out = True
            terminate_tree(proc)
            break
        time.sleep(0.05)

    try:
        out, err = proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()

    duration_ms = int((time.monotonic() - started) * 1000)
    out = redact_text(out or "", sensitive)
    err = redact_text(err or "", sensitive)
    if timed_out:
        err = (err + "\n" if err else "") + (
            f"process exceeded timeout of {spec.timeout_seconds}s and was terminated"
        )
    if was_cancelled:
        err = (err + "\n" if err else "") + "process was cancelled and terminated"

    out, out_tr = _truncate(out, spec.max_log_bytes)
    err, err_tr = _truncate(err, spec.max_log_bytes)
    if out:
        emit(StreamEventType.STDOUT, {"text": out})
    if err:
        emit(StreamEventType.STDERR, {"text": err})
    emit(
        StreamEventType.RUN_FINISHED,
        {
            "exit_code": proc.returncode,
            "timed_out": timed_out,
            "cancelled": was_cancelled,
            "duration_ms": duration_ms,
        },
    )
    return CompletedRun(
        exit_code=proc.returncode,
        stdout=out,
        stderr=err,
        stdout_truncated=out_tr,
        stderr_truncated=err_tr,
        timed_out=timed_out,
        cancelled=was_cancelled,
        duration_ms=duration_ms,
        redacted_argv=redacted_argv,
    )


def stream_events(
    spec: RunSpec, *, cancel: Cancellation | None = None
) -> Iterator[dict[str, Any]]:
    """Iterator variant of :func:`execute` yielding normalized events."""
    queue: list[dict[str, Any]] = []
    done = threading.Event()

    def _collect(ev: dict[str, Any]) -> None:
        queue.append(ev)

    result: dict[str, CompletedRun] = {}

    def _run() -> None:
        result["run"] = execute(spec, cancel=cancel, on_event=_collect)
        done.set()

    worker = threading.Thread(target=_run, daemon=True)
    worker.start()
    last = 0
    while not done.is_set() or last < len(queue):
        while last < len(queue):
            yield queue[last]
            last += 1
        done.wait(0.05)
    worker.join()
