"""Process-tree cleanup: terminate only owned processes, never by name."""

from __future__ import annotations

import os
import subprocess
import sys


def _windows_argv(argv: list[str]) -> list[str]:
    """Route .cmd/.bat shims through cmd.exe (CreateProcess cannot run them).

    Only applies to the exact resolved executable path — never a shell string.
    """
    if argv and argv[0].lower().endswith((".cmd", ".bat")):
        return ["cmd.exe", "/d", "/c", argv[0], *argv[1:]]
    return argv


def spawn(argv: list[str], *, cwd: str, env: dict[str, str]) -> subprocess.Popen[str]:
    """Spawn a child in its own process group so timeout/cancel kills the tree.

    Never uses shell=True. The caller owns exactly this process group.
    """
    if sys.platform == "win32":
        argv = _windows_argv(argv)
        new_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        return subprocess.Popen(  # noqa: S603 — fixed argv array, never shell
            argv,
            cwd=cwd,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=new_group,
        )
    return subprocess.Popen(  # noqa: S603 — fixed argv array, never shell
        argv,
        cwd=cwd,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )


def terminate_tree(proc: subprocess.Popen[str], *, grace_seconds: float = 5.0) -> None:
    """Terminate an owned process (and its group children where practical).

    Only ever targets the specific PID / process group started by :func:`spawn`.
    """
    if proc.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            # Terminate the process itself first.
            proc.terminate()
            try:
                proc.wait(timeout=grace_seconds)
                return
            except subprocess.TimeoutExpired:
                pass
            # Fall back to tree-kill scoped to this exact PID (owned process only).
            subprocess.run(  # noqa: S603 — fixed argv, no shell, owned PID only
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],  # noqa: S607
                capture_output=True,
                timeout=15,
                check=False,
            )
        else:
            try:
                os.killpg(os.getpgid(proc.pid), 15)  # SIGTERM to owned group
            except (ProcessLookupError, PermissionError, OSError):
                proc.terminate()
            try:
                proc.wait(timeout=grace_seconds)
                return
            except subprocess.TimeoutExpired:
                pass
            try:
                os.killpg(os.getpgid(proc.pid), 9)  # SIGKILL to owned group
            except (ProcessLookupError, PermissionError, OSError):
                proc.kill()
    except Exception:  # noqa: S110 — best-effort final kill; result already recorded
        try:
            proc.kill()
        except Exception:  # noqa: S110 — nothing left to do; OS reaps the child
            pass
