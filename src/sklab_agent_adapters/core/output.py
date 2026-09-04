"""Output helpers: JSON-only stdout, diagnostics on stderr."""

from __future__ import annotations

import json
import sys
from typing import Any

from rich.console import Console

err_console = Console(stderr=True)


def print_json(data: Any) -> None:
    """Print valid JSON to stdout — nothing else may go to stdout with --json."""
    sys.stdout.write(json.dumps(data, indent=2, default=str))
    sys.stdout.write("\n")
    sys.stdout.flush()


def print_jsonl(obj: Any) -> None:
    sys.stdout.write(json.dumps(obj, default=str) + "\n")
    sys.stdout.flush()


def warn(message: str) -> None:
    err_console.print(f"[yellow]warning:[/yellow] {message}")
