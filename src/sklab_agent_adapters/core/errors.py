"""Machine-readable error codes shared by adapters, runner, and CLI."""

from __future__ import annotations


class ErrorCode:
    EXECUTABLE_NOT_FOUND = "EXECUTABLE_NOT_FOUND"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    PROCESS_FAILED = "PROCESS_FAILED"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    WORKSPACE_ERROR = "WORKSPACE_ERROR"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    CAPABILITY_UNSUPPORTED = "CAPABILITY_UNSUPPORTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AdapterError(Exception):
    """Normalized adapter error carrying a machine code and human message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}
