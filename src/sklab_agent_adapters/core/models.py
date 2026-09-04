"""Normalized run request / run result models (schema_version = 1)."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

ADAPTER_VERSION = "0.1.0"
SCHEMA_VERSION = 1

CONTROL_TASK_FILENAME = ".sklab-agent-task.md"
CONTROL_CONTEXT_FILENAME = ".sklab-agent-context.md"
CONTROL_FILENAMES = frozenset({CONTROL_TASK_FILENAME, CONTROL_CONTEXT_FILENAME})


class RunStatus(StrEnum):
    SUCCESS = "SUCCESS"
    AGENT_FAILED = "AGENT_FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    UNAVAILABLE = "UNAVAILABLE"
    UNSUPPORTED = "UNSUPPORTED"
    NO_CHANGES = "NO_CHANGES"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AuthState(StrEnum):
    READY = "READY"
    NOT_AUTHENTICATED = "NOT_AUTHENTICATED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    EXPIRED_OR_INVALID = "EXPIRED_OR_INVALID"
    AUTH_UNKNOWN = "AUTH_UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"


class Compatibility(StrEnum):
    SUPPORTED = "SUPPORTED"
    SUPPORTED_WITH_WARNINGS = "SUPPORTED_WITH_WARNINGS"
    UNKNOWN_VERSION = "UNKNOWN_VERSION"
    TOO_OLD = "TOO_OLD"
    UNAVAILABLE = "UNAVAILABLE"


class TokenUsage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None
    source: str | None = None


class CostUsage(BaseModel):
    amount: float | None = None
    currency: str | None = None
    source: str | None = None


class AgentRunRequest(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    agent_id: str
    workspace: Path
    instruction: str = ""
    task_file: Path | None = None
    context_file: Path | None = None
    model: str | None = None
    timeout_seconds: int = 1800
    environment: dict[str, str] = Field(default_factory=dict)
    session_id: str | None = None
    resume: bool = False
    extra_args: list[str] = Field(default_factory=list)
    stream: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)
    dry_run: bool = False

    @field_validator("timeout_seconds")
    @classmethod
    def _timeout_bounds(cls, v: int) -> int:
        if v < 1 or v > 86400:
            raise ValueError("timeout_seconds must be between 1 and 86400")
        return v

    @field_validator("instruction")
    @classmethod
    def _instruction_or_files(cls, v: str, info: object) -> str:
        # Pydantic v2: cross-field check happens in adapter validation; keep simple here.
        return v


class AgentRunResult(BaseModel):
    schema_version: int = SCHEMA_VERSION
    agent_id: str
    adapter_version: str = ADAPTER_VERSION
    agent_version: str | None = None
    status: RunStatus
    started_at: str = ""
    finished_at: str = ""
    duration_ms: int = 0
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    workspace: str = ""
    session_id: str | None = None
    resumable: bool = False
    patch_path: str | None = None
    patch_fingerprint: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    token_usage: TokenUsage | None = None
    cost_usage: CostUsage | None = None
    model: str | None = None
    warnings: list[str] = Field(default_factory=list)
    error: dict[str, str] | None = None


class SessionInfo(BaseModel):
    session_id: str
    created_at: str = ""
    resumable: bool = False
    agent_id: str = ""
    metadata: dict[str, str] = Field(default_factory=dict)


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()
