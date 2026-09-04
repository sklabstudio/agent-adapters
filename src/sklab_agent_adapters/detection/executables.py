"""Executable detection: shutil.which + explicit override, nothing else."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExecutableInfo:
    found: bool
    path: str | None
    source: str  # "explicit" | "path" | "missing"
    warnings: list[str]


def resolve_executable(
    candidates: list[str], *, explicit: str | None = None
) -> ExecutableInfo:
    """Resolve an agent executable.

    Only the configured explicit path or PATH lookup is used. Similarly named
    binaries outside those two sources are never executed.
    """
    warnings: list[str] = []
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return ExecutableInfo(True, str(p), "explicit", warnings)
        return ExecutableInfo(
            False, None, "missing", [f"configured executable not found: {explicit}"]
        )
    for name in candidates:
        found = shutil.which(name)
        if found:
            return ExecutableInfo(True, found, "path", warnings)
    return ExecutableInfo(False, None, "missing", [])
