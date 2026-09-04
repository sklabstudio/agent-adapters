# SKLab Agent Adapters

**One normalized interface for coding agents.**

```bash
sklab-agents detect
sklab-agents list
sklab-agents show hermes
sklab-agents run hermes --workspace ./repo --instruction "Fix the failing test"
```

> Different agents. One normalized interface. Explicit capabilities. Native
> authentication. Safe process control. Machine-readable results.

## Why

Every coding agent has its own CLI flags, auth model, session model, and output
shape. SKLab orchestration (and future Web UI / PromptBench / CodeTrials /
PatchBench) needs facts + normalized execution instead of hardcoded agent
names. This package is that connectivity layer: capability-aware,
version-aware, auth-safe, streamable, and testable without paid providers.

This project is **not** a coding agent, a model provider, a credential vault, a
benchmark engine, or a hosted service.

## Supported Agents

| Agent | Status at v0.1.0 | Non-interactive run |
|---|---|---|
| Hermes | verified live (v0.20.3) | `hermes -z … --in DIR` |
| Codex CLI | verified live (v0.147.0) | `codex exec … -C DIR` |
| Claude Code | verified live help (v2.1.198) | `claude -p … --output-format json` |
| Zero | provisional (not installed) | help-probed |
| OpenCode | provisional (not installed) | help-probed `opencode run` |
| Gemini CLI | provisional (not installed) | help-probed `-p/--prompt` |
| Generic command | fully supported | your argv template |

Provisional adapters probe `--help` at runtime and keep capabilities
`unknown` until verified. They never fake support. See `docs/adapters.md`.

## Installation

Requires Python 3.12+.

```bash
pip install sklab-agent-adapters        # from source checkout:
pip install -e .
sklab-agents --version
```

## Quick Start

```bash
sklab-agents detect                    # what is installed?
sklab-agents list
sklab-agents show codex
sklab-agents capabilities claude
sklab-agents auth hermes               # read-only status
sklab-agents run codex -w ./repo -i "Fix the failing test" --dry-run
sklab-agents run codex -w ./repo -i "Fix the failing test" --patch-out fix.patch
sklab-agents doctor
```

All major commands accept `--json` (stdout is valid JSON only; diagnostics go
to stderr). `run` also supports `--stream` and `--jsonl`.

## Capabilities

Each capability is `true` / `false` / `unknown` with evidence — never a guess:

```bash
sklab-agents capabilities hermes --json
sklab-agents find FILES_WRITE,SHELL,NON_INTERACTIVE --json
```

See `docs/capabilities.md`.

## Authentication

Native auth only: already-authenticated CLIs, official env keys, or official
device/browser login started by the native CLI. `sklab-agents auth <agent>`
inspects status; it never asks for passwords, never scrapes cookies, never
bypasses MFA or quotas. See `docs/authentication.md`.

## Running Agents

```bash
sklab-agents run <agent> --workspace ./repo --instruction "..." \
  [--model M] [--timeout 600] [--env KEY=VAL] [--session-id S] [--resume] \
  [--extra FLAG] [--stream] [--jsonl] [--json] [--dry-run] [--patch-out p.patch]
```

Runs are workspace-confined, use argv arrays (never `shell=True`), filtered
environments, timeouts, cooperative cancellation, and post-run git patch
capture with SHA-256 fingerprint. See `docs/architecture.md`.

## Streaming

```bash
sklab-agents run hermes -w ./repo -i "..." --stream        # human progress on stderr
sklab-agents run hermes -w ./repo -i "..." --jsonl         # normalized JSONL on stdout
```

Event types: `RUN_STARTED, STDOUT, STDERR, TOOL_EVENT, SESSION_EVENT,
USAGE_EVENT, RUN_FINISHED, WARNING, ERROR`.

## Sessions

Native resume where the agent supports it (`--session-id` + `--resume`);
otherwise an explicit `CAPABILITY_UNSUPPORTED` — never faked log stitching.

## Patch Capture

After each run SKLab records baseline HEAD, captures `git diff HEAD` plus new
files, excludes `.sklab-agent-*` control files, and fingerprints with SHA-256.
Dirty workspaces are preserved and reported (`DIRTY_WORKSPACE`), never reset.

## Generic Adapter

Wire any CLI in `sklab-agents.yaml`:

```yaml
agents:
  my-agent:
    adapter: command
    command: ["my-agent", "run", "{instruction}"]
    capabilities: {shell: true, files_write: true, non_interactive: true}
```

Placeholders: `{workspace} {instruction} {task_file} {context_file} {model}
{session_id}`. Unknown placeholders fail loudly.

## Security Model

- Adapters are wrappers, **not sandboxes** — agents may execute arbitrary code.
  Use ReproBox/containers/VMs for isolation.
- Native provider auth is the trust boundary; no bypasses, no cookie scraping.
- No destructive git operations, no broad process kills, no full-env logging.
- Secrets are redacted from all persisted output (tested with fake tokens).

See `docs/security.md`.

## Integrations

ReproBox (isolated workspaces), CodeTrials (normalized runs), PatchBench
(patch path + fingerprint), RepoContext (`--context-file`), PromptBench
(stable invocation). See `docs/integrations.md`.

## Adding an Adapter

See `docs/adding-an-adapter.md`.

## Development

```bash
pip install -e . && pip install pytest ruff mypy build
pytest
ruff check .
mypy src
python -m build
```

CI runs ruff + mypy + pytest + build + wheel smoke on Windows/Linux/macOS with
fixture agents only — no real provider keys.

## Limitations

- Zero / OpenCode / Gemini adapters are provisional (CLIs not installed at
  build time); live verification pending.
- `list_models` is honest-but-often-`unknown`: most CLIs expose no
  machine-readable model list.
- Session listing is unsupported in v0.1.0 (`sessions` reports it explicitly).
- No auto-install of agents (future `sklab-stack`); no credential vault
  (future Provider Connections); no Web UI (Python API is ready for it).

## Roadmap

Live verification of provisional adapters, session listing where natively
supported, installer metadata consumption by `sklab-stack`, orchestrator query
patterns, Web UI bindings.

## License

MIT © 2026 SKLab Studio. Agent/provider names remain property of their
owners; no affiliation implied.
