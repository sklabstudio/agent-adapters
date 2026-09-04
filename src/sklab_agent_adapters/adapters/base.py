"""AgentAdapter base: normalized detect/version/caps/auth/models/run/resume/health."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from sklab_agent_adapters.core.capabilities import Capability, CapabilityInfo
from sklab_agent_adapters.core.errors import AdapterError, ErrorCode
from sklab_agent_adapters.core.models import (
    AgentRunRequest,
    AgentRunResult,
    AuthState,
    Compatibility,
    RunStatus,
    SessionInfo,
    utcnow_iso,
)
from sklab_agent_adapters.core.redaction import collect_sensitive_values, redact_text
from sklab_agent_adapters.detection.compatibility import classify as classify_version
from sklab_agent_adapters.detection.executables import ExecutableInfo, resolve_executable
from sklab_agent_adapters.detection.versions import ParsedVersion, parse_version_output
from sklab_agent_adapters.execution.runner import Cancellation, CompletedRun, RunSpec, execute
from sklab_agent_adapters.workspace import control_files as ws_control
from sklab_agent_adapters.workspace.git import baseline as git_baseline
from sklab_agent_adapters.workspace.patch import capture_patch


@dataclass
class DetectionResult:
    agent_id: str
    installed: bool
    executable: str | None
    executable_source: str
    version_raw: str | None
    version: str | None
    compatibility: Compatibility
    warnings: list[str] = field(default_factory=list)


@dataclass
class AuthResult:
    agent_id: str
    state: AuthState
    detail: str = ""
    login_hint: str | None = None


@dataclass
class ModelsResult:
    agent_id: str
    state: str  # "list" | "unknown" | "unsupported"
    models: list[str] = field(default_factory=list)
    detail: str = ""


class AgentAdapter(ABC):
    """Normalized interface every agent adapter implements.

    Unsupported operations must raise AdapterError(CAPABILITY_UNSUPPORTED) —
    never fake support.
    """

    agent_id: str = "unknown"
    display_name: str = "Unknown"
    homepage: str = ""
    executable_candidates: ClassVar[list[str]] = []
    known_versions: tuple[str, ...] = ()
    minimum_version: str | None = None
    supported_platforms: tuple[str, ...] = ("windows", "linux", "darwin")
    native_install_hint: str = ""

    def __init__(self, *, executable: str | None = None, max_log_bytes: int = 1048576) -> None:
        self._explicit_executable = executable
        self._max_log_bytes = max_log_bytes

    # -- identity -----------------------------------------------------
    def metadata(self) -> dict[str, Any]:
        detection = self.detect()
        return {
            "adapter_id": self.agent_id,
            "display_name": self.display_name,
            "homepage": self.homepage,
            "installation_status": (
                "installed" if detection.installed else "not_installed"
            ),
            "supported_platforms": list(self.supported_platforms),
            "minimum_version": self.minimum_version,
            "native_install_hint": self.native_install_hint,
            "detected_version": detection.version,
            "compatibility": detection.compatibility.value,
        }

    # -- detection ----------------------------------------------------
    def resolve(self) -> ExecutableInfo:
        return resolve_executable(
            list(self.executable_candidates), explicit=self._explicit_executable
        )

    def _run_probe(
        self, argv: list[str], *, timeout: int = 30, cwd: str | None = None
    ) -> CompletedRun:
        info = self.resolve()
        if not info.found or not info.path:
            raise AdapterError(
                ErrorCode.EXECUTABLE_NOT_FOUND, f"{self.agent_id} executable not found")
        spec = RunSpec(
            argv=[info.path, *argv],
            cwd=cwd or str(Path.cwd()),
            timeout_seconds=timeout,
            max_log_bytes=self._max_log_bytes,
        )
        return execute(spec)

    def parse_version(self, text: str) -> ParsedVersion:
        return parse_version_output(text, known_versions=self.known_versions)

    def detect(self) -> DetectionResult:
        info = self.resolve()
        warnings = list(info.warnings)
        if not info.found or not info.path:
            return DetectionResult(
                agent_id=self.agent_id,
                installed=False,
                executable=None,
                executable_source="missing",
                version_raw=None,
                version=None,
                compatibility=Compatibility.UNAVAILABLE,
                warnings=warnings,
            )
        version_text = self._probe_version_text()
        parsed = self.parse_version(version_text or "")
        compat = classify_version(
            parsed, installed=True, minimum_version=self.minimum_version
        )
        if compat == Compatibility.SUPPORTED_WITH_WARNINGS:
            warnings.append(
                f"untested {self.agent_id} version {parsed.normalized}; may differ")
        elif compat == Compatibility.UNKNOWN_VERSION:
            warnings.append(f"could not confirm {self.agent_id} version compatibility")
        return DetectionResult(
            agent_id=self.agent_id,
            installed=True,
            executable=info.path,
            executable_source=info.source,
            version_raw=(version_text or "").strip() or None,
            version=parsed.normalized,
            compatibility=compat,
            warnings=warnings,
        )

    def _probe_version_text(self) -> str | None:
        for args in self.version_argv_options():
            try:
                run = self._run_probe(list(args), timeout=30)
            except AdapterError:
                continue
            text = ((run.stdout or "") + "\n" + (run.stderr or "")).strip()
            if text:
                return text
        return None

    def version_argv_options(self) -> list[tuple[str, ...]]:
        return [("--version",)]

    def help_text(self) -> str | None:
        try:
            run = self._run_probe(["--help"], timeout=30)
        except AdapterError:
            return None
        text = ((run.stdout or "") + "\n" + (run.stderr or "")).strip()
        return text or None

    # -- capabilities / auth / models ---------------------------------
    @abstractmethod
    def get_capabilities(self) -> dict[Capability, CapabilityInfo]:
        ...

    def get_auth_status(self) -> AuthResult:
        return AuthResult(
            agent_id=self.agent_id, state=AuthState.AUTH_UNKNOWN, detail="not implemented"
        )

    def login(self) -> AuthResult:
        raise AdapterError(
            ErrorCode.CAPABILITY_UNSUPPORTED,
            f"{self.agent_id} has no verified official non-interactive login flow in v0.1.0",
        )

    def list_models(self) -> ModelsResult:
        return ModelsResult(agent_id=self.agent_id, state="unknown", detail="not verified")

    def healthcheck(self) -> dict[str, Any]:
        """Zero-cost checks only: executable, version, compatibility, auth hint."""
        detection = self.detect()
        try:
            auth = self.get_auth_status()
            auth_state = auth.state.value
            auth_detail = redact_text(auth.detail, collect_sensitive_values())
        except AdapterError as exc:
            auth_state, auth_detail = AuthState.AUTH_UNKNOWN.value, exc.message
        return {
            "agent_id": self.agent_id,
            "installed": detection.installed,
            "executable": detection.executable,
            "version": detection.version,
            "compatibility": detection.compatibility.value,
            "auth_state": auth_state,
            "auth_detail": auth_detail,
            "warnings": detection.warnings,
        }

    def list_sessions(self) -> list[SessionInfo]:
        raise AdapterError(
            ErrorCode.CAPABILITY_UNSUPPORTED,
            f"{self.agent_id} session listing is not supported by this adapter",
        )

    # -- run ----------------------------------------------------------
    def validate_request(self, request: AgentRunRequest) -> Path:
        try:
            workspace = ws_control.validate_workspace(request.workspace)
        except AdapterError:
            raise
        ws_control.validate_optional_file(request.task_file, label="task_file")
        ws_control.validate_optional_file(request.context_file, label="context_file")
        if not request.instruction.strip() and request.task_file is None:
            raise AdapterError(
                ErrorCode.INVALID_CONFIGURATION,
                "provide --instruction or --task-file (one is required)",
            )
        return workspace

    @abstractmethod
    def build_argv(
        self, request: AgentRunRequest, executable: str, workspace: Path
    ) -> tuple[list[str], list[str]]:
        """Return (argv, redacted_argv). Must use argument arrays, never shell."""

    def prepare_run(self, request: AgentRunRequest) -> dict[str, Any]:
        """Dry-run view: resolved executable, redacted argv, workspace, caps used."""
        workspace = self.validate_request(request)
        detection = self.detect()
        if not detection.installed or not detection.executable:
            raise AdapterError(
                ErrorCode.EXECUTABLE_NOT_FOUND, f"{self.agent_id} executable not found"
            )
        argv, redacted = self.build_argv(request, detection.executable, workspace)
        caps = self.get_capabilities()
        return {
            "agent_id": self.agent_id,
            "executable": detection.executable,
            "argv": redacted,
            "workspace": str(workspace),
            "timeout_seconds": request.timeout_seconds,
            "environment_variable_names": sorted((request.environment or {}).keys()),
            "capabilities_used": sorted(c.value for c, i in caps.items() if i.supported),
            "output_mode": "stream-jsonl" if request.stream else "captured",
            "version": detection.version,
            "compatibility": detection.compatibility.value,
        }

    def run(
        self,
        request: AgentRunRequest,
        *,
        cancel: Cancellation | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> AgentRunResult:
        workspace = self.validate_request(request)
        detection = self.detect()
        if not detection.installed or not detection.executable:
            return self._terminal_result(
                request, workspace, detection, RunStatus.UNAVAILABLE,
                ErrorCode.EXECUTABLE_NOT_FOUND, f"{self.agent_id} executable not found",
            )
        base = git_baseline(workspace)
        started = utcnow_iso()
        import time as _time

        t0 = _time.monotonic()
        self._pre_run(request, workspace)
        try:
            argv, redacted = self.build_argv(request, detection.executable, workspace)
        except AdapterError as exc:
            elapsed = int((_time.monotonic() - t0) * 1000)
            return self._terminal_result(
                request, workspace, detection, RunStatus.UNSUPPORTED,
                exc.code, exc.message, started=started, duration_ms=elapsed,
            )
        spec = RunSpec(
            argv=argv,
            cwd=str(workspace),
            env_extra=dict(request.environment or {}),
            timeout_seconds=request.timeout_seconds,
            max_log_bytes=self._max_log_bytes,
            redacted_argv=redacted,
        )
        completed = execute(spec, cancel=cancel, on_event=on_event)
        duration_ms = int((_time.monotonic() - t0) * 1000)
        patch_out = (request.metadata or {}).get("patch_out")
        patch = capture_patch(workspace, dirty_before=base.dirty, out_path=patch_out)
        warnings = list(detection.warnings)
        warnings.extend(patch.notes)

        if completed.cancelled:
            status, code = RunStatus.CANCELLED, ErrorCode.CANCELLED
        elif completed.timed_out:
            status, code = RunStatus.TIMEOUT, ErrorCode.TIMEOUT
        elif completed.exit_code == 0:
            status, code = RunStatus.SUCCESS, None
            if self._looks_like_auth_failure(completed.stdout, completed.stderr):
                status, code = RunStatus.AUTH_REQUIRED, ErrorCode.AUTH_REQUIRED
        else:
            if self._looks_like_auth_failure(completed.stdout, completed.stderr):
                status, code = RunStatus.AUTH_REQUIRED, ErrorCode.AUTH_REQUIRED
            else:
                status, code = RunStatus.AGENT_FAILED, ErrorCode.PROCESS_FAILED

        error = None
        if code is not None:
            error = {"code": code, "message": self._short_error(completed, code)}
        found_session = self.extract_session(completed.stdout, completed.stderr)
        usage_tokens, usage_cost = self.extract_usage(completed.stdout, completed.stderr)
        result = AgentRunResult(
            agent_id=self.agent_id,
            agent_version=detection.version,
            status=status,
            started_at=started,
            finished_at=utcnow_iso(),
            duration_ms=duration_ms,
            exit_code=completed.exit_code,
            stdout=completed.stdout,
            stderr=completed.stderr,
            stdout_truncated=completed.stdout_truncated,
            stderr_truncated=completed.stderr_truncated,
            workspace=str(workspace),
            session_id=request.session_id or found_session,
            resumable=self.supports_resume() and bool(request.session_id or found_session),
            patch_path=patch.patch_path,
            patch_fingerprint=patch.fingerprint,
            changed_files=patch.changed_files,
            token_usage=usage_tokens,
            cost_usage=usage_cost,
            model=request.model,
            warnings=warnings,
            error=error,
        )
        return self._enrich_result(request, result)

    def resume(
        self,
        request: AgentRunRequest,
        *,
        cancel: Cancellation | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> AgentRunResult:
        if not self.supports_resume():
            raise AdapterError(
                ErrorCode.CAPABILITY_UNSUPPORTED,
                f"{self.agent_id} does not support native session resume",
            )
        if not request.session_id:
            raise AdapterError(ErrorCode.SESSION_NOT_FOUND, "resume requires a session_id")
        resumed = request.model_copy(update={"resume": True})
        return self.run(resumed, cancel=cancel, on_event=on_event)

    # -- hooks for subclasses -----------------------------------------
    def _pre_run(self, request: AgentRunRequest, workspace: Path) -> None:  # noqa: B027
        """Optional per-adapter setup before argv construction (e.g. temp files)."""

    def _enrich_result(
        self, request: AgentRunRequest, result: AgentRunResult
    ) -> AgentRunResult:
        """Optional post-run enrichment (e.g. parse sidecar usage reports)."""
        return result

    def supports_resume(self) -> bool:
        caps = self.get_capabilities()
        resume_cap = caps.get(Capability.SESSION_RESUME, None)
        return bool(resume_cap and resume_cap.supported)

    def extract_session(self, stdout: str, stderr: str) -> str | None:
        return None

    def extract_usage(
        self, stdout: str, stderr: str
    ) -> tuple[Any, Any]:
        return None, None

    @staticmethod
    def _looks_like_auth_failure(stdout: str, stderr: str) -> bool:
        blob = f"{stdout}\n{stderr}".lower()
        markers = (
            "not authenticated", "not logged in", "auth required", "authentication required",
            "invalid api key", "incorrect api key", "expired token", "unauthorized",
            "please run", "login required", "no auth", "missing api key", "api key not",
        )
        return any(m in blob for m in markers)

    @staticmethod
    def _short_error(completed: CompletedRun, code: str) -> str:
        tail = (completed.stderr or completed.stdout or "").strip().splitlines()
        tail_text = tail[-1] if tail else f"agent exited with code {completed.exit_code}"
        return f"{code}: {tail_text[:500]}"

    def _terminal_result(
        self,
        request: AgentRunRequest,
        workspace: Path,
        detection: DetectionResult,
        status: RunStatus,
        code: str,
        message: str,
        *,
        started: str | None = None,
        duration_ms: int = 0,
    ) -> AgentRunResult:
        now = utcnow_iso()
        return AgentRunResult(
            agent_id=self.agent_id,
            agent_version=detection.version,
            status=status,
            started_at=started or now,
            finished_at=now,
            duration_ms=duration_ms,
            workspace=str(workspace),
            model=request.model,
            warnings=list(detection.warnings),
            error={"code": code, "message": message},
        )
