# Changelog

## 0.1.0 (2026-09-04)

Initial release — SKLab Agent Adapters, integration-verified.

- Normalized `AgentAdapter` interface (detect/version/capabilities/auth/models/run/resume/health)
- Adapters: Hermes (verified v0.20.3), Codex CLI (verified v0.147.0),
  Claude Code (verified v2.1.198), Generic Command (full), Zero / OpenCode /
  Gemini CLI (provisional, help-probed, live verification pending)
- Capability matrix with explicit true/false/unknown + evidence
- Safe subprocess execution: argv arrays, filtered env, timeout, cooperative
  cancel, owned-process-group cleanup (Windows `.cmd` shim routing included)
- Workspace confinement, read-only git baseline, patch capture with SHA-256
  fingerprint, control-file exclusion
- Streaming events + JSONL, `--dry-run`, `--json` everywhere
- Auth boundary: status inspection only by default; no passwords, cookies, or
  quota bypass
- Secret redaction in all persisted output
- Deterministic Python fixture agents; no paid calls in CI
- Docs: architecture, capabilities, authentication, adapters,
  adding-an-adapter, security, integrations, demo, progress
