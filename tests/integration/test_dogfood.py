"""Dogfood: GenericCommandAdapter + fake coding agent on a real git repo.

Proves run success, streaming, patch capture + fingerprint, dirty pre-existing
change preserved, untracked pre-existing file preserved, control file excluded,
and no secret leakage — the same contract real adapters must honor.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from conftest import FAKE_AGENT

from sklab_agent_adapters.adapters.generic import GenericCommandAdapter
from sklab_agent_adapters.core.models import CONTROL_TASK_FILENAME, AgentRunRequest, RunStatus


def _adapter(mode: str, **extra: str) -> GenericCommandAdapter:
    cmd = [sys.executable, str(FAKE_AGENT), "--mode", mode,
           "--workspace", "{workspace}"]
    for key, value in extra.items():
        cmd += [f"--{key.replace('_', '-')}", value]
    return GenericCommandAdapter(
        command=cmd,
        capabilities={"files_read": True, "files_write": True, "shell": True,
                      "non_interactive": True, "streaming": True,
                      "session_resume": True, "patch_output": True},
    )


def test_dogfood_full_cycle(git_repo: Path, tmp_path: Path) -> None:
    # Pre-existing dirty tracked change + untracked user file must survive.
    (git_repo / "tracked.txt").write_text("base\nuser-dirty\n", encoding="utf-8")
    (git_repo / "user-notes.txt").write_text("precious\n", encoding="utf-8")
    (git_repo / CONTROL_TASK_FILENAME).write_text("task body\n", encoding="utf-8")

    events: list[dict[str, object]] = []
    adapter = _adapter("success_edit")
    patch_out = tmp_path / "agent.patch"
    request = AgentRunRequest(
        agent_id="dogfood", workspace=git_repo, instruction="append line",
        timeout_seconds=120, stream=True,
        environment={"FAKE_SECRET_TOKEN": "dogfood-SECRET-77777777"},
        metadata={"patch_out": str(patch_out)},
    )
    result = adapter.run(request, on_event=events.append)

    assert result.status == RunStatus.SUCCESS
    assert result.exit_code == 0
    assert any(e.get("type") == "RUN_STARTED" for e in events)
    assert any(e.get("type") == "RUN_FINISHED" for e in events)
    # Patch + fingerprint.
    assert result.patch_fingerprint
    assert patch_out.is_file()
    body = patch_out.read_text(encoding="utf-8")
    assert result.patch_fingerprint == hashlib.sha256(body.encode()).hexdigest()
    assert "hello.txt" in result.changed_files
    assert "+fake-agent edit" in body
    # Dirty + untracked preserved; control file excluded.
    tracked = (git_repo / "tracked.txt").read_text(encoding="utf-8")
    assert "user-dirty" in tracked
    assert (git_repo / "user-notes.txt").read_text(encoding="utf-8") == "precious\n"
    assert CONTROL_TASK_FILENAME not in result.changed_files
    assert CONTROL_TASK_FILENAME not in body
    assert any("DIRTY_WORKSPACE" in w for w in result.warnings)
    # No secret leakage anywhere in the serialized result.
    serialized = json.dumps(result.model_dump(mode="json"))
    assert "dogfood-SECRET-77777777" not in serialized
    assert "dogfood-SECRET-77777777" not in body


def test_dogfood_streaming_and_jsonl_modes(git_repo: Path) -> None:
    events: list[dict[str, object]] = []
    result = _adapter("stream").run(
        AgentRunRequest(agent_id="dogfood", workspace=git_repo,
                        instruction="stream it", stream=True),
        on_event=events.append)
    assert result.status == RunStatus.SUCCESS
    kinds = [e.get("type") for e in events]
    assert "STDOUT" in kinds and "STDERR" in kinds

    result = _adapter("jsonl").run(
        AgentRunRequest(agent_id="dogfood", workspace=git_repo, instruction="jsonl"))
    assert result.status == RunStatus.SUCCESS


def test_dogfood_session_create_and_resume(git_repo: Path) -> None:
    created = _adapter("session_create").run(
        AgentRunRequest(agent_id="dogfood", workspace=git_repo, instruction="start"))
    assert created.status == RunStatus.SUCCESS

    resumed = _adapter("session_resume", session_id="sess-fake-1").run(
        AgentRunRequest(agent_id="dogfood", workspace=git_repo, instruction="more",
                        session_id="sess-fake-1", resume=True))
    assert resumed.status == RunStatus.SUCCESS
    assert "sess-fake-1" in resumed.stdout


def test_dogfood_usage_and_malformed(git_repo: Path) -> None:
    from sklab_agent_adapters.adapters.claude_code import ClaudeCodeAdapter

    used = _adapter("usage").run(
        AgentRunRequest(agent_id="dogfood", workspace=git_repo, instruction="u"))
    assert used.status == RunStatus.SUCCESS
    # Claude parser maps the same envelope fixture agents emit.
    tokens, cost = ClaudeCodeAdapter().extract_usage(used.stdout, used.stderr)
    assert tokens is not None and tokens.input_tokens == 120
    assert cost is not None and cost.currency == "USD"

    broken = _adapter("malformed").run(
        AgentRunRequest(agent_id="dogfood", workspace=git_repo, instruction="m"))
    assert broken.status == RunStatus.SUCCESS
    assert ClaudeCodeAdapter().extract_session(broken.stdout, broken.stderr) is None


def test_repo_still_clean_of_mutation(git_repo: Path) -> None:
    _adapter("success_edit").run(
        AgentRunRequest(agent_id="dogfood", workspace=git_repo, instruction="x"))
    log = subprocess.run(["git", "log", "--oneline"], cwd=git_repo, capture_output=True,
                         text=True, check=False).stdout
    assert len(log.strip().splitlines()) == 1, "adapter must never commit"
