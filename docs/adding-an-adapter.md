# Adding an Adapter

1. Subclass `AgentAdapter` in `src/sklab_agent_adapters/adapters/<name>.py`
   and decorate with `@register_adapter`.
2. Set identity: `agent_id`, `display_name`, `homepage`,
   `executable_candidates`, `known_versions` (pin verified ones),
   `minimum_version` (optional), `native_install_hint`.
3. Declare `get_capabilities()` — every `Capability` must appear; use
   `None` (unknown) instead of guessing, and cite `evidence`.
4. Detection: override `version_argv_options()` if `--version` is wrong;
   `parse_version()` defaults to first `X.Y.Z` match. Keep a fixture sample
   under `tests/fixtures/`.
5. Auth: implement `get_auth_status()` with safe read-only probes; map to
   `AuthState`; provide `login_hint`. Implement `login()` only for verified
   official non-interactive flows.
6. Run mapping: implement `build_argv()` returning `(argv, redacted_argv)`
   as arrays. Add model/session/stream flags only when the caller requests
   them. Prefer help-probing over hardcoding for fast-moving CLIs.
7. Streaming: rely on base `on_event` emission; map structured events with
   `coerce_agent_event` (never invent tool events from prose).
8. Sessions: override `extract_session()`; `supports_resume()` follows the
   `SESSION_RESUME` capability. `resume()` uses native resume or raises
   `CAPABILITY_UNSUPPORTED`.
9. Usage: override `extract_usage()` or the `_enrich_result()` hook; only
   populate from reliable machine-readable sources.
10. Tests: version parser (known/newer/malformed), help fixture, auth
    mapping, capability honesty, command construction, plus a fixture-agent
    run through your adapter if possible.
11. Docs: extend `docs/adapters.md` and the capability matrix; record
    verification state in `docs/progress.md`.
12. Secret safety: never log raw argv/env; redaction is automatic in the
    runner, but keep new probes free of credential handling.
