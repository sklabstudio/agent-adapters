"""Codex CLI adapter — verified against codex-cli 0.147.0 (live, 2026-09-04).

Verified evidence (``codex --help`` / ``codex exec --help`` / ``codex --version``):
- ``codex exec "<prompt>"`` non-interactive; ``-C/--cd DIR`` working root
- ``-m/--model``, ``--json`` JSONL events, ``--skip-git-repo-check``
- ``-i/--image``, ``-o/--output-last-message``, ``--output-schema``
- ``codex exec resume`` / ``codex resume`` session resume
- ``codex login`` / ``codex logout`` auth management (``login status`` live: ChatGPT)
- ``codex mcp`` MCP management, ``codex doctor`` health
"""

from __future__ import annotations

import json
import re
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

_TOKEN_FIELDS = ("input_tokens", "output_tokens", "cached_tokens", "reasoning_tokens")


@register_adapter
class CodexAdapter(AgentAdapter):
    agent_id = "codex"
    display_name = "Codex CLI"
    homepage = "https://github.com/openai/codex"
    executable_candidates = ["codex", "codex.exe", "codex.cmd"]
    known_versions = ("0.147.0",)
    native_install_hint = "Install the official Codex CLI, then `codex login`."

    def get_capabilities(self) -> dict[Capability, CapabilityInfo]:
        ev = "cli_help"
        return {
            Capability.FILES_READ: cap(
                True, ev, "workspace-rooted agent; read-only sandbox mode exists"),
            Capability.FILES_WRITE: cap(
                True, ev, "workspace-write sandbox mode; `apply` command"),
            Capability.SHELL: cap(
                True, ev, "sandbox policy governs model-generated shell commands"),
            Capability.GIT: cap(None, "unverified", "no git-specific flag verified"),
            Capability.MCP: cap(True, ev, "`mcp` subcommand verified"),
            Capability.SKILLS: cap(None, "unverified", "no skills flag verified"),
            Capability.SUBAGENTS: cap(None, "unverified", "no subagent flag verified"),
            Capability.SESSION_RESUME: cap(
                True, ev, "`exec resume` and `resume` commands verified"),
            Capability.NON_INTERACTIVE: cap(True, ev, "`exec` runs non-interactively"),
            Capability.STREAMING: cap(True, ev, "--json prints JSONL events"),
            Capability.JSON_OUTPUT: cap(True, ev, "--json JSONL event stream verified"),
            Capability.MODEL_SELECTION: cap(True, ev, "-m/--model verified"),
            Capability.CONTEXT_FILE: cap(
                None, "unverified", "stdin prompt supported; no context-file flag"),
            Capability.TASK_FILE: cap(None, "unverified", "prompt via arg/stdin"),
            Capability.PATCH_OUTPUT: cap(
                True, "adapter", "captured by SKLab git-diff layer post-run"),
            Capability.TOKEN_USAGE: cap(
                None, "unverified", "usage events not verified without paid call"),
            Capability.COST_USAGE: cap(None, "unverified", "no cost flag verified"),
            Capability.WEB_ACCESS: cap(None, "unverified", "no web flag verified"),
            Capability.IMAGE_INPUT: cap(True, ev, "-i/--image verified"),
        }

    def get_auth_status(self) -> AuthResult:
        try:
            run = self._run_probe(["login", "status"], timeout=30)
        except Exception:
            return AuthResult(self.agent_id, AuthState.AUTH_UNKNOWN, "login status probe failed")
        blob = ((run.stdout or "") + "\n" + (run.stderr or "")).strip()
        low = blob.lower()
        if "logged in" in low:
            return AuthResult(self.agent_id, AuthState.READY, "native login reported active")
        if "not logged in" in low or "no auth" in low or "missing" in low:
            return AuthResult(self.agent_id, AuthState.NOT_AUTHENTICATED,
                              "native login not present", login_hint="codex login")
        if run.exit_code != 0 and not blob:
            return AuthResult(self.agent_id, AuthState.AUTH_UNKNOWN, "empty login status output")
        return AuthResult(self.agent_id, AuthState.AUTH_UNKNOWN, "unparseable login status output")

    def login(self) -> AuthResult:
        from sklab_agent_adapters.core.errors import AdapterError, ErrorCode

        raise AdapterError(
            ErrorCode.CAPABILITY_UNSUPPORTED,
            "codex login is interactive; run `codex login`, then re-check auth",
        )

    def list_models(self) -> ModelsResult:
        return ModelsResult(self.agent_id, "unknown",
                            detail="no machine-readable model list flag verified")

    def build_argv(
        self, request: AgentRunRequest, executable: str, workspace: Path
    ) -> tuple[list[str], list[str]]:
        from sklab_agent_adapters.core.errors import AdapterError, ErrorCode
        from sklab_agent_adapters.core.redaction import collect_sensitive_values, redact_text

        if request.resume and request.session_id:
            argv = [executable, "exec", "resume", request.session_id]
            if request.model:
                argv += ["--model", request.model]
            argv += ["-C", str(workspace), "--skip-git-repo-check"]
            if request.instruction.strip():
                argv.append(request.instruction)
        else:
            if not request.instruction.strip():
                raise AdapterError(ErrorCode.INVALID_CONFIGURATION, "codex requires --instruction")
            argv = [executable, "exec", request.instruction,
                    "-C", str(workspace), "--skip-git-repo-check"]
            if request.model:
                argv += ["--model", request.model]
            if request.stream and "--json" not in request.extra_args:
                argv.append("--json")
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
            for key in ("session_id", "thread_id", "id"):
                val = obj.get(key) if isinstance(obj, dict) else None
                if isinstance(val, str) and val:
                    return val
        m = re.search(r"(?:session|thread)[_-]?id\s*[:=]\s*([A-Za-z0-9][A-Za-z0-9_\-\.]{2,})",
                      stdout + "\n" + stderr, re.IGNORECASE)
        return m.group(1) if m else None

    def extract_usage(self, stdout: str, stderr: str) -> tuple[TokenUsage | None, CostUsage | None]:
        found: dict[str, int] = {}
        for raw_line in (stdout + "\n" + stderr).splitlines():
            line = raw_line.strip()
            if not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            stack = [obj]
            while stack:
                cur = stack.pop()
                if isinstance(cur, dict):
                    for k, v in cur.items():
                        if (
                            k in _TOKEN_FIELDS
                            and isinstance(v, int)
                        ):
                            found.setdefault(k, v)
                        elif isinstance(v, (dict, list)):
                            stack.append(v)
                elif isinstance(cur, list):
                    stack.extend(cur)
        if not found:
            return None, None
        return TokenUsage(
            input_tokens=found.get("input_tokens"),
            output_tokens=found.get("output_tokens"),
            cached_tokens=found.get("cached_tokens"),
            reasoning_tokens=found.get("reasoning_tokens"),
            source="codex --json events",
        ), None
