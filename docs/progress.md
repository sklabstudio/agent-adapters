# Progress

Live build log for v0.1.0 (overnight-execution checkpoint file).

## 2026-09-04 — build

- [x] Scaffolded repo, core models/capabilities/registry/config
- [x] Execution (runner/streaming/timeout/env/process-tree) + workspace/patch
- [x] GenericCommandAdapter (placeholders, strict rejection)
- [x] Hermes adapter (verified v0.20.3 live: help/version/status)
- [x] Codex adapter (verified v0.147.0 live: help/exec/login status)
- [x] Claude adapter (verified help v2.1.198 live)
- [x] Zero/OpenCode/Gemini provisional adapters (help-probed, pending live)
- [x] CLI: version/list/detect/show/capabilities/auth/models/run/find/doctor/clean/sessions
- [x] Fixture agent framework (13 modes) + fixtures (live + synthetic)
- [x] Unit + integration tests incl. dogfood
- [x] Docs (9 files) + README + CI + packaging
- [x] Full quality gate (pytest/ruff/mypy/build/wheel smoke) — green locally
  - pytest: 80 passed; ruff: clean; mypy: clean; build + wheel smoke: ok
- [x] Fixture dogfood via installed CLI — SUCCESS, patch+fingerprint verified,
  dirty/untracked preserved, no secret leakage
- [x] Zero-cost live detection: hermes 0.20.3 SUPPORTED/auth READY,
  codex 0.147.0 SUPPORTED/auth READY, claude 2.1.198 SUPPORTED/auth UNKNOWN
  (honest); zero/opencode/gemini not installed (UNAVAILABLE, pending)
- [x] Live inference NOT run (paid) — reported as LIVE_INFERENCE_NOT_RUN
- [x] Fixed during build: missing child-output pipes; filtered env dropped
  home vars (broke hermes auth probe); duplicate DIRTY warning; CI bash fix
- [ ] ReproBox / CodeTrials / PatchBench joint checks (pending availability)
- [x] GitHub repo created + pushed + Actions green (win/linux/macos)

## Live agent notes (build machine, Windows)

- hermes 0.20.3 installed; `status` shows OpenRouter key READY.
- codex-cli 0.147.0 installed; `login status` = ChatGPT login READY.
- claude 2.1.198 installed; auth status unverified (no machine-readable flag).
- zero / opencode / gemini: not installed → fixture validation only.
- No paid inference will be run for verification (LIVE_INFERENCE_NOT_RUN).
