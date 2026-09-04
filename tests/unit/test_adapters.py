"""Adapter parsing/command tests against captured (and synthetic) fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

from sklab_agent_adapters.adapters.registry import get_adapter
from sklab_agent_adapters.core.capabilities import Capability
from sklab_agent_adapters.core.errors import AdapterError
from sklab_agent_adapters.core.models import AgentRunRequest, AuthState

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _req(**over: object) -> AgentRunRequest:
    base: dict[str, object] = {
        "agent_id": "x", "workspace": Path("."), "instruction": "do it",
    }
    base.update(over)
    return AgentRunRequest(**base)  # type: ignore[arg-type]


def test_hermes_version_known() -> None:
    adapter = get_adapter("hermes")
    parsed = adapter.parse_version(_read("hermes_version.txt"))
    assert parsed.normalized == "0.20.3" and parsed.known


def test_hermes_help_capabilities() -> None:
    caps = get_adapter("hermes").get_capabilities()
    assert caps[Capability.NON_INTERACTIVE].supported is True
    assert caps[Capability.SESSION_RESUME].supported is True
    assert caps[Capability.MODEL_SELECTION].supported is True
    assert caps[Capability.MCP].supported is True
    assert caps[Capability.SKILLS].supported is True


def test_hermes_build_argv(tmp_path: Path) -> None:
    adapter = get_adapter("hermes")
    argv, redacted = adapter.build_argv(
        _req(model="m1", session_id="s1", resume=True), "/exe/hermes", tmp_path)
    assert argv[:2] == ["/exe/hermes", "-z"]
    assert "--in" in argv and "-m" in argv and "--resume" in argv
    assert redacted == argv  # no secrets involved


def test_hermes_requires_instruction(tmp_path: Path) -> None:
    import pytest

    adapter = get_adapter("hermes")
    with pytest.raises(AdapterError):
        adapter.build_argv(_req(instruction="  "), "/exe/hermes", tmp_path)


def test_hermes_usage_file_parsing() -> None:
    from sklab_agent_adapters.adapters.hermes import HermesAdapter

    tokens, cost = HermesAdapter._parse_usage_dict(
        {"input_tokens": 100, "output_tokens": 20, "estimated_cost": 0.002})
    assert tokens is not None and tokens.input_tokens == 100 and tokens.output_tokens == 20
    assert cost is not None and abs(cost.amount - 0.002) < 1e-9


def test_codex_version_known() -> None:
    parsed = get_adapter("codex").parse_version(_read("codex_version.txt"))
    assert parsed.normalized == "0.147.0" and parsed.known


def test_codex_build_argv(tmp_path: Path) -> None:
    argv, _ = get_adapter("codex").build_argv(_req(model="o3"), "/exe/codex", tmp_path)
    assert argv[:3] == ["/exe/codex", "exec", "do it"]
    assert "-C" in argv and "--skip-git-repo-check" in argv and "--model" in argv


def test_codex_build_resume(tmp_path: Path) -> None:
    argv, _ = get_adapter("codex").build_argv(
        _req(resume=True, session_id="abc"), "/exe/codex", tmp_path)
    assert argv[:4] == ["/exe/codex", "exec", "resume", "abc"]


def test_codex_session_and_usage_from_jsonl() -> None:
    adapter = get_adapter("codex")
    stdout = ('{"type":"thread.started","thread_id":"thr-1"}\n'
              '{"usage":{"input_tokens":7,"output_tokens":3}}\n')
    assert adapter.extract_session(stdout, "") == "thr-1"
    tokens, _ = adapter.extract_usage(stdout, "")
    assert tokens is not None and tokens.input_tokens == 7


def test_claude_version_known() -> None:
    parsed = get_adapter("claude").parse_version(_read("claude_version.txt"))
    assert parsed.normalized == "2.1.198" and parsed.known


def test_claude_build_argv_json_default(tmp_path: Path) -> None:
    argv, _ = get_adapter("claude").build_argv(_req(), "/exe/claude", tmp_path)
    assert argv[:3] == ["/exe/claude", "-p", "do it"]
    assert "--output-format" in argv and "json" in argv


def test_claude_build_argv_stream_and_resume(tmp_path: Path) -> None:
    adapter = get_adapter("claude")
    argv, _ = adapter.build_argv(
        _req(stream=True, resume=True, session_id="sid-1"), "/exe/claude", tmp_path)
    assert "stream-json" in argv and "--resume" in argv
    # Caller-provided format must not be duplicated.
    argv2, _ = adapter.build_argv(
        _req(extra_args=["--output-format", "text"]), "/exe/claude", tmp_path)
    assert argv2.count("--output-format") == 1


def test_claude_result_json_parsing() -> None:
    adapter = get_adapter("claude")
    stdout = ('{"type":"result","session_id":"abc-123",'
              '"usage":{"input_tokens":120,"output_tokens":45},'
              '"total_cost_usd":0.0042}')
    assert adapter.extract_session(stdout, "") == "abc-123"
    tokens, cost = adapter.extract_usage(stdout, "")
    assert tokens is not None and tokens.input_tokens == 120
    assert cost is not None and cost.currency == "USD"


def test_claude_malformed_output_safe() -> None:
    adapter = get_adapter("claude")
    assert adapter.extract_session("not json {{{", "") is None
    assert adapter.extract_usage("not json {{{", "") == (None, None)


def test_provisional_adapters_stay_unknown() -> None:
    for agent_id in ("zero", "opencode", "gemini"):
        caps = get_adapter(agent_id).get_capabilities()
        trues = [c for c, i in caps.items()
                 if i.supported is True and c is not Capability.PATCH_OUTPUT]
        assert agent_id == "opencode" and trues == [Capability.NON_INTERACTIVE] or \
            agent_id == "gemini" and trues == [Capability.NON_INTERACTIVE] or \
            (agent_id == "zero" and trues == []), f"{agent_id}: {trues}"


def test_opencode_help_probed_flags() -> None:
    adapter = get_adapter("opencode")
    adapter._help = lambda: _read("opencode_help.synthetic.txt")  # type: ignore[method-assign]
    argv, _ = adapter.build_argv(_req(model="m", session_id="s", resume=True),
                                 "/exe/opencode", Path("."))
    assert argv[:3] == ["/exe/opencode", "run", "do it"]
    assert "--model" in argv and "--session" in argv


def test_gemini_help_probed_flags() -> None:
    adapter = get_adapter("gemini")
    adapter._help = lambda: _read("gemini_help.synthetic.txt")  # type: ignore[method-assign]
    argv, _ = adapter.build_argv(_req(model="m"), "/exe/gemini", Path("."))
    assert argv[1] in ("-p", "--prompt") and "--model" in argv


def test_zero_build_includes_instruction() -> None:
    adapter = get_adapter("zero")
    adapter._help = lambda: _read("zero_help.synthetic.txt")  # type: ignore[method-assign]
    argv, _ = adapter.build_argv(_req(), "/exe/zero", Path("."))
    assert "do it" in argv


def test_auth_states_are_normalized() -> None:
    for agent_id in ("hermes", "codex", "claude", "zero", "opencode", "gemini", "command"):
        state = get_adapter(agent_id).get_auth_status().state
        assert isinstance(state, AuthState), agent_id


def test_models_honest_for_all() -> None:
    for agent_id in ("hermes", "codex", "claude", "zero", "opencode", "gemini", "command"):
        res = get_adapter(agent_id).list_models()
        assert res.state in ("list", "unknown", "unsupported"), agent_id
        if res.state == "list":
            assert res.models, agent_id


def test_explicit_executable_used(tmp_path: Path) -> None:
    adapter = get_adapter("codex", executable=sys.executable)
    det = adapter.detect()
    assert det.executable == sys.executable and det.executable_source == "explicit"
