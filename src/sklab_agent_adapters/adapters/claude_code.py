"""Claude Code adapter — verified against 2.1.198 (live --help, 2026-09-04).

Verified evidence (``claude --help`` / ``claude --version``):
- ``-p/--print`` non-interactive; ``--output-format text|json|stream-json``
- ``--model``, ``-r/--resume [id]``, ``--continue``, ``--session-id <uuid>``
- ``--add-dir``, ``--allowedTools/--disallowedTools``, ``--tools``, ``--agents``
- ``--disable-slash-commands`` ("Disable all skills" => skills exist)
- ``--mcp-config`` / ``mcp`` subcommand, ``doctor``, ``auth`` commands
- ``--worktree`` (git worktree), ``--max-budget-usd``? (NOT verified — never passed)

``--output-format json`` envelope (session_id, usage, total_cost_usd) is
documented behavior parsed best-effort; live inference never runs in CI.
"""

from __future__ import annotations

import json
from pathlib import Path

from sklab_agent_adapters.adapters.base import AgentAdapter, AuthResult, ModelsResult
from sklab_agent_adapters.adapters.registry import register_adapter
from sklab_agent_adapters.core.capabilities import Capability, CapabilityInfo, cap
from sklab_agent_adapters.core.models import (
    AgentRunRequest,
    AuthState,
    CostUsage,
    TokenUsage,
)


def _usage_int(usage: dict[str, object], key: str) -> int | None:
    value = usage.get(key)
    return value if isinstance(value, int) else None


@register_adapter
class ClaudeCodeAdapter(AgentAdapter):
    agent_id = "claude"
    display_name = "Claude Code"
    homepage = "https://github.com/anthropics/claude-code"
    executable_candidates = ["claude", "claude.exe", "claude.cmd"]
    known_versions = ("2.1.198",)
    native_install_hint = "Install Claude Code (`npm i -g @anthropic-ai/claude-code`)."

    def get_capabilities(self) -> dict[Capability, CapabilityInfo]:
        ev = "cli_help"
        return {
            Capability.FILES_READ: cap(
                True, ev, "Read tool; --add-dir grants directory access"),
            Capability.FILES_WRITE: cap(
                True, ev, "Edit tool; --allowedTools/--tools gate mutations"),
            Capability.SHELL: cap(True, ev, "Bash tool documented in --tools help"),
            Capability.GIT: cap(True, ev, "--worktree creates git worktrees"),
            Capability.MCP: cap(
                True, ev, "--mcp-config and `mcp` subcommand verified"),
            Capability.SKILLS: cap(
                True, ev, "--disable-slash-commands disables skills"),
            Capability.SUBAGENTS: cap(
                True, ev, "--agent/--agents define custom agents"),
            Capability.SESSION_RESUME: cap(
                True, ev, "--resume/--continue/--session-id verified"),
            Capability.NON_INTERACTIVE: cap(
                True, ev, "-p/--print documented for non-interactive output"),
            Capability.STREAMING: cap(
                True, ev, "--output-format stream-json verified"),
            Capability.JSON_OUTPUT: cap(
                True, ev, "--output-format json verified"),
            Capability.MODEL_SELECTION: cap(True, ev, "--model verified"),
            Capability.CONTEXT_FILE: cap(
                None, "unverified", "no context-file flag verified"),
            Capability.TASK_FILE: cap(
                None, "unverified", "prompt via positional arg"),
            Capability.PATCH_OUTPUT: cap(
                True, "adapter", "captured by SKLab git-diff layer post-run"),
            Capability.TOKEN_USAGE: cap(
                True, "docs", "--output-format json carries usage"),
            Capability.COST_USAGE: cap(
                True, "docs", "--output-format json carries total cost"),
            Capability.WEB_ACCESS: cap(None, "unverified", "no web flag verified"),
            Capability.IMAGE_INPUT: cap(
                None, "unverified", "no image flag verified in --help"),
        }

    def get_auth_status(self) -> AuthResult:
        # `claude auth` exists but no machine-readable status flag is verified;
        # probe conservatively and degrade to AUTH_UNKNOWN rather than misparse.
        try:
            run = self._run_probe(["auth", "status"], timeout=30)
        except Exception:
            return AuthResult(self.agent_id, AuthState.AUTH_UNKNOWN, "auth probe failed")
        blob = ((run.stdout or "") + "\n" + (run.stderr or "")).strip()
        low = blob.lower()
        ready_markers = ("logged in", "authenticated", "active", "connected", "subscribed")
        if run.exit_code == 0 and any(s in low for s in ready_markers):
            return AuthResult(self.agent_id, AuthState.READY, "native auth reported active")
        missing_markers = ("not logged in", "not authenticated", "logged out", "no auth")
        if any(s in low for s in missing_markers):
            return AuthResult(self.agent_id, AuthState.NOT_AUTHENTICATED,
                              "native auth not present", login_hint="claude auth login")
        return AuthResult(
            self.agent_id, AuthState.AUTH_UNKNOWN,
            "no verified machine-readable auth status; use `claude auth login` if needed",
        )

    def list_models(self) -> ModelsResult:
        return ModelsResult(self.agent_id, "unknown",
                            detail="no machine-readable model list flag verified")

    def build_argv(
        self, request: AgentRunRequest, executable: str, workspace: Path
    ) -> tuple[list[str], list[str]]:
        from sklab_agent_adapters.core.errors import AdapterError, ErrorCode
        from sklab_agent_adapters.core.redaction import collect_sensitive_values, redact_text

        if not request.instruction.strip():
            raise AdapterError(ErrorCode.INVALID_CONFIGURATION, "claude requires --instruction")
        argv = [executable, "-p", request.instruction]
        if request.model:
            argv += ["--model", request.model]
        if request.resume and request.session_id:
            argv += ["--resume", request.session_id]
        elif request.session_id:
            argv += ["--session-id", request.session_id]
        has_format = any(
            a == "--output-format" or a.startswith("--output-format=")
            for a in request.extra_args
        )
        if not has_format:
            argv += ["--output-format", "stream-json" if request.stream else "json"]
        argv.extend(request.extra_args)
        sensitive = collect_sensitive_values(dict(request.environment or {}))
        return argv, [redact_text(a, sensitive) for a in argv]

    def extract_session(self, stdout: str, stderr: str) -> str | None:
        for raw_line in (stdout + "\n" + stderr).splitlines():
            line = raw_line.strip()
            if not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                sid = obj.get("session_id") or obj.get("sessionId")
                if isinstance(sid, str) and sid:
                    return sid
        return None

    def extract_usage(self, stdout: str, stderr: str) -> tuple[TokenUsage | None, CostUsage | None]:
        tokens: TokenUsage | None = None
        cost: CostUsage | None = None
        for raw_line in (stdout + "\n" + stderr).splitlines():
            line = raw_line.strip()
            if not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            # Only `result` envelopes carry totals; other events are scanned
            # best-effort for embedded usage payloads.
            usage = obj.get("usage") if isinstance(obj, dict) else None
            if isinstance(usage, dict):
                tokens = TokenUsage(
                    input_tokens=_usage_int(usage, "input_tokens"),
                    output_tokens=_usage_int(usage, "output_tokens"),
                    cached_tokens=_usage_int(usage, "cache_read_input_tokens"),
                    reasoning_tokens=None,
                    source="claude --output-format json",
                )
            total = obj.get("total_cost_usd") if isinstance(obj, dict) else None
            if isinstance(total, (int, float)):
                cost = CostUsage(amount=float(total), currency="USD",
                                 source="claude --output-format json")
            if tokens is not None and cost is not None:
                break
        return tokens, cost
