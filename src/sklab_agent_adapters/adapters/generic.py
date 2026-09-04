"""Generic command adapter: safe argv templates with explicit placeholders."""

from __future__ import annotations

import re
from pathlib import Path

from sklab_agent_adapters.adapters.base import (
    AgentAdapter,
    AuthResult,
    DetectionResult,
    ModelsResult,
)
from sklab_agent_adapters.adapters.registry import register_adapter
from sklab_agent_adapters.core.capabilities import Capability, CapabilityInfo, cap
from sklab_agent_adapters.core.errors import AdapterError, ErrorCode
from sklab_agent_adapters.core.models import AgentRunRequest, AuthState

_PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")

SAFE_PLACEHOLDERS = frozenset(
    {"workspace", "instruction", "task_file", "context_file", "model", "session_id"}
)

_CAPABILITY_ALIASES = {
    "files_read": Capability.FILES_READ,
    "files_write": Capability.FILES_WRITE,
    "shell": Capability.SHELL,
    "git": Capability.GIT,
    "mcp": Capability.MCP,
    "skills": Capability.SKILLS,
    "subagents": Capability.SUBAGENTS,
    "session_resume": Capability.SESSION_RESUME,
    "non_interactive": Capability.NON_INTERACTIVE,
    "streaming": Capability.STREAMING,
    "json_output": Capability.JSON_OUTPUT,
    "model_selection": Capability.MODEL_SELECTION,
    "context_file": Capability.CONTEXT_FILE,
    "task_file": Capability.TASK_FILE,
    "patch_output": Capability.PATCH_OUTPUT,
    "token_usage": Capability.TOKEN_USAGE,
    "cost_usage": Capability.COST_USAGE,
    "web_access": Capability.WEB_ACCESS,
    "image_input": Capability.IMAGE_INPUT,
}


@register_adapter
class GenericCommandAdapter(AgentAdapter):
    """Mandatory generic adapter driven by an explicit argv template.

    Example config::

        agents:
          my-agent:
            adapter: command
            command: ["my-agent", "run", "{instruction}"]
            capabilities: {files_write: true, shell: true, non_interactive: true}
    """

    agent_id = "command"
    display_name = "Generic Command Agent"
    homepage = "https://github.com/sklabstudio/agent-adapters"
    executable_candidates = []
    native_install_hint = "Configure `command:` argv template in sklab-agents.yaml."

    def __init__(
        self,
        *,
        executable: str | None = None,
        max_log_bytes: int = 1048576,
        command: list[str] | None = None,
        capabilities: dict[str, bool] | None = None,
    ) -> None:
        super().__init__(executable=executable, max_log_bytes=max_log_bytes)
        self._template = list(command or [])
        self._declared: dict[str, bool] = dict(capabilities or {})

    # -- template -----------------------------------------------------
    def placeholder_values(self, request: AgentRunRequest, workspace: Path) -> dict[str, str]:
        return {
            "workspace": str(workspace),
            "instruction": request.instruction,
            "task_file": str(request.task_file) if request.task_file else "",
            "context_file": str(request.context_file) if request.context_file else "",
            "model": request.model or "",
            "session_id": request.session_id or "",
        }

    def render(self, request: AgentRunRequest, workspace: Path) -> list[str]:
        if not self._template:
            raise AdapterError(
                ErrorCode.INVALID_CONFIGURATION,
                "generic command adapter requires a non-empty `command:` argv template",
            )
        values = self.placeholder_values(request, workspace)
        rendered: list[str] = []
        for token in self._template:
            names = _PLACEHOLDER_RE.findall(token)
            for name in names:
                if name not in SAFE_PLACEHOLDERS:
                    raise AdapterError(
                        ErrorCode.INVALID_CONFIGURATION,
                        f"unknown placeholder {{{name}}}; allowed: {sorted(SAFE_PLACEHOLDERS)}",
                    )
            out = token
            for name in names:
                out = out.replace("{" + name + "}", values[name])
            rendered.append(out)
        if request.extra_args:
            rendered.extend(request.extra_args)
        return rendered

    def build_argv(
        self, request: AgentRunRequest, executable: str, workspace: Path
    ) -> tuple[list[str], list[str]]:
        # Generic adapter ignores PATH-resolved executable: template argv is explicit.
        argv = self.render(request, workspace)
        from sklab_agent_adapters.core.redaction import collect_sensitive_values, redact_text

        sensitive = collect_sensitive_values(dict(request.environment or {}))
        return argv, [redact_text(a, sensitive) for a in argv]

    def detect(self) -> DetectionResult:
        from sklab_agent_adapters.core.models import Compatibility

        if not self._template:
            return DetectionResult(
                agent_id=self.agent_id, installed=False, executable=None,
                executable_source="missing", version_raw=None, version=None,
                compatibility=Compatibility.UNAVAILABLE,
                warnings=["generic adapter needs `command:` configured"],
            )
        return DetectionResult(
            agent_id=self.agent_id, installed=True, executable=self._template[0],
            executable_source="explicit", version_raw=None, version=None,
            compatibility=Compatibility.UNKNOWN_VERSION,
            warnings=["generic adapter version is not probed"],
        )

    def get_capabilities(self) -> dict[Capability, CapabilityInfo]:
        caps: dict[Capability, CapabilityInfo] = {}
        for alias, member in _CAPABILITY_ALIASES.items():
            if alias in self._declared:
                caps[member] = cap(
                    bool(self._declared[alias]),
                    evidence="config",
                    notes="declared in sklab-agents.yaml for the custom command",
                )
            else:
                caps[member] = cap(None, evidence="unverified",
                                   notes="not declared for this custom command")
        # Non-interactive defaults to True only when explicitly declared; else unknown.
        return caps

    def get_auth_status(self) -> AuthResult:
        return AuthResult(agent_id=self.agent_id, state=AuthState.UNSUPPORTED,
                          detail="generic commands expose no auth probe")

    def list_models(self) -> ModelsResult:
        return ModelsResult(agent_id=self.agent_id, state="unsupported",
                            detail="generic commands expose no model list")
