# Authentication

SKLab Agent Adapters use **official/native authentication only**.

Allowed:

- already-authenticated native CLI (`codex login` done by the user, Hermes
  API keys configured via `hermes model`, etc.)
- official API-key environment/config mechanisms
- official device/browser login initiated by the native CLI

Never:

- asking for account passwords
- scraping browser cookies or copying consumer web-session tokens
- bypassing MFA or provider usage limits
- rotating/revoking credentials automatically
- multi-account quota evasion (no Zen/Go limit games with OpenCode)

## Behavior

`sklab-agents auth <agent>` inspects status (read-only) and returns one of
`READY / NOT_AUTHENTICATED / AUTH_REQUIRED / EXPIRED_OR_INVALID /
AUTH_UNKNOWN / UNSUPPORTED` plus a `login_hint` naming the official command.

- Hermes: parses `hermes status` (✓ markers) — live-verified READY via
  OpenRouter key on the build machine.
- Codex: parses `codex login status` — live-verified READY (ChatGPT login).
- Claude: probes `claude auth status`, degrades to `AUTH_UNKNOWN` rather than
  misparse (no verified machine-readable flag).
- OpenCode: probes `auth status` only if `--help` advertises `auth`.
- Zero/Gemini/generic: `AUTH_UNKNOWN`/`UNSUPPORTED` until verified.

`auth <agent> --login` exists but every adapter rejects it in v0.1.0 unless a
verified non-interactive official flow exists — interactive logins must be
performed by the human in the native CLI.

No credential vault is built here; the future Provider Connections layer owns
encrypted secret storage.
