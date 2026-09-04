"""JSON report writer (redacted by construction — callers pass redacted data)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_report(data: dict[str, Any], path: str | Path) -> str:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return str(dest)
