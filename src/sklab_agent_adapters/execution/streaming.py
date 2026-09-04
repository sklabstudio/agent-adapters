"""Normalized streaming events (RUN_STARTED ... RUN_FINISHED)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from enum import StrEnum

from sklab_agent_adapters.core.models import utcnow_iso


class StreamEventType(StrEnum):
    RUN_STARTED = "RUN_STARTED"
    STDOUT = "STDOUT"
    STDERR = "STDERR"
    TOOL_EVENT = "TOOL_EVENT"
    SESSION_EVENT = "SESSION_EVENT"
    USAGE_EVENT = "USAGE_EVENT"
    RUN_FINISHED = "RUN_FINISHED"
    WARNING = "WARNING"
    ERROR = "ERROR"


def make_event(
    kind: StreamEventType, data: dict[str, object] | None = None
) -> dict[str, object]:
    return {
        "type": kind.value,
        "at": utcnow_iso(),
        "data": data or {},
    }


def iter_jsonl(text: str) -> Iterator[dict[str, object]]:
    """Yield parsed JSON objects from JSONL text; skip blank/malformed lines."""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            yield obj


def coerce_agent_event(obj: dict[str, object], agent_id: str) -> dict[str, object]:
    """Conservatively map a foreign structured event to a normalized envelope.

    Unknown shapes become STDOUT-carried text; tool/session/usage events are
    only produced when the source object explicitly carries those fields.
    Never invents tool events from arbitrary prose.
    """
    kind = str(obj.get("type", "")).upper()
    if kind in ("TOOL_EVENT", "TOOL_USE", "TOOL_RESULT") and isinstance(
        obj.get("tool"), (dict, str)
    ):
        return make_event(StreamEventType.TOOL_EVENT, {"agent": agent_id, "event": obj})
    if kind in ("SESSION_EVENT", "SESSION") and "session_id" in obj:
        return make_event(StreamEventType.SESSION_EVENT, {"agent": agent_id, "event": obj})
    if kind in ("USAGE_EVENT", "USAGE", "TOKEN_USAGE") and any(
        k in obj for k in ("input_tokens", "output_tokens", "usage", "tokens")
    ):
        return make_event(StreamEventType.USAGE_EVENT, {"agent": agent_id, "event": obj})
    if kind == "ERROR" or "error" in obj:
        return make_event(StreamEventType.ERROR, {"agent": agent_id, "event": obj})
    text = str(obj.get("text") or obj.get("message") or obj.get("content") or "")
    if text:
        return make_event(StreamEventType.STDOUT, {"agent": agent_id, "text": text})
    return make_event(StreamEventType.STDOUT, {"agent": agent_id, "text": json.dumps(obj)})
