"""Core unit tests: registry, capabilities, versions, detection, config, redaction."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

from sklab_agent_adapters.adapters.registry import (
    find_by_capabilities,
    get_adapter,
    list_adapters,
)
from sklab_agent_adapters.core.capabilities import Capability
from sklab_agent_adapters.core.config import SKLabConfig, load_config
from sklab_agent_adapters.core.redaction import (
    collect_sensitive_values,
    env_var_names_only,
    redact_text,
)
from sklab_agent_adapters.detection.compatibility import classify
from sklab_agent_adapters.detection.executables import resolve_executable
from sklab_agent_adapters.detection.versions import extract_version, parse_version_output

FIXTURES = Path(__file__).parent / "fixtures"


def test_registry_lists_all_seven() -> None:
    ids = list_adapters()
    assert ids == ["claude", "codex", "command", "gemini", "hermes", "opencode", "zero"]


def test_registry_unknown_raises() -> None:
    with pytest.raises(KeyError):
        get_adapter("nope")


def test_every_adapter_declares_full_capability_set() -> None:
    for agent_id in list_adapters():
        caps = get_adapter(agent_id).get_capabilities()
        missing = [c for c in Capability if c not in caps]
        assert not missing, f"{agent_id} missing {missing}"


def test_no_adapter_fakes_support_without_evidence() -> None:
    for agent_id in list_adapters():
        for cap_name, info in get_adapter(agent_id).get_capabilities().items():
            if info.supported is True:
                assert info.evidence not in ("", "unverified"), f"{agent_id}.{cap_name}"


def test_find_by_capabilities_shell_noninteractive() -> None:
    matches = find_by_capabilities([Capability.FILES_WRITE, Capability.SHELL,
                                    Capability.NON_INTERACTIVE])
    ids = [m.agent_id for m in matches]
    assert "hermes" in ids and "codex" in ids and "claude" in ids
    # Provisional adapters must NOT match real capability queries.
    assert "zero" not in ids and "opencode" not in ids and "gemini" not in ids


def test_version_extract_known() -> None:
    assert extract_version("codex-cli 0.147.0") == "0.147.0"
    assert extract_version("2.1.198 (Claude Code)") == "2.1.198"
    assert extract_version("Hermes Agent v0.20.3 (2026.8.16.2)") == "0.20.3"


def test_version_malformed() -> None:
    parsed = parse_version_output("no version here", known_versions=("1.0.0",))
    assert parsed.normalized is None and not parsed.known
    assert classify(parsed, installed=True).value == "UNKNOWN_VERSION"


def test_version_unknown_newer() -> None:
    parsed = parse_version_output("codex-cli 9.99.0", known_versions=("0.147.0",))
    assert parsed.normalized == "9.99.0" and not parsed.known and parsed.newer_than_known
    assert classify(parsed, installed=True).value == "SUPPORTED_WITH_WARNINGS"


def test_version_supported_and_too_old() -> None:
    parsed = parse_version_output("codex-cli 0.147.0", known_versions=("0.147.0",))
    assert classify(parsed, installed=True).value == "SUPPORTED"
    old = parse_version_output("tool 0.1.0", known_versions=("0.147.0",))
    assert classify(old, installed=True, minimum_version="0.2.0").value == "TOO_OLD"
    assert classify(old, installed=False).value == "UNAVAILABLE"


def test_executable_explicit_override_missing() -> None:
    info = resolve_executable(["codex"], explicit="/nonexistent/bin/agent")
    assert not info.found and info.source == "missing" and info.warnings


def test_executable_path_lookup() -> None:
    info = resolve_executable([Path(sys.executable).name], explicit=sys.executable)
    assert info.found and info.source == "explicit"


def test_config_strict_rejects_unknown_fields(tmp_path: Path) -> None:
    cfg_file = tmp_path / "sklab-agents.yaml"
    cfg_file.write_text(yaml.safe_dump({
        "schema_version": 1,
        "agents": {"custom": {"adapter": "command",
                              "command": ["my-agent", "{instruction}"],
                              "bogus_field": True}},
    }), encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(cfg_file)


def test_config_rejects_bad_schema(tmp_path: Path) -> None:
    cfg_file = tmp_path / "sklab-agents.yaml"
    cfg_file.write_text(yaml.safe_dump({"schema_version": 99}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(cfg_file)


def test_config_defaults_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = load_config(None)
    assert isinstance(cfg, SKLabConfig) and cfg.runtime.timeout_seconds == 1800


def test_redaction_replaces_known_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-abcdefgh12345678")
    sensitive = collect_sensitive_values({"EXTRA": "short"})
    assert "sk-test-abcdefgh12345678" in sensitive
    out = redact_text("key=sk-test-abcdefgh12345678 done", sensitive)
    assert "sk-test-abcdefgh12345678" not in out and "[REDACTED]" in out


def test_redaction_patterns_without_list() -> None:
    out = redact_text("token ghp_abcdefgh1234567890 end", [])
    assert "ghp_abcdefgh1234567890" not in out


def test_env_names_only_never_values() -> None:
    names = env_var_names_only({"A": "secret-value", "B": "x"})
    assert names == ["A", "B"]
