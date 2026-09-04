# Integrations

## ReproBox

ReproBox provides isolated workspaces; this layer accepts any workspace path
and preserves environment metadata in `AgentRunRequest.metadata`. Run fixture
agents inside ReproBox-controlled directories exactly like normal runs:

```bash
sklab-agents run fake --workspace <reprobox-workspace> --instruction "..." --json
```

Status at v0.1.0: interface-compatible by design (workspace + filtered env +
no paid calls). A live ReproBox joint run is pending operator setup and is
tracked in `docs/progress.md`. The ReproBox repo is never modified by this
project.

## CodeTrials

CodeTrials can shell out to the stable invocation:

```bash
sklab-agents run <agent> --workspace <trial-repo> --instruction "<task>" \
  --patch-out result.patch --json
```

The same normalized envelope represents every agent, so trial harnesses never
hardcode agent CLIs. No CodeTrials changes required.

## PatchBench

After a run, PatchBench consumes `patch_path`, `patch_fingerprint`, and
`workspace` from the result JSON. Scoring/verifier logic is not duplicated
here. A controlled fixture integration (fake agent → patch → PatchBench
shape) is exercised in the dogfood test; a live PatchBench run is pending
and tracked in `docs/progress.md`.

## RepoContext

Pass `--context-file <file>`; adapters deliver context through native
mechanisms where verified, otherwise it stays available for deterministic
prompt composition by the caller. RepoContext is never auto-executed here.

## PromptBench

PromptBench can use the identical stable `sklab-agents run … --json`
invocation across agents for comparable trials. No PromptBench changes made.
