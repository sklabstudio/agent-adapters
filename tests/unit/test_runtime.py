"""Generic adapter + streaming + runner + patch + safety tests."""

from __future__ import annotations

import hashlib
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from conftest import fake_argv

from sklab_agent_adapters.adapters.generic import GenericCommandAdapter
from sklab_agent_adapters.core.capabilities import Capability
from sklab_agent_adapters.core.errors import AdapterError
from sklab_agent_adapters.core.models import AgentRunRequest, RunStatus
from sklab_agent_adapters.execution.runner import Cancellation, RunSpec, execute
from sklab_agent_adapters.execution.streaming import (
    StreamEventType,
    coerce_agent_event,
    iter_jsonl,
    make_event,
)
from sklab_agent_adapters.workspace.control_files import validate_workspace
from sklab_agent_adapters.workspace.git import baseline
from sklab_agent_adapters.workspace.patch import capture_patch


def _req(workspace: Path, **over: object) -> AgentRunRequest:
    base: dict[str, object] = {"agent_id": "command", "workspace": workspace,
                               "instruction": "hello"}
    base.update(over)
    return AgentRunRequest(**base)  # type: ignore[arg-type]


# -- generic adapter --------------------------------------------------------

def test_placeholder_substitution(tmp_path: Path) -> None:
    adapter = GenericCommandAdapter(
        command=[sys.executable, "agent.py", "{instruction}", "--ws", "{workspace}",
                 "--model", "{model}", "--session", "{session_id}"],
        capabilities={"shell": True},
    )
    rendered = adapter.render(_req(tmp_path, model="m", session_id="s"), tmp_path)
    assert rendered[2] == "hello" and rendered[4] == str(tmp_path)
    assert rendered[6] == "m" and rendered[8] == "s"


def test_unknown_placeholder_rejected(tmp_path: Path) -> None:
    adapter = GenericCommandAdapter(command=["agent", "{evil}; rm -rf"])
    with pytest.raises(AdapterError) as exc:
        adapter.render(_req(tmp_path), tmp_path)
    assert exc.value.code == "INVALID_CONFIGURATION"


def test_empty_command_rejected(tmp_path: Path) -> None:
    with pytest.raises(AdapterError):
        GenericCommandAdapter(command=[]).render(_req(tmp_path), tmp_path)


def test_undeclared_capabilities_are_unknown() -> None:
    caps = GenericCommandAdapter(command=["a"]).get_capabilities()
    assert caps[Capability.SHELL].supported is None
    declared = GenericCommandAdapter(command=["a"],
                                     capabilities={"shell": True}).get_capabilities()
    assert declared[Capability.SHELL].supported is True


def test_generic_run_success(workspace: Path) -> None:
    adapter = GenericCommandAdapter(
        command=[*fake_argv("--mode", "success_edit", "--workspace", "{workspace}"),
                 ],
        capabilities={"files_write": True, "non_interactive": True},
    )
    result = adapter.run(_req(workspace))
    assert result.status == RunStatus.SUCCESS and result.exit_code == 0
    assert (workspace / "hello.txt").read_text(encoding="utf-8") == "fake-agent edit\n"


def test_generic_run_failure_maps_agent_failed(workspace: Path) -> None:
    adapter = GenericCommandAdapter(command=fake_argv("--mode", "fail"))
    result = adapter.run(_req(workspace))
    assert result.status == RunStatus.AGENT_FAILED
    assert result.error and result.error["code"] == "PROCESS_FAILED"


def test_generic_auth_failure_detected(workspace: Path) -> None:
    adapter = GenericCommandAdapter(command=fake_argv("--mode", "auth_required"))
    result = adapter.run(_req(workspace))
    assert result.status == RunStatus.AUTH_REQUIRED


def test_generic_no_changes(workspace: Path) -> None:
    adapter = GenericCommandAdapter(command=fake_argv("--mode", "no_changes"))
    result = adapter.run(_req(workspace))
    assert result.status == RunStatus.SUCCESS


# -- runner -----------------------------------------------------------------

def test_stdout_stderr_capture(workspace: Path) -> None:
    done = execute(RunSpec(argv=fake_argv("--mode", "stream"), cwd=str(workspace)))
    assert done.exit_code == 0
    assert "stdout line 4" in done.stdout and "stderr line 2" in done.stderr
    assert not done.timed_out and not done.cancelled


def test_timeout_kills_owned_process(workspace: Path) -> None:
    start = time.monotonic()
    done = execute(RunSpec(argv=fake_argv("--mode", "timeout"), cwd=str(workspace),
                           timeout_seconds=2))
    assert done.timed_out and time.monotonic() - start < 20


def test_cancel_kills_owned_process(workspace: Path) -> None:
    cancel = Cancellation()
    box: dict[str, object] = {}

    def _target() -> None:
        box["run"] = execute(
            RunSpec(argv=fake_argv("--mode", "timeout"), cwd=str(workspace),
                    timeout_seconds=60), cancel=cancel)

    thread = threading.Thread(target=_target)
    thread.start()
    time.sleep(0.5)
    cancel.cancel()
    thread.join(timeout=30)
    assert not thread.is_alive()
    assert box["run"].cancelled is True


def test_unrelated_process_untouched(workspace: Path) -> None:
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        done = execute(RunSpec(argv=fake_argv("--mode", "timeout"), cwd=str(workspace),
                               timeout_seconds=2))
        assert done.timed_out
        assert other.poll() is None, "unrelated process must survive adapter timeout"
    finally:
        other.terminate()
        other.wait(timeout=15)


def test_env_filtering_no_full_serialization(workspace: Path) -> None:
    done = execute(RunSpec(argv=fake_argv("--mode", "echo_args"), cwd=str(workspace),
                           env_extra={"SKLAB_CUSTOM": "yes"}))
    assert done.exit_code == 0  # filtered env still launches fine


def test_home_vars_inherited_for_native_auth() -> None:
    import os

    from sklab_agent_adapters.execution.environment import build_env

    os.environ["USERPROFILE"] = os.environ.get("USERPROFILE", "C:\\Users\\test")
    env = build_env({})
    assert "USERPROFILE" in env
    assert "PATH" in env
    assert "OPENAI_API_KEY_NOT_A_REAL_VAR_XYZ" not in env


def test_secret_redacted_from_output(workspace: Path) -> None:
    secret = "supersecret-FAKE-1234567890"
    done = execute(RunSpec(argv=fake_argv("--mode", "leak"), cwd=str(workspace),
                           env_extra={"FAKE_SECRET_TOKEN": secret}))
    assert secret not in done.stdout and "[REDACTED]" in done.stdout


def test_log_truncation_bounded(workspace: Path) -> None:
    done = execute(RunSpec(argv=fake_argv("--mode", "stream"), cwd=str(workspace),
                           max_log_bytes=32))
    assert done.stdout_truncated or done.stderr_truncated
    assert len(done.stdout.encode()) < 1024


# -- streaming ---------------------------------------------------------------

def test_jsonl_iterator_skips_garbage() -> None:
    objs = list(iter_jsonl('{"a":1}\nnot json\n{"b":2}\n'))
    assert objs == [{"a": 1}, {"b": 2}]


def test_coerce_never_invents_tool_events() -> None:
    ev = coerce_agent_event({"text": "I used the Edit tool successfully"}, "x")
    assert ev["type"] == StreamEventType.STDOUT.value
    tool = coerce_agent_event({"type": "tool_event", "tool": {"name": "Edit"}}, "x")
    assert tool["type"] == StreamEventType.TOOL_EVENT.value


def test_event_envelope_shape() -> None:
    ev = make_event(StreamEventType.RUN_STARTED, {"argv": ["a"]})
    assert set(ev) == {"type", "at", "data"}


# -- workspace / patch ----------------------------------------------------------

def test_workspace_validation_rejects_missing_and_file(tmp_path: Path) -> None:
    with pytest.raises(AdapterError):
        validate_workspace(tmp_path / "nope")
    f = tmp_path / "f.txt"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(AdapterError):
        validate_workspace(f)


def test_patch_capture_untracked_and_fingerprint(git_repo: Path) -> None:
    (git_repo / "new.txt").write_text("new content\n", encoding="utf-8")
    (git_repo / "tracked.txt").write_text("base\nmore\n", encoding="utf-8")
    patch_file = git_repo.parent / "out.patch"
    cap = capture_patch(git_repo, dirty_before=False, out_path=patch_file)
    assert cap.enabled and cap.fingerprint
    assert "new.txt" in cap.changed_files and "tracked.txt" in cap.changed_files
    body = patch_file.read_text(encoding="utf-8")
    assert body and "+new content" in body
    assert cap.fingerprint == hashlib.sha256(body.encode()).hexdigest()


def test_patch_excludes_control_files(git_repo: Path) -> None:
    from sklab_agent_adapters.core.models import CONTROL_TASK_FILENAME

    (git_repo / CONTROL_TASK_FILENAME).write_text("task\n", encoding="utf-8")
    (git_repo / "real.txt").write_text("real\n", encoding="utf-8")
    cap = capture_patch(git_repo, dirty_before=False)
    assert CONTROL_TASK_FILENAME not in cap.changed_files
    assert "real.txt" in cap.changed_files


def test_dirty_baseline_detected(git_repo: Path) -> None:
    (git_repo / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    base = baseline(git_repo)
    assert base.is_repo and base.dirty and base.head


def test_no_git_mutation_on_capture(git_repo: Path) -> None:
    (git_repo / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    before = subprocess.run(["git", "status", "--porcelain"], cwd=git_repo,
                            capture_output=True, text=True, check=False).stdout
    capture_patch(git_repo, dirty_before=True)
    after = subprocess.run(["git", "status", "--porcelain"], cwd=git_repo,
                           capture_output=True, text=True, check=False).stdout
    assert before == after
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=git_repo,
                          capture_output=True, text=True, check=False).stdout
    assert head.strip()  # HEAD untouched


def test_missing_instruction_and_task_rejected(workspace: Path) -> None:
    adapter = GenericCommandAdapter(command=fake_argv("--mode", "no_changes"))
    with pytest.raises(AdapterError):
        adapter.run(_req(workspace, instruction="   "))
