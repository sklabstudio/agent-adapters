"""Deterministic cross-platform fake agent for tests and dogfood.

Usage (argv array, never shell):
    python fake_agent.py --mode <mode> [--workspace DIR] [--file NAME] [--extra ...]

Modes:
    success_edit   append a line to <workspace>/<file> (default hello.txt), exit 0
    fail           exit 3 with stderr message
    auth_required  exit 4 printing "not authenticated" marker
    timeout        sleep 60s (runner must kill it), exit 0 if not killed
    no_changes     exit 0 without touching anything
    stream         print 5 stdout + 3 stderr lines with flush, exit 0
    jsonl          print 3 JSON event lines + final result JSON, exit 0
    session_create print {"session_id": "sess-<pid>"} line, exit 0
    session_resume require --session-id, echo it back, exit 0 (else exit 2)
    usage          print result JSON with usage + cost fields, exit 0
    malformed      print non-JSON garbage on stdout, exit 0
    echo_args      print argv as JSON (for placeholder/dry-run-adjacent checks)
    leak           print FAKE_SECRET_TOKEN env value to stdout (redaction test)
    ignore_term    ignore SIGTERM once then sleep (cleanup robustness check)

All modes are deterministic and require no network, no API keys, no paid calls.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", default="success_edit")
    p.add_argument("--workspace", default=".")
    p.add_argument("--file", default="hello.txt")
    p.add_argument("--session-id", default="")
    p.add_argument("--extra", nargs=argparse.REMAINDER, default=[])
    return p.parse_args()


def main() -> int:
    args = _parse()
    mode = args.mode
    ws = args.workspace

    if mode == "success_edit":
        with open(os.path.join(ws, args.file), "a", encoding="utf-8") as fh:
            fh.write("fake-agent edit\n")
        print("done: edited file")
        return 0
    if mode == "fail":
        print("fake failure: something broke", file=sys.stderr)
        return 3
    if mode == "auth_required":
        print("Error: not authenticated. Please run login.", file=sys.stderr)
        return 4
    if mode == "timeout":
        time.sleep(60)
        print("should have been killed")
        return 0
    if mode == "no_changes":
        print("no changes made")
        return 0
    if mode == "stream":
        for i in range(5):
            print(f"stdout line {i}", flush=True)
            time.sleep(0.02)
        for i in range(3):
            print(f"stderr line {i}", file=sys.stderr, flush=True)
            time.sleep(0.02)
        return 0
    if mode == "jsonl":
        print(json.dumps({"type": "TOOL_EVENT", "tool": {"name": "Edit"}}), flush=True)
        print(json.dumps({"type": "SESSION_EVENT", "session_id": "sess-fake-1"}), flush=True)
        print(json.dumps({"type": "USAGE_EVENT", "input_tokens": 10, "output_tokens": 5}), flush=True)
        print(json.dumps({"type": "result", "session_id": "sess-fake-1",
                           "usage": {"input_tokens": 10, "output_tokens": 5},
                           "total_cost_usd": 0.001}))
        return 0
    if mode == "session_create":
        print(json.dumps({"session_id": "sess-fake-new"}), flush=True)
        print("session created")
        return 0
    if mode == "session_resume":
        if not args.session_id:
            print("SESSION_NOT_FOUND: --session-id required", file=sys.stderr)
            return 2
        print(f"resumed {args.session_id}")
        return 0
    if mode == "usage":
        print(json.dumps({"type": "result", "session_id": "sess-usage-1",
                           "usage": {"input_tokens": 120, "output_tokens": 45,
                                     "cache_read_input_tokens": 10},
                           "total_cost_usd": 0.0042}))
        return 0
    if mode == "malformed":
        print("not json at all {{{oops")
        print("second garbage line", file=sys.stderr)
        return 0
    if mode == "echo_args":
        print(json.dumps({"argv": sys.argv[1:]}))
        return 0
    if mode == "leak":
        print(f"leaked={os.environ.get('FAKE_SECRET_TOKEN', '')}")
        return 0
    if mode == "ignore_term":
        import signal as _signal

        def _once(signum: int, frame: object) -> None:
            _signal.signal(_signal.SIGTERM, _signal.SIG_DFL)
            print("ignored first SIGTERM", flush=True)

        if hasattr(_signal, "SIGTERM"):
            _signal.signal(_signal.SIGTERM, _once)
        time.sleep(30)
        print("survived (cleanup must SIGKILL/terminate)")
        return 0
    print(f"unknown mode: {mode}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
