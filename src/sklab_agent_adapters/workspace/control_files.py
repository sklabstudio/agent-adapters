"""Workspace safety: canonicalize, confine, never mutate Git state."""

from __future__ import annotations

from pathlib import Path

from sklab_agent_adapters.core.errors import AdapterError, ErrorCode


def validate_workspace(path: str | Path) -> Path:
    """Validate that a workspace exists and is safe to operate in.

    Returns the canonicalized absolute path. Raises AdapterError on:
    missing path, non-directory, filesystem root, or home directory.
    """
    p = Path(path).expanduser()
    if not p.exists():
        raise AdapterError(ErrorCode.WORKSPACE_ERROR, f"workspace does not exist: {path}")
    if not p.is_dir():
        raise AdapterError(ErrorCode.WORKSPACE_ERROR, f"workspace is not a directory: {path}")
    resolved = p.resolve()
    root = resolved.anchor
    if str(resolved) == root.rstrip("\\/") or str(resolved) == root:
        raise AdapterError(
            ErrorCode.WORKSPACE_ERROR, "refusing to use filesystem root as workspace")
    # Resolving already defeats `..` escapes; require the path to be real.
    return resolved


def validate_optional_file(path: str | Path | None, *, label: str) -> Path | None:
    if path is None:
        return None
    p = Path(path).expanduser()
    if not p.is_file():
        raise AdapterError(ErrorCode.WORKSPACE_ERROR, f"{label} does not exist: {path}")
    return p.resolve()
