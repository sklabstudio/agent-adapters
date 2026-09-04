"""Filtered subprocess environment: explicit allowlist, no full-env serialization."""

from __future__ import annotations

import os

# Safe-to-inherit, non-secret variable names. Everything else must be
# passed explicitly per-run via AgentRunRequest.environment. Home/config
# paths are included because native CLIs need them to locate their own
# auth state — they carry no credentials themselves.
SAFE_INHERIT = frozenset(
    {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "TEMP",
        "TMP",
        "HOME",
        "USER",
        "USERNAME",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "APPDATA",
        "LOCALAPPDATA",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_CACHE_HOME",
        "XDG_STATE_HOME",
        "LANG",
        "LC_ALL",
        "TERM",
        "SHELL",
        "EDITOR",
        "NO_COLOR",
        "CLICOLOR",
        "PYTHONIOENCODING",
        "PYTHONUTF8",
        "CODEX_HOME",
        "CLAUDE_CONFIG_DIR",
        "GEMINI_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    }
)


def build_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Build a filtered child environment.

    Inherits only SAFE_INHERIT names from the host, then overlays explicit
    per-run variables (which win). Never serializes the full host env.
    """
    env: dict[str, str] = {}
    for name in SAFE_INHERIT:
        val = os.environ.get(name)
        if val is not None:
            env[name] = val
    # PATH must always exist for executable resolution.
    if "PATH" not in env and os.environ.get("PATH"):
        env["PATH"] = os.environ["PATH"]
    if extra:
        env.update(extra)
    return env
