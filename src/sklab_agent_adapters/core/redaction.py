"""Secret redaction: never persist raw credentials in logs/reports/errors."""

from __future__ import annotations

import os
import re

REDACTED = "[REDACTED]"

# Generic high-entropy token shapes seen across providers.
_TOKEN_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9\-_]{8,}"),
    re.compile(r"sk-ant-[A-Za-z0-9\-_]{8,}"),
    re.compile(r"xox[bap]-[A-Za-z0-9\-]+"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{8,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{8,}"),
    re.compile(r"AIza[A-Za-z0-9\-_]{10,}"),
    re.compile(r"ya29\.[A-Za-z0-9\-_]+"),
    re.compile(r"glpat-[A-Za-z0-9\-_]{8,}"),
]

_SENSITIVE_NAME_HINTS = ("API_KEY", "APIKEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIALS", "AUTH")


def collect_sensitive_values(extra: dict[str, str] | None = None) -> list[str]:
    """Collect candidate secret values from the host env plus explicit extras.

    Only values of suspiciously-named variables (or explicit extras) are
    collected — the full environment is never serialized.
    """
    values: list[str] = []
    for name, val in os.environ.items():
        upper = name.upper()
        if any(hint in upper for hint in _SENSITIVE_NAME_HINTS) and val and len(val) >= 8:
            values.append(val)
    if extra:
        values.extend(v for v in extra.values() if v and len(v) >= 8)
    # Longest first so overlapping values redact cleanly.
    return sorted(set(values), key=len, reverse=True)


def redact_text(text: str, sensitive: list[str] | None = None) -> str:
    """Redact known secret values and generic token shapes from text."""
    out = text
    for secret in sensitive or []:
        if secret:
            out = out.replace(secret, REDACTED)
    for pattern in _TOKEN_PATTERNS:
        out = pattern.sub(REDACTED, out)
    return out


def redact_mapping(mapping: dict[str, str], sensitive: list[str] | None = None) -> dict[str, str]:
    """Redact values in a string mapping (e.g. env snapshot for reports)."""
    return {k: redact_text(v, sensitive) for k, v in mapping.items()}


def env_var_names_only(env: dict[str, str]) -> list[str]:
    """Return sorted env var names for dry-run display (never values)."""
    return sorted(env.keys())
