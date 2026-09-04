# Security

- **Agents execute arbitrary code.** Adapters are wrappers, not sandboxes.
  Run untrusted work in ReproBox, a container, or a VM.
- **Native provider auth is the trust boundary.** No password collection, no
  browser-cookie/session harvesting, no MFA or usage-limit bypass, no
  multi-account quota evasion.
- **No destructive git operations.** The adapter never runs `reset`, `clean`,
  `checkout`, or `commit`; dirty workspaces are preserved and reported.
- **No broad process kills.** Timeout/cancel terminate only the owned PID /
  process group — never by executable name.
- **No shell.** All execution uses argv arrays; `.cmd/.bat` shims are routed
  through `cmd.exe /d /c` with argv preserved (Windows only).
- **Secrets never persist.** Known secret values (suspiciously-named env vars
  + per-run env) and generic token shapes are redacted from stdout/stderr,
  logs, reports, metadata, and errors. The full host environment is never
  serialized — only filtered names plus explicit per-run variables reach the
  child. Tests assert fake tokens never appear in outputs.
- **No telemetry.** SKLab adds no network activity; the native agent uses
  only its own configured provider path.
- **Clean is scoped.** `sklab-agents clean` removes only `.sklab-agent-*`
  control files and `sklab-*` temp metadata — never sessions, credentials,
  or user files (dry-run + confirm supported).
