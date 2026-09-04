# Demo

```bash
# 1. What agents are available?
sklab-agents detect

# 2. Inspect one
sklab-agents show hermes
sklab-agents capabilities codex --required SHELL,NON_INTERACTIVE

# 3. Dry-run (nothing launches)
sklab-agents run hermes --workspace ./repo \
  --instruction "Fix the failing test" --dry-run

# 4. Real run with patch capture
sklab-agents run hermes --workspace ./repo \
  --instruction "Fix the failing test" \
  --patch-out ./fix.patch --json > result.json

# 5. Stream structured events
sklab-agents run codex --workspace ./repo \
  --instruction "Add input validation" --jsonl

# 6. Resume a native session
sklab-agents run claude --workspace ./repo --instruction "Continue" \
  --session-id <id> --resume --json

# 7. Custom agent via generic adapter (sklab-agents.yaml)
sklab-agents run my-agent --workspace ./repo --instruction "Triage" --json

# 8. Health + cleanup
sklab-agents doctor
sklab-agents clean --workspace ./repo --dry-run
```
