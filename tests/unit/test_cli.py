"""CLI tests: startup, JSON validity, dry-run, run, doctor, clean, sessions."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from typer.testing import CliRunner

from sklab_agent_adapters.cli import app

runner = CliRunner()


def _config_with_fake(tmp_path: Path, mode: str = "success_edit",
                      capabilities: dict[str, bool] | None = None) -> str:
    fake = str(Path(__file__).parent.parent / "fake_agents" / "fake_agent.py")
    cfg = {
        "schema_version": 1,
        "agents": {
            "fake": {
                "adapter": "command",
                "command": [sys.executable, fake, "--mode", mode,
                            "--workspace", "{workspace}"],
                "capabilities": capabilities or {
                    "files_write": True, "non_interactive": True, "shell": True},
            }
        },
        "runtime": {"timeout_seconds": 60, "max_log_bytes": 1048576},
    }
    path = tmp_path / "sklab-agents.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return str(path)


def test_version_and_help() -> None:
    res = runner.invoke(app, ["version"])
    assert res.exit_code == 0 and "sklab-agents" in res.stdout
    res = runner.invoke(app, ["--version"])
    assert res.exit_code == 0 and "0.1.0" in res.stdout
    res = runner.invoke(app, ["version", "--json"])
    assert res.exit_code == 0
    assert json.loads(res.stdout)["version"]


def test_list_detect_json_valid() -> None:
    for cmd in (["list", "--json"], ["detect", "--json"], ["doctor", "--json"]):
        res = runner.invoke(app, cmd)
        assert res.exit_code == 0, res.output
        json.loads(res.stdout)  # must be valid JSON


def test_show_capabilities_auth_models(tmp_path: Path) -> None:
    cfg = _config_with_fake(tmp_path)
    for cmd in (["show", "hermes", "--json", "--config", cfg],
                ["capabilities", "codex", "--json", "--config", cfg],
                ["auth", "codex", "--json", "--config", cfg],
                ["models", "claude", "--json", "--config", cfg],
                ["capabilities", "fake", "--json", "--config", cfg]):
        res = runner.invoke(app, cmd)
        assert res.exit_code == 0, (cmd, res.output)
        json.loads(res.stdout)


def test_capabilities_required_flag(tmp_path: Path) -> None:
    cfg = _config_with_fake(tmp_path)
    res = runner.invoke(app, ["capabilities", "codex", "--json", "--config", cfg,
                              "--required", "SHELL,NON_INTERACTIVE"])
    assert res.exit_code == 0
    assert json.loads(res.stdout)["satisfied"] is True


def test_find_command(tmp_path: Path) -> None:
    cfg = _config_with_fake(tmp_path)
    res = runner.invoke(app, ["find", "FILES_WRITE,SHELL,NON_INTERACTIVE",
                              "--json", "--config", cfg])
    assert res.exit_code == 0
    assert "codex" in json.loads(res.stdout)["matches"]


def test_dry_run_redacted_and_no_launch(tmp_path: Path) -> None:
    cfg = _config_with_fake(tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    secret = "dryrun-SECRET-99999999"
    res = runner.invoke(app, ["run", "fake", "--workspace", str(ws),
                              "--instruction", "do things",
                              "--env", f"FAKE_SECRET_TOKEN={secret}",
                              "--dry-run", "--json", "--config", cfg])
    assert res.exit_code == 0, res.output
    payload = json.loads(res.stdout)
    assert payload["dry_run"] is True
    assert secret not in res.stdout
    assert not (ws / "hello.txt").exists(), "dry-run must not launch the agent"


def test_run_success_json(tmp_path: Path) -> None:
    cfg = _config_with_fake(tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    res = runner.invoke(app, ["run", "fake", "--workspace", str(ws),
                              "--instruction", "write file",
                              "--json", "--config", cfg])
    assert res.exit_code == 0, res.output
    payload = json.loads(res.stdout)
    assert payload["status"] == "SUCCESS"
    assert (ws / "hello.txt").exists()


def test_run_failure_exit_code(tmp_path: Path) -> None:
    cfg = _config_with_fake(tmp_path, mode="fail")
    ws = tmp_path / "ws"
    ws.mkdir()
    res = runner.invoke(app, ["run", "fake", "--workspace", str(ws),
                              "--instruction", "x", "--json", "--config", cfg])
    assert res.exit_code == 1
    assert json.loads(res.stdout)["status"] == "AGENT_FAILED"


def test_run_jsonl_valid(tmp_path: Path) -> None:
    cfg = _config_with_fake(tmp_path, mode="stream")
    ws = tmp_path / "ws"
    ws.mkdir()
    res = runner.invoke(app, ["run", "fake", "--workspace", str(ws),
                              "--instruction", "x", "--jsonl", "--config", cfg])
    assert res.exit_code == 0, res.output
    lines = [line for line in res.stdout.splitlines() if line.strip()]
    assert len(lines) >= 3
    for line in lines:
        obj = json.loads(line)  # every line must be valid JSON
        assert "type" in obj
    assert lines[-1].startswith('{"type": "RUN_RESULT"')


def test_run_secret_never_leaks(tmp_path: Path) -> None:
    fake = str(Path(__file__).parent.parent / "fake_agents" / "fake_agent.py")
    cfg = {"schema_version": 1,
           "agents": {"leaky": {"adapter": "command",
                                "command": [sys.executable, fake, "--mode", "leak"],
                                "capabilities": {"non_interactive": True}}}}
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    ws = tmp_path / "ws"
    ws.mkdir()
    secret = "leak-SECRET-4242424242"
    res = runner.invoke(app, ["run", "leaky", "--workspace", str(ws),
                              "--instruction", "x",
                              "--env", f"FAKE_SECRET_TOKEN={secret}",
                              "--json", "--config", str(path)])
    assert secret not in res.stdout
    assert "[REDACTED]" in res.stdout


def test_sessions_unsupported_honest(tmp_path: Path) -> None:
    cfg = _config_with_fake(tmp_path)
    res = runner.invoke(app, ["sessions", "codex", "--json", "--config", cfg])
    assert res.exit_code == 3
    assert json.loads(res.stdout)["error"]["code"] == "CAPABILITY_UNSUPPORTED"


def test_clean_safety(tmp_path: Path) -> None:
    from sklab_agent_adapters.core.models import CONTROL_TASK_FILENAME

    ws = tmp_path / "ws"
    ws.mkdir()
    control = ws / CONTROL_TASK_FILENAME
    control.write_text("task", encoding="utf-8")
    keep = ws / "user.txt"
    keep.write_text("user", encoding="utf-8")
    res = runner.invoke(app, ["clean", "--workspace", str(ws), "--dry-run", "--json"])
    assert res.exit_code == 0
    assert str(control) in json.loads(res.stdout)["candidates"]
    assert control.exists()
    res = runner.invoke(app, ["clean", "--workspace", str(ws), "--yes", "--json"])
    assert res.exit_code == 0
    assert not control.exists() and keep.exists()
