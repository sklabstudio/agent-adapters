"""Gemini CLI adapter — PROVISIONAL (gemini CLI not installed, 2026-09-04).

Public documented behavior used (conservatively, all help-probed at runtime):
- ``gemini -p/--prompt "<prompt>"`` non-interactive execution
- ``--model`` model selection, ``--output-format`` machine-readable output
- ``--resume``/``--continue`` session handling where advertised

Flags are only added when the live ``--help`` text advertises them.
"""

from __future__ import annotations

from pathlib import Path

from sklab_agent_adapters.adapters.base import AgentAdapter, AuthResult, ModelsResult
from sklab_agent_adapters.adapters.registry import register_adapter
from sklab_agent_adapters.core.capabilities import Capability, CapabilityInfo, cap
from sklab_agent_adapters.core.models import AgentRunRequest, AuthState


@register_adapter
class GeminiCliAdapter(AgentAdapter):
    agent_id = "gemini"
    display_name = "Gemini CLI"
    homepage = "https://github.com/google-gemini/gemini-cli"
    executable_candidates = ["gemini", "gemini.exe", "gemini.cmd"]
    known_versions = ()
    native_install_hint = "Install the Gemini CLI, then complete its official login."

    _help_cache: str | None = None

    def _help(self) -> str:
        if self._help_cache is None:
            self._help_cache = self.help_text() or ""
        return self._help_cache

    def _supports(self, *flags: str) -> bool:
        text = self._help().lower()
        return any(f.lower() in text for f in flags)

    def get_capabilities(self) -> dict[Capability, CapabilityInfo]:
        pending = "gemini CLI not installed at build time; live verification pending"
        caps: dict[Capability, CapabilityInfo] = {
            c: cap(None, "unverified", pending) for c in Capability
        }
        caps[Capability.NON_INTERACTIVE] = cap(
            True, "docs", "-p/--prompt runs non-interactively; live check pending")
        caps[Capability.PATCH_OUTPUT] = cap(
            True, "adapter", "captured by SKLab git-diff layer post-run")
        if self._help():
            if self._supports("--model"):
                caps[Capability.MODEL_SELECTION] = cap(True, "cli_help", "--model advertised")
            if self._supports("--output-format"):
                caps[Capability.JSON_OUTPUT] = cap(True, "cli_help", "--output-format advertised")
            if self._supports("--resume", "--continue"):
                caps[Capability.SESSION_RESUME] = cap(True, "cli_help", "resume flag advertised")
        return caps

    def get_auth_status(self) -> AuthResult:
        return AuthResult(self.agent_id, AuthState.AUTH_UNKNOWN,
                          "gemini CLI not verified; use its official login, then re-check")

    def list_models(self) -> ModelsResult:
        return ModelsResult(self.agent_id, "unknown",
                            detail="no verified machine-readable model list; live check pending")

    def build_argv(
        self, request: AgentRunRequest, executable: str, workspace: Path
    ) -> tuple[list[str], list[str]]:
        from sklab_agent_adapters.core.errors import AdapterError, ErrorCode
        from sklab_agent_adapters.core.redaction import collect_sensitive_values, redact_text

        if not request.instruction.strip():
            raise AdapterError(ErrorCode.INVALID_CONFIGURATION, "gemini requires --instruction")
        prompt_flags = ("-p", "--prompt")
        use_flag = next((f for f in prompt_flags if self._supports(f)), "-p")
        argv = [executable, use_flag, request.instruction]
        if request.model and self._supports("--model"):
            argv += ["--model", request.model]
        if request.resume and request.session_id and self._supports("--resume"):
            argv += ["--resume", request.session_id]
        argv.extend(request.extra_args)
        sensitive = collect_sensitive_values(dict(request.environment or {}))
        return argv, [redact_text(a, sensitive) for a in argv]
