"""Zero adapter — PROVISIONAL (Zero CLI not installed at build time, 2026-09-04).

Strategy: detect via PATH, parse ``--version`` conservatively, and choose run
argv by probing ``--help`` text at runtime (``run`` subcommand vs bare prompt)
instead of hardcoding stale assumptions. Capabilities stay ``unknown`` until
verified against a real CLI. Live verification is pending.
"""

from __future__ import annotations

from pathlib import Path

from sklab_agent_adapters.adapters.base import AgentAdapter, AuthResult, ModelsResult
from sklab_agent_adapters.adapters.registry import register_adapter
from sklab_agent_adapters.core.capabilities import Capability, CapabilityInfo, cap
from sklab_agent_adapters.core.models import AgentRunRequest, AuthState


@register_adapter
class ZeroAdapter(AgentAdapter):
    agent_id = "zero"
    display_name = "Zero"
    homepage = "https://github.com/sklabstudio/agent-adapters/blob/main/docs/adapters.md#zero-provisional"
    executable_candidates = ["zero", "zero.exe", "zero.cmd"]
    known_versions = ()
    native_install_hint = "Install the Zero CLI, then ensure `zero` is on PATH."

    _help_cache: str | None = None

    def _help(self) -> str:
        if self._help_cache is None:
            self._help_cache = self.help_text() or ""
        return self._help_cache

    def get_capabilities(self) -> dict[Capability, CapabilityInfo]:
        pending = "Zero CLI not installed at build time; live verification pending"
        caps: dict[Capability, CapabilityInfo] = {
            c: cap(None, "unverified", pending) for c in Capability
        }
        caps[Capability.PATCH_OUTPUT] = cap(
            True, "adapter", "captured by SKLab git-diff layer post-run")
        return caps

    def get_auth_status(self) -> AuthResult:
        return AuthResult(self.agent_id, AuthState.AUTH_UNKNOWN,
                          "Zero CLI not verified; live auth check pending")

    def list_models(self) -> ModelsResult:
        return ModelsResult(self.agent_id, "unknown", detail="Zero CLI not verified")

    def _supports(self, *flags: str) -> bool:
        text = self._help().lower()
        return any(f.lower() in text for f in flags)

    def build_argv(
        self, request: AgentRunRequest, executable: str, workspace: Path
    ) -> tuple[list[str], list[str]]:
        from sklab_agent_adapters.core.errors import AdapterError, ErrorCode
        from sklab_agent_adapters.core.redaction import collect_sensitive_values, redact_text

        if not request.instruction.strip():
            raise AdapterError(ErrorCode.INVALID_CONFIGURATION, "zero requires --instruction")
        argv = [executable]
        help_words = self._help().lower().split()
        if "run" in help_words:
            argv.append("run")
        argv.append(request.instruction)
        for flag in ("--workspace", "--cwd", "--dir"):
            if self._supports(flag):
                argv += [flag, str(workspace)]
                break
        if request.model and self._supports("--model", "-m "):
            argv += ["--model", request.model]
        if request.resume and request.session_id and self._supports("--resume", "--session"):
            argv += ["--resume", request.session_id]
        elif request.session_id and self._supports("--session"):
            argv += ["--session", request.session_id]
        argv.extend(request.extra_args)
        sensitive = collect_sensitive_values(dict(request.environment or {}))
        return argv, [redact_text(a, sensitive) for a in argv]
