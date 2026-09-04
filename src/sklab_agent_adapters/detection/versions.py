"""Conservative version parsing: known / unknown-newer / malformed."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ParsedVersion:
    raw: str
    normalized: str | None  # e.g. "0.20.3" or None when unparseable
    known: bool  # matches a pinned known-good sample
    newer_than_known: bool


_VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


def extract_version(text: str) -> str | None:
    """Extract the first X.Y[.Z] triple from free-form version output."""
    m = _VERSION_RE.search(text or "")
    if not m:
        return None
    major, minor, patch = m.group(1), m.group(2), m.group(3) or "0"
    return f"{int(major)}.{int(minor)}.{int(patch)}"


def _tuple(v: str) -> tuple[int, int, int]:
    parts = (v.split(".") + ["0", "0"])[:3]
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def parse_version_output(
    text: str, *, known_versions: tuple[str, ...] = ()
) -> ParsedVersion:
    raw = (text or "").strip()
    normalized = extract_version(raw)
    if normalized is None:
        return ParsedVersion(raw=raw, normalized=None, known=False, newer_than_known=False)
    known = normalized in known_versions
    newer = False
    if known_versions and not known:
        try:
            newest = max(_tuple(v) for v in known_versions)
            newer = _tuple(normalized) > newest
        except ValueError:
            newer = False
    return ParsedVersion(
        raw=raw, normalized=normalized, known=known, newer_than_known=newer
    )
