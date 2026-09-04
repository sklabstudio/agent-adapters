"""Adapter registry: explicit registration, capability search, no plugin exec."""

from __future__ import annotations

from sklab_agent_adapters.adapters.base import AgentAdapter
from sklab_agent_adapters.core.capabilities import Capability

_REGISTRY: dict[str, type[AgentAdapter]] = {}


def register_adapter(cls: type[AgentAdapter]) -> type[AgentAdapter]:
    _REGISTRY[cls.agent_id] = cls
    return cls


def get_adapter(
    agent_id: str, *, executable: str | None = None, max_log_bytes: int = 1048576
) -> AgentAdapter:
    try:
        cls = _REGISTRY[agent_id]
    except KeyError:
        raise KeyError(f"unknown agent {agent_id!r}; known: {sorted(_REGISTRY)}") from None
    return cls(executable=executable, max_log_bytes=max_log_bytes)


def list_adapters() -> list[str]:
    return sorted(_REGISTRY)


def find_by_capabilities(
    required: list[Capability | str], *, executable_overrides: dict[str, str] | None = None
) -> list[AgentAdapter]:
    """Return adapters whose declared capabilities cover every required entry."""
    need = [c if isinstance(c, Capability) else Capability(c) for c in required]
    matches: list[AgentAdapter] = []
    for agent_id in list_adapters():
        adapter = get_adapter(
            agent_id, executable=(executable_overrides or {}).get(agent_id)
        )
        caps = adapter.get_capabilities()
        if all(caps.get(c) is not None and caps[c].supported is True for c in need):
            matches.append(adapter)
    return matches


def _register_builtin() -> None:
    from sklab_agent_adapters.adapters import (  # noqa: F401
        claude_code,
        codex,
        gemini_cli,
        generic,
        hermes,
        opencode,
        zero,
    )


_register_builtin()
