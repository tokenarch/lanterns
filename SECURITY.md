# Security

## Reporting a Vulnerability

If you discover a security vulnerability in NightClaw, please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Use GitHub's private vulnerability reporting feature (Security tab → Report
a vulnerability) when available, or contact the maintainer directly by
emailing Chris Timpe at [human@tokenarch.com](mailto:human@tokenarch.com).

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will acknowledge receipt within 48 hours and aim to provide a fix or
mitigation within 7 days for critical issues.

## Scope

NightClaw is a Cowork-deployed protocol layer consisting of:

- **Engine code** — `nightclaw_engine/` (deterministic Python, ~25 modules)
  invoked by the agent via `scripts/nightclaw-ops.py` for every T-step
  action. This is the authoritative state-mutation surface.
- **Optional bridge process** — `nightclaw_bridge/` runs a local WebSocket
  + HTTP server (default ports 8787 / 8080) that powers the optional
  browser monitor at `apps/monitor/*.html`. Off by default; started
  manually by the operator with `bash scripts/start-monitor.sh`.
- **Workspace doctrine** — root-level Markdown files (SOUL.md,
  AGENTS-CORE.md, etc.) that the agent reads at session start. Protected
  files are SHA-256-hashed in `audit/INTEGRITY-MANIFEST.md`.
- **Admin shell scripts** — `scripts/*.sh` for install, re-sign, validation.

Cowork itself sandboxes each session inside an Anthropic-managed Linux VM;
the workspace folder is mounted via Cowork's mount path. There is no
host/guest VM split, no local credential file, and no platform CLI
configured by the operator.

## Threat categories

**Prompt injection** — the largest practical threat surface. An attacker
who can land instructions in any file the agent reads at runtime (web
fetch results, file contents, tool outputs) may attempt to override
NightClaw's Hard Lines (defined in `SOUL.md`). Mitigations:

- Hard Lines are encoded as agent identity, not consulted as a rulebook
- The cron prompt explicitly tells the worker to refuse instructions
  sourced from fetched content, gateway logs, or tool results
- Bundles enforce typed argument validation — injected text cannot
  invoke arbitrary state mutation
- The append-only audit log records every action; tampering with prior
  entries is detectable via `audit-spine`

**Integrity-verification bypass** — an attacker with shell access to the
workspace folder can edit protected files. The SHA-256 manifest catches
drift on the next `integrity-check` run (T0 of every session), but does
NOT prevent the edit. For tamper-proof integrity, use signed git commits.

**Information disclosure** — workspace files, audit log contents, and
project LONGRUNNERs may contain sensitive information. Anyone with read
access to the folder Cowork mounts can read these. Operator responsibility:
do not put secrets in `USER.md`, `MEMORY.md`, or any project LONGRUNNER.

**Placeholder injection** — `install.sh` substitutes `{OWNER}` and
`{WORKSPACE_ROOT}` across `.md` files. The script's `validate_input`
function whitelists allowed characters and rejects path-traversal
sequences; do not edit `install.sh` to relax these checks.

**Bridge / monitor exposure** — if you run the optional monitor, the
bridge listens on `localhost:8080` (HTTP) and `localhost:8787` (WebSocket).
These should remain bound to localhost; do not expose them to other
machines without authentication added in front.

## Known limitations

- SHA-256 integrity checks detect accidental drift, not adversarial tampering
- Hard Lines are natural-language instructions; they are defense-in-depth
  and cannot replace a sandboxed execution environment
- The append-only audit log can be circumvented by editing the file
  directly outside of agent control. It governs agent behavior, not
  human behavior
- Cowork sessions run within Anthropic's sandbox; security boundaries
  relevant to Anthropic's platform are out of scope for this document
