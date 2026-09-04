"""OpenCode adapter — PROVISIONAL (opencode CLI not installed, 2026-09-04).

Public documented behavior used (conservatively, all help-probed at runtime):
- ``opencode run "<message>"`` non-interactive task run
- ``--model`` model selection, ``--session``/``--continue`` session handling
- ``auth`` command family for provider readiness (probed, never assumed)

Flags are only added when the live ``--help`` text advertises them, so newer
or older CLIs degrade gracefully instead of failing on unknown flags.
Capabilities backed only by docs are marked evidence="docs"; everything else
stays unknown until live verification.
"""

from __future__ import annotations

from pathlib import Path

from sklab_agent_adapters.adapters.base import AgentAdapter, AuthResult, ModelsResult
from sklab_agent_adapters.adapters.registry import register_adapter
from sklab_agent_adapters.core.capabilities import Capability, CapabilityInfo, cap
from sklab_agent_adapters.core.models import AgentRunRequest, AuthState


@register_adapter
class OpenCodeAdapter(AgentAdapter):
    agent_id = "opencode"
    display_name = "OpenCode"
    homepage = "https://github.com/sst/opencode"
    executable_candidates = ["opencode", "opencode.exe", "opencode.cmd"]
    known_versions = ()
    native_install_hint = (
        "Install OpenCode (https://opencode.ai), then `opencode auth login`."
    )

    _help_cache: str | None = None

    def _help(self) -> str:
        if self._help_cache is None:
            self._help_cache = self.help_text() or ""
        return self._help_cache

    def _supports(self, *flags: str) -> bool:
        text = self._help().lower()
        return any(f.lower() in text for f in flags)

    def get_capabilities(self) -> dict[Capability, CapabilityInfo]:
        pending = "opencode CLI not installed at build time; live verification pending"
        caps: dict[Capability, CapabilityInfo] = {
            c: cap(None, "unverified", pending) for c in Capability
        }
        caps[Capability.NON_INTERACTIVE] = cap(
            True, "docs", "`opencode run` executes a task non-interactively; live check pending")
        caps[Capability.PATCH_OUTPUT] = cap(
            True, "adapter", "captured by SKLab git-diff layer post-run")
        if self._help():
            if self._supports("--model"):
                caps[Capability.MODEL_SELECTION] = cap(True, "cli_help", "--model advertised")
            if self._supports("--session", "--continue", "resume"):
                caps[Capability.SESSION_RESUME] = cap(True, "cli_help", "session flag advertised")
            if self._supports("--format json", "json"):
                caps[Capability.JSON_OUTPUT] = cap(True, "cli_help", "json flag advertised")
        return caps

    def get_auth_status(self) -> AuthResult:
        if "auth" in self._help().lower():
            try:
                run = self._run_probe(["auth", "status"], timeout=30)
            except Exception:
                try:
                    run = self._run_probe(["auth"], timeout=30)
                except Exception:
                    return AuthResult(self.agent_id, AuthState.AUTH_UNKNOWN, "auth probe failed")
            blob = ((run.stdout or "") + "\n" + (run.stderr or "")).lower()
            if any(s in blob for s in ("logged in", "authenticated", "ready", "active")):
                return AuthResult(self.agent_id, AuthState.READY, "native auth reported active")
            if any(s in blob for s in ("not logged in", "not authenticated", "no auth", "missing")):
                return AuthResult(self.agent_id, AuthState.NOT_AUTHENTICATED,
                                  "native auth not present", login_hint="opencode auth login")
        return AuthResult(self.agent_id, AuthState.AUTH_UNKNOWN,
                          "opencode CLI not verified; respect Zen/Go/free-model quotas")

    def list_models(self) -> ModelsResult:
        return ModelsResult(self.agent_id, "unknown",
                            detail="no verified machine-readable model list; live check pending")

    def build_argv(
        self, request: AgentRunRequest, executable: str, workspace: Path
    ) -> tuple[list[str], list[str]]:
        from sklab_agent_adapters.core.errors import AdapterError, ErrorCode
        from sklab_agent_adapters.core.redaction import collect_sensitive_values, redact_text

        if not request.instruction.strip():
            raise AdapterError(ErrorCode.INVALID_CONFIGURATION, "opencode requires --instruction")
        argv = [executable, "run", request.instruction]
        if request.model and self._supports("--model"):
            argv += ["--model", request.model]
        session_flags = ("--continue", "--session", "--resume")
        if request.resume and request.session_id and self._supports(*session_flags):
            if self._supports("--session"):
                argv += ["--session", request.session_id]
            elif self._supports("--continue"):
                argv += ["--continue", request.session_id]
        elif request.session_id and self._supports("--session"):
            argv += ["--session", request.session_id]
        argv.extend(request.extra_args)
        sensitive = collect_sensitive_values(dict(request.environment or {}))
        return argv, [redact_text(a, sensitive) for a in argv]
