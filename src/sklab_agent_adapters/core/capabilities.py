"""Capability model: explicit, evidence-backed, never guessed."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Capability(StrEnum):
    FILES_READ = "FILES_READ"
    FILES_WRITE = "FILES_WRITE"
    SHELL = "SHELL"
    GIT = "GIT"
    MCP = "MCP"
    SKILLS = "SKILLS"
    SUBAGENTS = "SUBAGENTS"
    SESSION_RESUME = "SESSION_RESUME"
    NON_INTERACTIVE = "NON_INTERACTIVE"
    STREAMING = "STREAMING"
    JSON_OUTPUT = "JSON_OUTPUT"
    MODEL_SELECTION = "MODEL_SELECTION"
    CONTEXT_FILE = "CONTEXT_FILE"
    TASK_FILE = "TASK_FILE"
    PATCH_OUTPUT = "PATCH_OUTPUT"
    TOKEN_USAGE = "TOKEN_USAGE"  # noqa: S105 — enum member name, not a credential
    COST_USAGE = "COST_USAGE"
    WEB_ACCESS = "WEB_ACCESS"
    IMAGE_INPUT = "IMAGE_INPUT"


class CapabilityInfo(BaseModel):
    """One capability entry. ``supported`` is True/False/None(unknown)."""

    model_config = {"populate_by_name": True}

    supported: bool | None = Field(
        default=None, description="True/False, or None when unknown — never a guess."
    )
    evidence: str = Field(
        default="unverified",
        description="How support was determined: cli_help, live_probe, docs, ...",
    )
    notes: str = ""
    minimum_version: str | None = None

    def to_json_dict(self) -> dict[str, object]:
        state = "unknown" if self.supported is None else ("true" if self.supported else "false")
        return {
            "supported": self.supported,
            "state": state,
            "evidence": self.evidence,
            "notes": self.notes,
            "minimum_version": self.minimum_version,
        }


def cap(
    supported: bool | None,
    evidence: str = "cli_help",
    notes: str = "",
    minimum_version: str | None = None,
) -> CapabilityInfo:
    return CapabilityInfo(
        supported=supported, evidence=evidence, notes=notes, minimum_version=minimum_version
    )


def capability_matrix(caps: dict[Capability, CapabilityInfo]) -> dict[str, dict[str, object]]:
    return {c.value: info.to_json_dict() for c, info in caps.items()}
