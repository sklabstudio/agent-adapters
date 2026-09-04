"""Version compatibility states — unknown/new versions never claim full support."""

from __future__ import annotations

from sklab_agent_adapters.core.models import Compatibility
from sklab_agent_adapters.detection.versions import ParsedVersion, _tuple


def classify(
    parsed: ParsedVersion,
    *,
    installed: bool,
    minimum_version: str | None = None,
) -> Compatibility:
    if not installed:
        return Compatibility.UNAVAILABLE
    if parsed.normalized is None:
        return Compatibility.UNKNOWN_VERSION
    if minimum_version:
        try:
            if _tuple(parsed.normalized) < _tuple(minimum_version):
                return Compatibility.TOO_OLD
        except ValueError:
            return Compatibility.UNKNOWN_VERSION
    if parsed.known:
        return Compatibility.SUPPORTED
    if parsed.newer_than_known:
        return Compatibility.SUPPORTED_WITH_WARNINGS
    return Compatibility.UNKNOWN_VERSION
