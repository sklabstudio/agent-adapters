# Architecture

```
CLI (Typer) ──> adapters/* ──> execution/runner ──> subprocess (argv, no shell)
     │               │                │
     │               │                ├── environment (filtered env)
     │               │                ├── process_tree (owned-group cleanup)
     │               │                └── streaming (normalized events)
     │               │
     │               ├── detection (which / version / compatibility)
     │               ├── workspace (validate / git baseline / patch capture)
     │               └── core (models / capabilities / config / redaction)
     └── reports (JSON)
```

## Layers

- **core/models**: `AgentRunRequest`, `AgentRunResult` (schema_version 1),
  `RunStatus`, `AuthState`, `Compatibility`, usage/session models.
- **core/capabilities**: 19-entry `Capability` enum; each entry carries
  `supported` (true/false/None=unknown), `evidence`, `notes`,
  `minimum_version`. `find_by_capabilities` lets the future Orchestrator query
  by requirements instead of agent names.
- **adapters/base**: normalized lifecycle — `detect`, `get_version` (via
  probe), `get_capabilities`, `get_auth_status`, `list_models`,
  `prepare_run` (dry-run), `run`, `cancel` (via `Cancellation` flag),
  `resume`, `collect_result` (the `AgentRunResult`), `healthcheck`.
  Unsupported operations raise `CAPABILITY_UNSUPPORTED`; nothing is faked.
- **execution/runner**: argv arrays only; per-run filtered env; timeout;
  cooperative cancel; stdout/stderr capture with byte-bound truncation;
  secret redaction before persistence; owned process-group termination
  (POSIX `killpg`, Windows process-group + scoped `taskkill /PID /T`).
  `.cmd/.bat` shims are routed through `cmd.exe /d /c` with argv preserved.
- **workspace**: canonicalization + root/home guards; read-only git baseline
  (`rev-parse`, `status --porcelain`); patch capture (`git diff HEAD` with
  control-file pathspec exclusion + `/dev/null` diffs for untracked files;
  SHA-256 fingerprint). Never `reset`/`clean`/`checkout`/commit.
- **detection**: `shutil.which` or explicit configured path only; version
  probes (`--version` variants); `SUPPORTED / SUPPORTED_WITH_WARNINGS /
  UNKNOWN_VERSION / TOO_OLD / UNAVAILABLE` — newer-than-known versions warn
  instead of claiming full support.
- **reports**: JSON writers; callers pass already-redacted data.

## Data flow of `run`

1. Validate workspace + task/context files.
2. `detect()` executable + version + compatibility.
3. Record git baseline (HEAD, dirty flag) — read-only.
4. Adapter builds argv array (+ redacted twin for display).
5. Runner executes with timeout/cancel, redacts, truncates, cleans up tree.
6. Patch capture vs baseline; fingerprint; control files excluded.
7. Auth-failure sniffing maps known markers to `AUTH_REQUIRED`.
8. `AgentRunResult` assembled; adapter `_enrich_result` hook parses sidecars
   (e.g. Hermes `--usage-file`, Claude `--output-format json`).

Execution success is NOT code-quality success — PatchBench owns verification.
