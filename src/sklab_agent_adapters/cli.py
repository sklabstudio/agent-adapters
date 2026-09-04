"""sklab-agents CLI: list/detect/show/capabilities/auth/models/run/doctor/clean/sessions."""

from __future__ import annotations

import json
import os
import signal
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from sklab_agent_adapters import ADAPTER_VERSION
from sklab_agent_adapters.adapters.base import AgentAdapter
from sklab_agent_adapters.adapters.generic import GenericCommandAdapter
from sklab_agent_adapters.adapters.registry import find_by_capabilities, get_adapter, list_adapters
from sklab_agent_adapters.core.capabilities import Capability, capability_matrix
from sklab_agent_adapters.core.config import NamedAgentConfig, SKLabConfig, load_config
from sklab_agent_adapters.core.errors import AdapterError
from sklab_agent_adapters.core.models import AgentRunRequest
from sklab_agent_adapters.core.output import err_console, print_json, print_jsonl
from sklab_agent_adapters.core.redaction import redact_text
from sklab_agent_adapters.execution.runner import Cancellation

app = typer.Typer(
    name="sklab-agents",
    help="One normalized interface for running, inspecting, and controlling coding agents.",
    no_args_is_help=True,
)
out_console = Console()


def _version_callback(value: bool) -> None:
    if value:
        out_console.print(f"sklab-agents {ADAPTER_VERSION}")
        raise typer.Exit()


@app.callback()
def _main(
    version: Annotated[
        bool | None,
        typer.Option("--version", "-V", callback=_version_callback, is_eager=True,
                     help="Print the package version and exit."),
    ] = None,
) -> None:
    """One normalized interface for coding agents."""


# -- config / adapter resolution --------------------------------------

def _load_config(config: str | None) -> SKLabConfig:
    try:
        return load_config(config)
    except Exception as exc:
        err_console.print(f"[red]invalid configuration:[/red] {exc}")
        raise typer.Exit(code=2) from exc


def _configured_executable(cfg: SKLabConfig, agent_id: str) -> str | None:
    entry = cfg.agents.get(agent_id)
    return entry.executable if entry else None


def _resolve_adapter(
    agent_id: str, cfg: SKLabConfig, *, max_log_bytes: int | None = None
) -> AgentAdapter:
    limit = max_log_bytes or cfg.runtime.max_log_bytes
    entry: NamedAgentConfig | None = cfg.agents.get(agent_id)
    if entry is not None and (entry.adapter == "command" or entry.command):
        if not entry.command:
            raise AdapterError("INVALID_CONFIGURATION",
                               f"agent {agent_id!r}: adapter 'command' needs `command:` argv")
        adapter = GenericCommandAdapter(
            command=list(entry.command),
            capabilities=dict(entry.capabilities or {}),
            max_log_bytes=limit,
        )
        adapter.agent_id = agent_id
        return adapter
    if entry is not None and entry.adapter and entry.adapter != agent_id:
        raise AdapterError(
            "INVALID_CONFIGURATION",
            f"agent {agent_id!r}: unknown adapter {entry.adapter!r} (only 'command' is pluggable)",
        )
    return get_adapter(agent_id, executable=_configured_executable(cfg, agent_id),
                       max_log_bytes=limit)


def _all_agent_ids(cfg: SKLabConfig) -> list[str]:
    ids = list_adapters()
    for name in cfg.agents:
        if name not in ids:
            ids.append(name)
    return sorted(ids)


def _parse_env(items: list[str]) -> dict[str, str]:
    env: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise AdapterError("INVALID_CONFIGURATION", f"--env must be KEY=VALUE, got {item!r}")
        key, value = item.split("=", 1)
        if not key.strip():
            raise AdapterError("INVALID_CONFIGURATION", f"--env has empty key: {item!r}")
        env[key] = value
    return env


# -- version ------------------------------------------------------------

@app.command()
def version(
    json_: Annotated[bool, typer.Option("--json", help="Machine-readable output.")] = False,
) -> None:
    """Print the package version."""
    if json_:
        print_json({"version": ADAPTER_VERSION})
    else:
        out_console.print(f"sklab-agents {ADAPTER_VERSION}")


# -- list ---------------------------------------------------------------

@app.command(name="list")
def list_cmd(
    config: Annotated[str | None, typer.Option("--config")] = None,
    json_: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List known adapters with install/version status."""
    cfg = _load_config(config)
    rows: list[dict[str, Any]] = []
    for agent_id in _all_agent_ids(cfg):
        try:
            adapter = _resolve_adapter(agent_id, cfg)
            det = adapter.detect()
            rows.append({
                "agent_id": agent_id,
                "display_name": adapter.display_name,
                "installed": det.installed,
                "version": det.version,
                "compatibility": det.compatibility.value,
            })
        except (KeyError, AdapterError) as exc:
            rows.append({"agent_id": agent_id, "error": str(exc)})
    if json_:
        print_json({"adapters": rows})
        return
    table = Table(title="SKLab agent adapters")
    table.add_column("agent")
    table.add_column("display name")
    table.add_column("installed")
    table.add_column("version")
    table.add_column("compatibility")
    for r in rows:
        table.add_row(
            r.get("agent_id", "?"), r.get("display_name", "-"),
            str(r.get("installed", "?")), str(r.get("version")),
            str(r.get("compatibility", r.get("error", "?"))),
        )
    out_console.print(table)


# -- detect ---------------------------------------------------------------

@app.command()
def detect(
    config: Annotated[str | None, typer.Option("--config")] = None,
    json_: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Detect installed agent executables, versions, and compatibility."""
    cfg = _load_config(config)
    results: list[dict[str, Any]] = []
    for agent_id in _all_agent_ids(cfg):
        try:
            det = _resolve_adapter(agent_id, cfg).detect()
            results.append({
                "agent_id": det.agent_id,
                "installed": det.installed,
                "executable": det.executable,
                "executable_source": det.executable_source,
                "version": det.version,
                "compatibility": det.compatibility.value,
                "warnings": det.warnings,
            })
        except (KeyError, AdapterError) as exc:
            results.append({"agent_id": agent_id, "error": str(exc)})
    if json_:
        print_json({"detections": results})
        return
    table = Table(title="Agent detection")
    table.add_column("agent")
    table.add_column("installed")
    table.add_column("executable")
    table.add_column("version")
    table.add_column("compatibility")
    for r in results:
        table.add_row(
            r.get("agent_id", "?"), str(r.get("installed", "?")),
            str(r.get("executable")), str(r.get("version")),
            str(r.get("compatibility", r.get("error", "?"))),
        )
    out_console.print(table)
    for r in results:
        for w in r.get("warnings", []):
            err_console.print(f"[yellow]warning:[/yellow] {r['agent_id']}: {w}")


# -- show -------------------------------------------------------------------

@app.command()
def show(
    agent: Annotated[str, typer.Argument(help="Adapter id, e.g. hermes.")],
    config: Annotated[str | None, typer.Option("--config")] = None,
    json_: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show adapter metadata + zero-cost healthcheck."""
    cfg = _load_config(config)
    try:
        adapter = _resolve_adapter(agent, cfg)
    except KeyError:
        err_console.print(f"[red]unknown agent:[/red] {agent}")
        raise typer.Exit(code=2) from None
    data = {"metadata": adapter.metadata(), "health": adapter.healthcheck()}
    if json_:
        print_json(data)
    else:
        out_console.print_json(json.dumps(data, indent=2, default=str))


# -- capabilities -------------------------------------------------------------

@app.command()
def capabilities(
    agent: Annotated[str, typer.Argument()],
    config: Annotated[str | None, typer.Option("--config")] = None,
    json_: Annotated[bool, typer.Option("--json")] = False,
    required: Annotated[str | None, typer.Option(
        "--required", help="Comma-separated capabilities, e.g. SHELL,FILES_WRITE.")] = None,
) -> None:
    """Show an agent's explicit capability matrix."""
    cfg = _load_config(config)
    try:
        adapter = _resolve_adapter(agent, cfg)
    except KeyError:
        err_console.print(f"[red]unknown agent:[/red] {agent}")
        raise typer.Exit(code=2) from None
    matrix = capability_matrix(adapter.get_capabilities())
    payload: dict[str, Any] = {"agent_id": agent, "capabilities": matrix}
    if required:
        need = [c.strip() for c in required.split(",") if c.strip()]
        try:
            declared = adapter.get_capabilities()
            ok = all(
                declared.get(Capability(c), None) is not None
                and declared[Capability(c)].supported is True
                for c in need
            )
        except ValueError as exc:
            err_console.print(f"[red]unknown capability:[/red] {exc}")
            raise typer.Exit(code=2) from None
        payload["required"] = need
        payload["satisfied"] = ok
    if json_:
        print_json(payload)
    else:
        out_console.print_json(json.dumps(payload, indent=2, default=str))


# -- auth -----------------------------------------------------------------------

@app.command()
def auth(
    agent: Annotated[str, typer.Argument()],
    config: Annotated[str | None, typer.Option("--config")] = None,
    json_: Annotated[bool, typer.Option("--json")] = False,
    login: Annotated[bool, typer.Option(
        "--login", help="Invoke the agent's official login flow (verified flows only).")] = False,
) -> None:
    """Inspect native auth status (read-only by default)."""
    cfg = _load_config(config)
    try:
        adapter = _resolve_adapter(agent, cfg)
    except KeyError:
        err_console.print(f"[red]unknown agent:[/red] {agent}")
        raise typer.Exit(code=2) from None
    try:
        result = adapter.login() if login else adapter.get_auth_status()
    except AdapterError as exc:
        if json_:
            print_json({"agent_id": agent, "error": exc.to_dict()})
        else:
            err_console.print(f"[red]{exc.code}:[/red] {exc.message}")
        raise typer.Exit(code=3) from None
    payload = {"agent_id": agent, "state": result.state.value,
               "detail": result.detail, "login_hint": result.login_hint}
    if json_:
        print_json(payload)
    else:
        out_console.print_json(json.dumps(payload, indent=2, default=str))


# -- models -----------------------------------------------------------------------

@app.command()
def models(
    agent: Annotated[str, typer.Argument()],
    config: Annotated[str | None, typer.Option("--config")] = None,
    json_: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List models where the agent exposes a machine-readable list (honest otherwise)."""
    cfg = _load_config(config)
    try:
        adapter = _resolve_adapter(agent, cfg)
    except KeyError:
        err_console.print(f"[red]unknown agent:[/red] {agent}")
        raise typer.Exit(code=2) from None
    res = adapter.list_models()
    payload = {"agent_id": agent, "state": res.state, "models": res.models, "detail": res.detail}
    if json_:
        print_json(payload)
    else:
        out_console.print_json(json.dumps(payload, indent=2, default=str))


# -- sessions -----------------------------------------------------------------------

@app.command()
def sessions(
    agent: Annotated[str, typer.Argument()],
    config: Annotated[str | None, typer.Option("--config")] = None,
    json_: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List native sessions where the adapter supports it."""
    cfg = _load_config(config)
    try:
        adapter = _resolve_adapter(agent, cfg)
    except KeyError:
        err_console.print(f"[red]unknown agent:[/red] {agent}")
        raise typer.Exit(code=2) from None
    try:
        items = adapter.list_sessions()
    except AdapterError as exc:
        if json_:
            print_json({"agent_id": agent, "error": exc.to_dict()})
        else:
            err_console.print(f"[red]{exc.code}:[/red] {exc.message}")
        raise typer.Exit(code=3) from None
    payload = {"agent_id": agent, "sessions": [s.model_dump() for s in items]}
    if json_:
        print_json(payload)
    else:
        out_console.print_json(json.dumps(payload, indent=2, default=str))


# -- run -------------------------------------------------------------------------------

@app.command()
def run(
    agent: Annotated[str, typer.Argument()],
    workspace: Annotated[str, typer.Option("--workspace", "-w",
                                           help="Workspace dir the agent may operate in.")] = ".",
    instruction: Annotated[str, typer.Option("--instruction", "-i")] = "",
    task_file: Annotated[str | None, typer.Option("--task-file")] = None,
    context_file: Annotated[str | None, typer.Option("--context-file")] = None,
    model: Annotated[str | None, typer.Option("--model", "-m")] = None,
    timeout: Annotated[int | None, typer.Option("--timeout",
                                                  help="Timeout seconds (config default).")] = None,
    env: Annotated[list[str], typer.Option("--env",
                                           help="Extra env KEY=VALUE (repeatable).")] = [],  # noqa: B006
    session_id: Annotated[str | None, typer.Option("--session-id")] = None,
    resume: Annotated[bool, typer.Option("--resume")] = False,
    extra: Annotated[list[str], typer.Option("--extra",
                                             help="Extra native args (repeatable).")] = [],  # noqa: B006
    stream: Annotated[bool, typer.Option("--stream")] = False,
    jsonl: Annotated[bool, typer.Option("--jsonl",
                                        help="Stream normalized JSONL events to stdout.")] = False,
    json_: Annotated[bool, typer.Option("--json",
                                        help="Print normalized result as JSON.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run",
                                          help="Resolve argv; do not launch.")] = False,
    patch_out: Annotated[str | None, typer.Option("--patch-out",
                                                     help="Write git patch to PATH.")] = None,
    config: Annotated[str | None, typer.Option("--config")] = None,
) -> None:
    """Run an agent non-interactively in a workspace (workspace-confined)."""
    cfg = _load_config(config)
    try:
        adapter = _resolve_adapter(agent, cfg)
    except KeyError:
        err_console.print(f"[red]unknown agent:[/red] {agent}")
        raise typer.Exit(code=2) from None
    try:
        env_map = _parse_env(list(env))
        request = AgentRunRequest(
            agent_id=agent,
            workspace=Path(workspace),
            instruction=instruction,
            task_file=Path(task_file) if task_file else None,
            context_file=Path(context_file) if context_file else None,
            model=model,
            timeout_seconds=timeout or cfg.runtime.timeout_seconds,
            environment=env_map,
            session_id=session_id,
            resume=resume,
            extra_args=list(extra),
            stream=stream or jsonl,
            metadata={"patch_out": patch_out} if patch_out else {},
        )
    except Exception as exc:
        err_console.print(f"[red]invalid request:[/red] {exc}")
        raise typer.Exit(code=2) from None

    if dry_run:
        try:
            plan = adapter.prepare_run(request)
        except AdapterError as exc:
            if json_ or jsonl:
                print_json({"agent_id": agent, "error": exc.to_dict()})
            else:
                err_console.print(f"[red]{exc.code}:[/red] {exc.message}")
            raise typer.Exit(code=3) from None
        if json_ or jsonl:
            print_json({"dry_run": True, **plan})
        else:
            out_console.print_json(json.dumps({"dry_run": True, **plan}, indent=2, default=str))
        return

    cancel = Cancellation()
    events: list[dict[str, Any]] = []

    def _on_event(ev: dict[str, Any]) -> None:
        events.append(ev)
        if jsonl:
            print_jsonl(ev)
        elif stream:
            kind = ev.get("type")
            data = ev.get("data", {})
            if kind in ("STDOUT", "STDERR") and isinstance(data, dict) and "text" in data:
                err_console.print(f"[dim]{kind.lower()}:[/dim] {str(data['text'])[:500]}")
            else:
                err_console.print(f"[dim]event:[/dim] {kind}")

    # Ctrl-C => cooperative cancel: owned process tree is terminated, result CANCELLED.
    prev_handler = signal.getsignal(signal.SIGINT)

    def _handle_sigint(signum: int, frame: object) -> None:
        cancel.cancel()

    signal.signal(signal.SIGINT, _handle_sigint)
    try:
        try:
            if resume and not session_id:
                err_console.print("[red]SESSION_NOT_FOUND:[/red] --resume requires --session-id")
                raise typer.Exit(code=2)
            result = adapter.resume(request, cancel=cancel, on_event=_on_event) \
                if resume else adapter.run(request, cancel=cancel, on_event=_on_event)
        except AdapterError as exc:
            if json_ or jsonl:
                if not jsonl:
                    print_json({"agent_id": agent, "error": exc.to_dict()})
                else:
                    print_jsonl({"type": "ERROR", "error": exc.to_dict()})
            else:
                err_console.print(f"[red]{exc.code}:[/red] {exc.message}")
            raise typer.Exit(code=3) from None
    finally:
        signal.signal(signal.SIGINT, prev_handler)

    payload = result.model_dump(mode="json")
    # Belt-and-braces: redact any leaked secret values from the serialized result.
    payload = json.loads(redact_text(json.dumps(payload), None))
    if jsonl:
        print_jsonl({"type": "RUN_RESULT", "result": payload})
    elif json_:
        print_json(payload)
    else:
        out_console.print(f"[bold]status:[/bold] {result.status.value} "
                          f"[dim](exit={result.exit_code} {result.duration_ms}ms)[/dim]")
        if result.session_id:
            out_console.print(f"[bold]session:[/bold] {result.session_id}")
        if result.patch_fingerprint:
            out_console.print(f"[bold]patch:[/bold] {result.patch_fingerprint[:16]}… "
                              f"{len(result.changed_files)} file(s)")
        if result.error:
            err_console.print(
                f"[red]{result.error.get('code')}:[/red] {result.error.get('message')}")
    raise typer.Exit(code=0 if result.status.value == "SUCCESS" else 1)


# -- capabilities search -----------------------------------------------------------

@app.command()
def find(
    required: Annotated[str, typer.Argument(
        help="Comma-separated capabilities, e.g. FILES_WRITE,SHELL,NON_INTERACTIVE.")],
    config: Annotated[str | None, typer.Option("--config")] = None,
    json_: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Find adapters satisfying all required capabilities (for orchestrators)."""
    cfg = _load_config(config)
    need = [c.strip() for c in required.split(",") if c.strip()]
    try:
        overrides = {a: e for a in _all_agent_ids(cfg)
                     if (e := _configured_executable(cfg, a))}
        matches = find_by_capabilities(need, executable_overrides=overrides)
    except ValueError as exc:
        err_console.print(f"[red]unknown capability:[/red] {exc}")
        raise typer.Exit(code=2) from None
    payload = {"required": need, "matches": [m.agent_id for m in matches]}
    if json_:
        print_json(payload)
    else:
        out_console.print_json(json.dumps(payload, indent=2))


# -- doctor ----------------------------------------------------------------------------

@app.command()
def doctor(
    config: Annotated[str | None, typer.Option("--config")] = None,
    json_: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Zero-cost environment health: PATH, CLIs, versions, auth, permissions, git."""
    import shutil

    cfg = _load_config(config)
    git_path = shutil.which("git")
    report: dict[str, Any] = {
        "path_entries": len(os.environ.get("PATH", "").split(os.pathsep)),
        "git": {"available": git_path is not None, "path": git_path},
        "python": {"version": sys.version.split()[0]},
        "agents": [],
    }
    for agent_id in _all_agent_ids(cfg):
        try:
            adapter = _resolve_adapter(agent_id, cfg)
            health = adapter.healthcheck()
            det = adapter.detect()
            health["executable_readable"] = bool(
                det.executable and os.access(det.executable, os.R_OK))
            health["executable_executable"] = bool(
                det.executable and os.access(det.executable, os.X_OK))
            report["agents"].append(health)
        except (KeyError, AdapterError) as exc:
            report["agents"].append({"agent_id": agent_id, "error": str(exc)})
    if json_:
        print_json(report)
    else:
        out_console.print_json(json.dumps(report, indent=2, default=str))


# -- clean -------------------------------------------------------------------------------

@app.command()
def clean(
    workspace: Annotated[str, typer.Option("--workspace", "-w",
                                           help="Workspace to clean artifacts from.")] = ".",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip confirmation.")] = False,
    json_: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Remove ONLY adapter-owned artifacts (control files, temp run metadata)."""
    import glob as _glob
    import tempfile

    from sklab_agent_adapters.core.models import CONTROL_FILENAMES

    ws = Path(workspace).expanduser()
    candidates: list[str] = []
    if ws.is_dir():
        for name in CONTROL_FILENAMES:
            p = ws / name
            if p.is_file():
                candidates.append(str(p))
    tmp = Path(tempfile.gettempdir())
    for pattern in ("sklab-hermes-usage-*.json", "sklab-agents-*.json"):
        candidates.extend(_glob.glob(str(tmp / pattern)))
    payload = {"workspace": str(ws), "dry_run": dry_run,
               "removed": [], "candidates": candidates}
    if dry_run:
        if json_:
            print_json(payload)
        else:
            out_console.print_json(json.dumps(payload, indent=2))
        return
    if candidates and not yes:
        out_console.print("Adapter-owned artifacts that would be removed:")
        for c in candidates:
            out_console.print(f"  - {c}")
        if not typer.confirm("Remove these files?"):
            raise typer.Exit(code=1)
    removed: list[str] = []
    for c in candidates:
        try:
            Path(c).unlink()
            removed.append(c)
        except OSError as exc:
            err_console.print(f"[yellow]warning:[/yellow] could not remove {c}: {exc}")
    payload["removed"] = removed
    if json_:
        print_json(payload)
    else:
        out_console.print_json(json.dumps(payload, indent=2))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
