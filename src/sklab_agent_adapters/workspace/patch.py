"""Patch capture: post-run diff vs baseline, control files excluded, no mutation."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from sklab_agent_adapters.core.models import CONTROL_FILENAMES
from sklab_agent_adapters.workspace.git import is_repo


@dataclass
class PatchCapture:
    enabled: bool
    patch_path: str | None = None
    fingerprint: str | None = None
    changed_files: list[str] = field(default_factory=list)
    dirty_before: bool = False
    notes: list[str] = field(default_factory=list)


def _git(workspace: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
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


def _changed_files(workspace: Path) -> list[str]:
    proc = _git(workspace, "status", "--porcelain")
    if proc.returncode != 0:
        return []
    files: list[str] = []
    for line in proc.stdout.splitlines():
        # Format: XY <path>[ -> <newpath>]
        name = line[3:].strip()
        if " -> " in name:
            name = name.split(" -> ", 1)[1].strip()
        name = name.strip('"')
        if Path(name).name in CONTROL_FILENAMES:
            continue
        files.append(name)
    return sorted(set(files))


def _untracked_diff(workspace: Path, files: list[str]) -> str:
    """Render untracked files as /dev/null unified diffs (read-only)."""
    chunks: list[str] = []
    for rel in files:
        target = workspace / rel
        if not target.is_file():
            continue
        try:
            if target.stat().st_size > 1_000_000:
                chunks.append(f"--- /dev/null\n+++ b/{rel}\n@@ binary/large file omitted @@\n")
                continue
            content = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        chunks.append(f"--- /dev/null\n+++ b/{rel}\n")
        for line in content.splitlines():
            chunks.append(f"+{line}\n")
    return "".join(chunks)


def capture_patch(
    workspace: Path,
    *,
    dirty_before: bool,
    out_path: str | Path | None = None,
) -> PatchCapture:
    """Capture post-run patch without mutating Git state.

    Tracked changes come from ``git diff HEAD`` (control files excluded via
    pathspec); untracked files are appended as /dev/null diffs. The SHA-256
    fingerprint covers the final patch bytes.
    """
    if not is_repo(workspace):
        return PatchCapture(enabled=False, dirty_before=dirty_before,
                            notes=["not a git repository"])
    changed = _changed_files(workspace)
    exclude = [f":!{name}" for name in CONTROL_FILENAMES]
    diff_proc = _git(workspace, "diff", "HEAD", "--", ".", *exclude)
    tracked_diff = diff_proc.stdout if diff_proc.returncode == 0 else ""

    untracked_proc = _git(workspace, "ls-files", "--others", "--exclude-standard")
    untracked = (
        [entry.strip() for entry in untracked_proc.stdout.splitlines() if entry.strip()]
        if untracked_proc.returncode == 0
        else []
    )
    untracked = [f for f in untracked if Path(f).name not in CONTROL_FILENAMES]
    patch_text = tracked_diff
    if untracked:
        patch_text += _untracked_diff(workspace, untracked)

    fingerprint = hashlib.sha256(patch_text.encode("utf-8")).hexdigest()
    result = PatchCapture(
        enabled=True,
        fingerprint=fingerprint,
        changed_files=sorted(set(changed) | set(untracked)),
        dirty_before=dirty_before,
    )
    if out_path is not None and patch_text.strip():
        dest = Path(out_path)
        dest.write_text(patch_text, encoding="utf-8")
        result.patch_path = str(dest)
    notes: list[str] = []
    if dirty_before:
        notes.append("DIRTY_WORKSPACE: pre-existing changes preserved, not attributed to agent")
    if not patch_text.strip():
        notes.append("no changes detected")
    result.notes = notes
    return result
