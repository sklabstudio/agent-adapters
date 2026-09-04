# Adapters

## Hermes (verified v0.20.3, live 2026-09-04)

- Detect: `hermes --version` → `0.20.3`.
- Run: `hermes -z "<instruction>" --in <workspace> [-m model]
  [--usage-file <tmp>] [--resume <session>]`.
- Usage sidecar `--usage-file` is always attached by the adapter and parsed
  into `token_usage`/`cost_usage`, then deleted.
- Auth: `hermes status` parsed for ready providers.
- Never modifies the Hermes installation; adapter layer only.

## Codex CLI (verified v0.147.0, live 2026-09-04)

- Run: `codex exec "<instruction>" -C <workspace> --skip-git-repo-check
  [-m model] [--json when streaming]`.
- Resume: `codex exec resume <id>`.
- Auth: `codex login status` (ChatGPT login observed READY).
- Sessions/usage parsed best-effort from `--json` JSONL events.

## Claude Code (verified help v2.1.198, live 2026-09-04)

- Run: `claude -p "<instruction>" --output-format <json|stream-json>
  [--model m] [--resume id | --session-id uuid]`.
- The adapter defaults to machine-readable output unless the caller passes
  their own `--output-format` via `--extra`.
- `session_id`, `usage`, `total_cost_usd` parsed from the result envelope.
- No paid call was made for verification; usage/cost mapping is evidence
  `docs` + fixture-tested.

## Zero (provisional)

CLI not installed at build time. Detection/version probes are generic;
run argv is chosen by inspecting `--help` (`run` subcommand, workspace/model/
session flags). Capabilities unknown; live verification pending.

## OpenCode (provisional)

CLI not installed. Uses documented `opencode run "<message>"` shape, with
`--model`/`--session`/`--continue` added only when advertised. Quotas
(Zen/Go/free-model) are never bypassed; no multi-account logic exists.

## Gemini CLI (provisional)

CLI not installed. Uses documented `-p/--prompt` shape with `--model` /
`--resume` added only when advertised. Official auth only.

## Generic Command (fully supported)

Explicit argv template + declared capabilities from `sklab-agents.yaml`.
Placeholders: `{workspace} {instruction} {task_file} {context_file} {model}
{session_id}`. Unknown placeholders are a hard error. Env and extra args are
appended safely (arrays, never shell).
