# OPS-CRON-SETUP.md
<!-- The exact scheduled task configuration for the always-on system. -->
<!-- Deploy these two tasks. Everything else is file-driven. -->
<!-- Update cadence here when you observe actual pass durations. -->

> **Platform: Claude Cowork.** Worker and manager run as Cowork scheduled
> tasks. The task prompts here are the `--message` payload that Cowork sends
> to the session at fire time — the protocol body in CRON-WORKER-PROMPT.md
> and CRON-MANAGER-PROMPT.md is the canonical instruction set.

---

## The System Runs on Two Scheduled Tasks

That's it. Two. Not one per project. Not one per phase. Two tasks total, running always.

```
TASK 1: WORKER PULSE     — fires every 3h, executes bounded project work
TASK 2: MANAGER PULSE    — fires every 24h, governs direction and value
```

When you add a new project, you add a row to ACTIVE-PROJECTS.md. You do not add a task.
When a project completes, it exits the dispatch table. You do not delete a task.
The scheduled tasks are permanent. The dispatch table is dynamic.

---

## Task 1: Worker Pulse

**Purpose:** Execute one bounded project pass per cycle. Self-routing via ACTIVE-PROJECTS.md.

**Prompt (copy exactly):**
```
HARD LINES ACTIVE: never post externally, never write outside workspace, never modify cron schedule, employment constraint enforced (see USER.md). Step 1: READ orchestration-os/CRON-HARDLINES.md. Step 2: READ orchestration-os/CRON-WORKER-PROMPT.md. Step 3: Follow it exactly from T0 through T9. Do not improvise steps.
```

**Cowork scheduled task setup:**
- Name: `nightclaw-worker-trigger`
- Cron expression: `0 */6 * * *` (every 6 hours)
- The session identifies itself as `session:nightclaw-worker` — this is declared in the
  prompt and used by `check-lock.py` for the LOCK.md holder field. No platform flag needed.

**Recommended starting cadence:** Every 6 hours.
**Adjust after observing:** Check `memory/YYYY-MM-DD.md` pass logs after 3 cycles. If passes
average < 15 min and budget allows, tighten to `0 */3 * * *` (every 3 hours). If passes run heavy,
widen to `0 */12 * * *` (every 12 hours).

**Model note:** Worker runs at whatever model Cowork assigns to the scheduled task session.
`set-model-tier` at T9 will emit a WARN and skip cleanly — this is expected in Cowork.
See MODEL-TIERS.md for tier documentation.

---

## Task 2: Manager Pulse

**Purpose:** Govern direction, value, priority, and escalations across all active projects.

**Prompt (copy exactly):**
```
HARD LINES ACTIVE: never post externally, never write outside workspace, never modify cron schedule, employment constraint enforced (see USER.md). Step 1: READ orchestration-os/CRON-HARDLINES.md. Step 2: READ orchestration-os/CRON-MANAGER-PROMPT.md. Step 3: Follow it exactly from T0 through T9. Do not improvise steps.
```

**Cowork scheduled task setup:**
- Name: `nightclaw-manager-trigger`
- Cron expression: `0 9 * * *` (daily at 9 AM — adjust to your preferred time)
- The session identifies itself as `session:nightclaw-manager` via the prompt.

**Recommended starting cadence:** Daily (1 pass/day — the manager governs direction, not execution).

---

## Setup Checklist

```
□ Task 1 created: nightclaw-worker-trigger, cron 0 */6 * * *, prompt copied from above
□ Task 2 created: nightclaw-manager-trigger, cron 0 9 * * *, prompt copied from above
□ MODEL-TIERS.md exists with claude-haiku/sonnet/opus model IDs filled in (informational)
□ ACTIVE-PROJECTS.md exists in workspace root with at least one active row
□ Each active project has a valid LONGRUNNER.md with:
    □ phase.status = "active"
    □ next_pass objective defined (not blank, not "awaiting confirmation")
    □ pass_output_criteria defined
    □ dispatch LONGRUNNER path exists on disk and matches ACTIVE-PROJECTS.md exactly
    □ next_pass input/output paths resolve to real repo locations (no stale path references)
□ orchestration-os/OPS-TOOL-REGISTRY.md reviewed — tools used in first pass are AVAILABLE
□ For script-based next_pass objectives, command executable paths are host-valid (prefer PATH-resolved commands like `python3` over hardcoded absolute paths unless verified)
□ memory/ directory exists (created automatically if not)
□ PROJECTS/MANAGER-REVIEW-REGISTRY.md exists (create minimal version if not)
```

---

## How to Add a New Project (No New Tasks)

```
1. Copy orchestration-os/LONGRUNNER-TEMPLATE.md → PROJECTS/[slug]/LONGRUNNER.md
2. Fill in: mission, phase.name, phase.objective, phase.stop_condition, next_pass
3. Add one row to ACTIVE-PROJECTS.md: priority, slug, LONGRUNNER path, phase, status: active
4. Done. Next worker pulse picks it up automatically.
```

---

## How to Pause a Project (No Task Changes)

```
1. In ACTIVE-PROJECTS.md: set status to "paused"
2. Done. Next worker pulse skips it. Current pass (if running) finishes naturally.
```

---

## How to Shift Focus (Zero Downtime)

```
1. In ACTIVE-PROJECTS.md: update the Priority column — renumber rows
2. Done. Next worker pulse routes to the new highest priority.
```

---

## How to Emergency Stop Everything

```
1. In ACTIVE-PROJECTS.md: set ALL rows to status: "paused"
2. Done. Both tasks keep running but find nothing actionable. Zero project work happens.
3. Resume by setting rows back to "active" one at a time.
```

The scheduled tasks never stop. The dispatch table controls what they do.

---

## Session Lock (LOCK.md)

The worker and manager tasks share write access to ACTIVE-PROJECTS.md and project LONGRUNNERs.
LOCK.md prevents concurrent writes when both tasks fire close together.

**Expiry:** A lock is stale if its `locked_at` timestamp is >20 minutes old.
Any session finding a stale lock clears it and proceeds normally.

**Normal operation:** The lock is acquired at STARTUP, held through T0–T8, and released
at T9 (BUNDLE:session_close). If a new task fires while the lock is held by a valid
(non-stale) session: exit immediately with a LOW deferral note to NOTIFICATIONS.md.

**Cadence implication:** Do not run the worker cadence below 25 minutes. The 20-minute
stale threshold is designed for the 3-hour default cadence — at <25 minutes, a
legitimate in-progress pass could be incorrectly classified as stale. See FM-028.

---

## Observed Cadence Log

Update this table as you observe real pass durations:

| Date | Project | Avg Pass Duration | Cron Setting | Alignment |
|------|---------|------------------|--------------|-----------|
| 2026-05-25 | — | unknown — first run | 0 */6 * * * (starting cadence) | TBD |
| — | — | — | — | — |

After 3–5 cycles, adjust cadence based on observed duration. Document it here.

---

## How to Change Cadence ({OWNER} only — agents cannot do this)

The agent cannot modify its own schedule (SOUL.md Hard Line). {OWNER} makes cadence
changes via Cowork: delete the existing scheduled task and recreate with the new cron expression.

**Cadence decision rule:** cron interval ≥ (average pass duration × 1.5). Buffer matters.

**Before tightening cadence:** confirm the average pass duration from `memory/YYYY-MM-DD.md`.
If passes average 12 minutes, an hourly cadence works. If passes average 25 minutes,
keep at 3 hours — overlapping sessions corrupt LONGRUNNER state.

**Document every cadence change** in the Observed Cadence Log table above.
