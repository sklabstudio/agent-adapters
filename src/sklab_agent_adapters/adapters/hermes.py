"""Hermes adapter — verified against Hermes Agent v0.20.3 (live, 2026-09-04).

Verified evidence (``hermes --help`` / ``hermes --version`` / ``hermes status``):
- ``-z/--oneshot PROMPT`` one-shot non-interactive mode
- ``--in DIR`` working directory, ``-m/--model``, ``--provider``
- ``--resume SESSION`` / ``--continue``, ``--usage-file PATH`` (oneshot JSON report)
- ``--skills SKILLS``, ``sessions`` / ``mcp`` / ``skills`` / ``auth`` / ``status`` / ``doctor``
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from sklab_agent_adapters.adapters.base import AgentAdapter, AuthResult, ModelsResult
from sklab_agent_adapters.adapters.registry import register_adapter
from sklab_agent_adapters.core.capabilities import Capability, CapabilityInfo, cap
from sklab_agent_adapters.core.models import (
    AgentRunRequest,
    AgentRunResult,
    AuthState,
    CostUsage,
    TokenUsage,
)


@register_adapter
class HermesAdapter(AgentAdapter):
    agent_id = "hermes"
    display_name = "Hermes"
    homepage = "https://github.com/hermes-agent/hermes"
    executable_candidates = ["hermes", "hermes.exe"]
    known_versions = ("0.20.3",)
    native_install_hint = "Install Hermes Agent, then ensure `hermes` is on PATH."
    _usage_file: str | None = None

    def get_capabilities(self) -> dict[Capability, CapabilityInfo]:
        ev = "cli_help"
        return {
            Capability.FILES_READ: cap(
                True, ev, "-z loads tools, memory, rules, AGENTS.md from CWD"),
            Capability.FILES_WRITE: cap(
                True, ev, "tool-calling agent; approvals auto-bypassed in -z"),
            Capability.SHELL: cap(
                True, ev, "tool-calling with terminal backend (see `status`)"),
            Capability.GIT: cap(True, ev, "--worktree implies git worktree support"),
            Capability.MCP: cap(True, ev, "`mcp` subcommand verified in --help"),
            Capability.SKILLS: cap(
                True, ev, "--skills flag and `skills` subcommand verified"),
            Capability.SUBAGENTS: cap(
                None, "unverified", "no subagent flag verified in --help"),
            Capability.SESSION_RESUME: cap(
                True, ev, "--resume/--continue and `sessions` subcommand"),
            Capability.NON_INTERACTIVE: cap(
                True, ev, "-z/--oneshot documented for scripts/pipes"),
            Capability.STREAMING: cap(
                None, "unverified", "no streaming flag verified for -z mode"),
            Capability.JSON_OUTPUT: cap(
                None, ev, "-z prints final text; --usage-file has JSON report"),
            Capability.MODEL_SELECTION: cap(
                True, ev, "-m/--model and --provider verified"),
            Capability.CONTEXT_FILE: cap(
                None, "unverified", "no context-file flag verified"),
            Capability.TASK_FILE: cap(None, "unverified", "prompt via -z arg"),
            Capability.PATCH_OUTPUT: cap(
                True, "adapter", "captured by SKLab git-diff layer post-run"),
            Capability.TOKEN_USAGE: cap(
                True, ev, "--usage-file JSON report (model, tokens, cost)"),
            Capability.COST_USAGE: cap(
                True, ev, "--usage-file JSON report includes estimated cost"),
            Capability.WEB_ACCESS: cap(
                None, "unverified", "egress/firewall config exists; not probed"),
            Capability.IMAGE_INPUT: cap(None, "unverified", "no image flag verified"),
        }

    # -- auth ---------------------------------------------------------
    def get_auth_status(self) -> AuthResult:
        try:
            run = self._run_probe(["status"], timeout=30)
        except Exception:
            return AuthResult(self.agent_id, AuthState.AUTH_UNKNOWN, "status probe failed")
        blob = (run.stdout or "") + "\n" + (run.stderr or "")
        if "✓" in blob or "logged in" in blob.lower():
            # Any ready key/provider counts; detail stays redacted by healthcheck.
            ready_lines = [ln.strip() for ln in blob.splitlines() if "✓" in ln]
            return AuthResult(
                self.agent_id, AuthState.READY,
                f"{len(ready_lines)} provider(s) ready via native auth",
                login_hint=None,
            )
        if "✗" in blob or "not logged in" in blob.lower() or "not set" in blob.lower():
            return AuthResult(
                self.agent_id, AuthState.NOT_AUTHENTICATED,
                "no ready provider in `hermes status`",
                login_hint="hermes model  (official interactive setup)",
            )
        return AuthResult(self.agent_id, AuthState.AUTH_UNKNOWN, "unparseable status output")

    def list_models(self) -> ModelsResult:
        return ModelsResult(
            agent_id=self.agent_id, state="unknown",
            detail="`hermes model` is interactive; no machine-readable list verified",
        )

    # -- run ----------------------------------------------------------
    def _pre_run(self, request: AgentRunRequest, workspace: Path) -> None:
        fd, path = tempfile.mkstemp(prefix="sklab-hermes-usage-", suffix=".json")
        import os as _os

        _os.close(fd)
        self._usage_file: str = path

    def build_argv(
        self, request: AgentRunRequest, executable: str, workspace: Path
    ) -> tuple[list[str], list[str]]:
        from sklab_agent_adapters.core.errors import AdapterError, ErrorCode
        from sklab_agent_adapters.core.redaction import collect_sensitive_values, redact_text

        if not request.instruction.strip():
            raise AdapterError(ErrorCode.INVALID_CONFIGURATION, "hermes requires --instruction")
        argv = [executable, "-z", request.instruction, "--in", str(workspace)]
        if request.model:
            argv += ["-m", request.model]
        usage_file = getattr(self, "_usage_file", None)
        if usage_file:
            argv += ["--usage-file", usage_file]
        if request.resume and request.session_id:
            argv += ["--resume", request.session_id]
        argv.extend(request.extra_args)
        sensitive = collect_sensitive_values(dict(request.environment or {}))
        return argv, [redact_text(a, sensitive) for a in argv]

    def _enrich_result(self, request: AgentRunRequest, result: AgentRunResult) -> AgentRunResult:
        usage_file = getattr(self, "_usage_file", None)
        self._usage_file = None
        if not usage_file:
            return result
        try:
            raw = Path(usage_file).read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, ValueError):
            return result
        finally:
            try:
                Path(usage_file).unlink(missing_ok=True)
            except OSError:
                pass
        if isinstance(data, dict):
            tokens, cost = self._parse_usage_dict(data)
            if tokens is not None:
                result.token_usage = tokens
            if cost is not None:
                result.cost_usage = cost
        return result

    @staticmethod
    def _parse_usage_dict(data: dict[str, object]) -> tuple[TokenUsage | None, CostUsage | None]:
        def _int(*keys: str) -> int | None:
            for k in keys:
                v = data.get(k)
                if isinstance(v, bool):
                    continue
                if isinstance(v, (int, float)):
                    return int(v)
            usage = data.get("usage")
            if isinstance(usage, dict):
                for k in keys:
                    v = usage.get(k)
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        return int(v)
            return None

        def _float(*keys: str) -> float | None:
            for k in keys:
                v = data.get(k)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    return float(v)
            return None

        tokens: TokenUsage | None = None
        token_keys = ("input_tokens", "prompt_tokens", "output_tokens", "completion_tokens")
        if any(_int(k) is not None for k in token_keys):
            tokens = TokenUsage(
                input_tokens=_int("input_tokens", "prompt_tokens"),
                output_tokens=_int("output_tokens", "completion_tokens"),
                cached_tokens=_int("cached_tokens"),
                reasoning_tokens=_int("reasoning_tokens"),
                source="hermes --usage-file",
            )
        cost: CostUsage | None = None
        amount = _float("cost", "estimated_cost", "total_cost", "amount")
        if amount is not None:
            currency = data.get("currency")
            cost = CostUsage(
                amount=amount,
                currency=currency if isinstance(currency, str) else "USD",
                source="hermes --usage-file",
            )
        return tokens, cost

    def extract_session(self, stdout: str, stderr: str) -> str | None:
        m = re.search(r"session[_-]?id\s*[:=]\s*([A-Za-z0-9][A-Za-z0-9_\-\.]{2,})",
                      stdout + "\n" + stderr, re.IGNORECASE)
        return m.group(1) if m else None
