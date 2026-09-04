"""SKLab Agent Adapters — one normalized interface for coding agents."""

from sklab_agent_adapters.core.models import (
    ADAPTER_VERSION,
    SCHEMA_VERSION,
    AgentRunRequest,
    AgentRunResult,
    RunStatus,
)

__all__ = [
    "ADAPTER_VERSION",
    "SCHEMA_VERSION",
    "AgentRunRequest",
    "AgentRunResult",
    "RunStatus",
]

__version__ = ADAPTER_VERSION
