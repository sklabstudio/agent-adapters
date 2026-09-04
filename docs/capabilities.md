# Capabilities

19 normalized capabilities: `FILES_READ, FILES_WRITE, SHELL, GIT, MCP, SKILLS,
SUBAGENTS, SESSION_RESUME, NON_INTERACTIVE, STREAMING, JSON_OUTPUT,
MODEL_SELECTION, CONTEXT_FILE, TASK_FILE, PATCH_OUTPUT, TOKEN_USAGE,
COST_USAGE, WEB_ACCESS, IMAGE_INPUT`.

Each entry:

```json
{"supported": true, "state": "true", "evidence": "cli_help",
 "notes": "-z/--oneshot documented for scripts/pipes", "minimum_version": null}
```

`supported` is `true` / `false` / `null` (unknown). Evidence values:
`cli_help` (verified flag text), `live_probe` (ran a safe subcommand),
`docs` (public docs, live check pending), `config` (custom command
declaration), `adapter` (provided by the SKLab layer itself, e.g. patch
capture), `unverified`.

## Matrix at v0.1.0 (abridged)

True for Hermes: FILES_READ/WRITE, SHELL, GIT, MCP, SKILLS, SESSION_RESUME,
NON_INTERACTIVE, MODEL_SELECTION, PATCH_OUTPUT(adapter), TOKEN_USAGE,
COST_USAGE (--usage-file).

True for Codex: FILES_READ/WRITE, SHELL, MCP, SESSION_RESUME,
NON_INTERACTIVE, STREAMING, JSON_OUTPUT, MODEL_SELECTION, IMAGE_INPUT,
PATCH_OUTPUT(adapter).

True for Claude: FILES_READ/WRITE, SHELL, GIT, MCP, SKILLS, SUBAGENTS,
SESSION_RESUME, NON_INTERACTIVE, STREAMING, JSON_OUTPUT, MODEL_SELECTION,
TOKEN_USAGE(docs), COST_USAGE(docs), PATCH_OUTPUT(adapter).

Generic command: whatever `sklab-agents.yaml` declares; undeclared is unknown.

Zero / OpenCode / Gemini: unknown except PATCH_OUTPUT(adapter) and
NON_INTERACTIVE(docs) for OpenCode/Gemini — live verification pending.

## Orchestrator queries

```python
from sklab_agent_adapters.adapters.registry import find_by_capabilities
agents = find_by_capabilities(["FILES_WRITE", "SHELL", "NON_INTERACTIVE"])
```

```bash
sklab-agents find FILES_WRITE,SHELL,NON_INTERACTIVE --json
```
