"""Strict YAML config: sklab-agents.yaml (schema_version = 1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

CONFIG_SCHEMA_VERSION = 1


class CommandAgentConfig(BaseModel):
    model_config = {"extra": "forbid"}

    adapter: str = "command"
    command: list[str] = Field(default_factory=list)
    executable: str | None = None
    capabilities: dict[str, bool] = Field(default_factory=dict)

    @field_validator("command")
    @classmethod
    def _nonempty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("command must be a non-empty argv array")
        return v


class NamedAgentConfig(BaseModel):
    model_config = {"extra": "forbid"}

    executable: str | None = None
    adapter: str | None = None
    command: list[str] | None = None
    capabilities: dict[str, bool] = Field(default_factory=dict)


class RuntimeConfig(BaseModel):
    model_config = {"extra": "forbid"}

    timeout_seconds: int = 1800
    max_log_bytes: int = 1048576

    @field_validator("timeout_seconds")
    @classmethod
    def _timeout_bounds(cls, v: int) -> int:
        if v < 1 or v > 86400:
            raise ValueError("timeout_seconds must be between 1 and 86400")
        return v


class SKLabConfig(BaseModel):
    model_config = {"extra": "forbid"}

    schema_version: int = CONFIG_SCHEMA_VERSION
    agents: dict[str, NamedAgentConfig] = Field(default_factory=dict)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)

    @field_validator("schema_version")
    @classmethod
    def _schema(cls, v: int) -> int:
        if v != CONFIG_SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version {v!r}; expected {CONFIG_SCHEMA_VERSION}")
        return v


def find_config_file(explicit: str | None = None) -> Path | None:
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None
    for name in ("sklab-agents.yaml", "sklab-agents.yml"):
        p = Path.cwd() / name
        if p.is_file():
            return p
    return None


def load_config(path: str | Path | None = None) -> SKLabConfig:
    cfg_path = Path(path) if path else find_config_file()
    if cfg_path is None:
        return SKLabConfig()
    data: Any = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config {cfg_path} must be a mapping")
    return SKLabConfig.model_validate(data)


def command_config_to_argv_template(cfg: CommandAgentConfig) -> list[str]:
    return list(cfg.command)
