# TOOL-STATUS.md

<!-- Fast pre-flight reference. ~200 tokens. Read this instead of OPS-TOOL-REGISTRY.md during worker passes. -->
<!-- Update this file whenever OPS-TOOL-REGISTRY.md changes. -->
<!-- Full detail, fallbacks, and approval requirements: OPS-TOOL-REGISTRY.md -->
<!-- Platform: Claude Cowork. Scheduled tasks fire Claude sessions directly. -->

## Quick Status Table

| Tool | Status | Key Constraint |
|------|--------|----------------|
| Web Search | AVAILABLE | Cowork WebSearch tool. Use intentionally — batch related queries. |
| File System (Read) | AVAILABLE | Workspace root: `claude_cowork_workspace/workspace/` |
| File System (Write) | AVAILABLE | Write within workspace only. SOUL.md Hard Lines apply for writes outside project dir. |
| Python / Script (bash sandbox) | AVAILABLE | Available via Cowork bash tool. CWD is outputs dir — use full paths. `python3` resolves correctly. |
| Web Fetch (static) | AVAILABLE | No JS execution. Blocked by Cloudflare/heavy SPAs. Use WebSearch fallback if fetch fails. |
| SQLite / DuckDB | AVAILABLE | File-based. DuckDB preferred for flat-file analytics. |
| Playwright (headless) | UNVERIFIED | Needs `playwright install chromium` confirmed before first use. |
| Scheduled Tasks | AVAILABLE | Cowork native. Two permanent tasks: nightclaw-worker-trigger, nightclaw-manager-trigger. Do NOT modify schedules — SOUL.md Hard Line. |

## Context Note — Claude Cowork Platform

Scheduled task sessions start from the task prompt directly. The prompt includes a COWORK ENVIRONMENT SETUP preamble that runs `find /sessions` to locate `nightclaw-ops.py`, `check-lock.py`, and `resign.sh` by absolute path. Bootstrap files (SOUL.md, AGENTS-CORE.md, etc.) are **not** auto-injected — the cron prompts instruct the session to read them explicitly at T0. Security boundaries are enforced by CRON-HARDLINES.md (read at T0 before any other action).

Model tiers for `next_pass.model_tier` — see MODEL-TIERS.md for current model IDs:
- `lightweight` → claude-haiku-4-5-20251001
- `standard`    → claude-sonnet-4-6
- `heavy`       → claude-opus-4-6

Minimum viable model for orchestration passes: `standard`. Do not route orchestration-heavy passes to `lightweight` — instruction-following fidelity degrades on the T-step protocol at that tier.

---

## Pre-Flight Decision Rule

For the `next_pass` objective in the LONGRUNNER, identify which tools above are needed.

- All needed tools are `AVAILABLE` → proceed with the pass
- A needed tool is `CONSTRAINED` → check remaining budget before proceeding (log if near limit)
- A needed tool is `UNVERIFIED` → **stop**. Log gap in LONGRUNNER `blocked_reason`. Set ACTIVE-PROJECTS.md status to `blocked`. Surface to {OWNER}.
- A needed tool is `UNAVAILABLE` → **stop**. Apply fallback from `OPS-TOOL-REGISTRY.md`. Note quality degradation in LONGRUNNER §Blockers.

Read `OPS-TOOL-REGISTRY.md` only when: a tool status changes, a new tool needs to be added, or a fallback is needed.
