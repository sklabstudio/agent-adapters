"""Read-only Git helpers: baseline inspection without state mutation."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


def _git(workspace: Path, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — fixed "git" argv, no shell, workspace cwd
        ["git", *args],  # noqa: S607 — git resolved via PATH intentionally
        cwd=str(workspace),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


@dataclass
class GitBaseline:
    is_repo: bool
    head: str | None
    dirty: bool
    status_porcelain: str = ""


def is_repo(workspace: Path) -> bool:
    proc = _git(workspace, "rev-parse", "--is-inside-work-tree")
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def baseline(workspace: Path) -> GitBaseline:
    """Record HEAD + dirty state. Read-only; never resets/cleans/checkouts."""
    if not is_repo(workspace):
        return GitBaseline(is_repo=False, head=None, dirty=False)
    head_proc = _git(workspace, "rev-parse", "HEAD")
    head = head_proc.stdout.strip() or None
    status_proc = _git(workspace, "status", "--porcelain")
    porcelain = status_proc.stdout if status_proc.returncode == 0 else ""
    return GitBaseline(
        is_repo=True,
        head=head,
        dirty=bool(porcelain.strip()),
        status_porcelain=porcelain,
    )
