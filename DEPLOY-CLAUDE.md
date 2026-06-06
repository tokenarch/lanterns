# DEPLOY-CLAUDE.md — Claude Desktop + Cowork Deployment Guide

> **Platform:** Claude Desktop with Cowork mode
> **Status:** Working deployment — this guide reflects the current tested setup.
> Details will be refined as more users onboard.
>

---

## What This Is

NightClaw can run entirely inside Claude Desktop using Cowork mode for interactive
sessions and two Claude scheduled tasks for autonomous overnight operation. No
additional runtime is required. The LLM is Claude; the workspace is a folder
on your machine that Cowork mounts directly.

The split:
- **Claude Cowork project** — your interactive session. Point it at the NightClaw
  workspace folder. This is how you approve projects, review notifications, run
  admin commands, and interact with the monitor.
- **Two Claude scheduled tasks** — the autonomous worker and manager. They fire on
  a cron schedule, find the workspace by path discovery, and execute one bounded
  pass each without any human present.

---

## Requirements

```
Claude Desktop (latest)
Cowork mode enabled
Python 3.10+
PyYAML
pytest  (for gate runs — optional but recommended)
Git Bash (Windows) — required for scripts/nightclaw-admin.sh
```

---

## Step 1 — Get the Files

Clone or download the NightClaw repo and place the contents in a folder you
control. A clean path with no spaces works best on Windows:

```
C:\Users\<you>\Documents\nightclaw-workspace\
```

The workspace root is wherever `SOUL.md` lives. Do not nest the files inside
a subdirectory — they go at the root.

---

## Step 2 — Run install.sh

From the workspace root (Git Bash on Windows):

```bash
bash scripts/install.sh
```

This prompts for your owner handle, workspace path, and model tier IDs, then
substitutes placeholders across every `.md` file and generates the initial
SHA-256 integrity hashes.

**On Windows:** use forward slashes or escaped backslashes when the script asks
for the workspace path, e.g. `C:/Users/you/Documents/nightclaw-workspace`.

---

## Step 3 — Fill in SOUL.md and USER.md

Open `SOUL.md`, replace `{DOMAIN_ANCHOR}` with 2–3 sentences describing your
domain focus. This is what the idle cycle uses to propose your first autonomous
project. Then re-sign:

```bash
bash scripts/resign.sh SOUL.md
```

Open `USER.md` and fill in your name, timezone, and any domain restrictions.
Re-sign if you change it:

```bash
bash scripts/resign.sh USER.md
```

---

## Step 4 — Verify the Workspace

```bash
bash scripts/verify-integrity.sh        # must show 11/11 PASS
bash scripts/validate.sh
python3 scripts/nightclaw-ops.py schema-lint
python3 scripts/nightclaw-ops.py scr-verify
python3 scripts/nightclaw-ops.py validate-bundles
python3 scripts/nightclaw-ops.py integrity-check
python3 scripts/nightclaw-ops.py preflight-import  # Pass 12 import gate
python3 scripts/nightclaw-ops.py syntax-check      # Pass 12 NTFS-truncation gate
pytest tests/ -q                                   # optional but recommended
```

All gates must pass before proceeding.

---

## Step 5 — Create a Cowork Project

1. Open Claude Desktop → Cowork
2. Create a new project
3. Point it at your workspace folder (the folder containing `SOUL.md`)
4. This project is your interactive session — use it to approve/reject
   project proposals, view notifications, and run admin commands

---

## Step 6 — Create the Two Scheduled Tasks

NightClaw requires two scheduled tasks in Claude Desktop Cowork: a **worker**
(runs every 6 hours) and a **manager** (runs once daily). Each task fires a
fresh Claude session whose system prompt is the contents of the corresponding
`*.skill.md` file below.

**Worker cadence:** every 6 hours (`0 */6 * * *`) — chosen as a conservative
default for Cowork's per-task token budget. After 3-5 real passes, adjust
based on `memory/YYYY-MM-DD.md` actual durations.

**Manager cadence:** 9 AM daily (`0 9 * * *`)

### 6a — Create the worker scheduled task

In Claude Desktop:

1. Open the Cowork project you created in Step 5
2. Open the scheduled-tasks panel (sidebar → Schedule)
3. Click **New scheduled task**
4. Name: `nightclaw-worker`
5. Schedule: every 6 hours (cron `0 */6 * * *`)
6. Model: leave as project default — the worker's tier is set at T9 by the prior pass
7. Prompt: paste the contents of the SKILL.md below

```text
# nightclaw-worker.skill.md

## COWORK ENVIRONMENT SETUP

You are a NightClaw worker session. Before doing anything else, locate your
workspace and confirm the engine surface is reachable:

```bash
# Discover the workspace root (the folder containing SOUL.md and LOCK.md).
# Cowork mounts the user's selected folder under /sessions/<id>/mnt/<folder-name>/,
# regardless of what the user named the folder. We anchor on "/mnt/" rather than
# any specific folder name so the discovery works for any workspace folder name.
WORKSPACE=$(find /sessions -type f -name "SOUL.md" -path "*/mnt/*" 2>/dev/null \
  | head -n1 | xargs -r dirname)

# Halt with a clear error if discovery returned nothing — silent fallthrough
# with WORKSPACE="" would let the rest of the script run from the wrong CWD.
if [ -z "$WORKSPACE" ]; then
    echo "FAIL: could not locate SOUL.md under /sessions/*/mnt/ — is your"
    echo "      Cowork project pointed at the NightClaw workspace folder?"
    exit 2
fi

# Confirm the three entry points exist
test -f "$WORKSPACE/scripts/nightclaw-ops.py" || { echo "FAIL: nightclaw-ops.py missing"; exit 2; }
test -f "$WORKSPACE/scripts/check-lock.py"    || { echo "FAIL: check-lock.py missing";    exit 2; }
test -f "$WORKSPACE/scripts/resign.sh"        || { echo "FAIL: resign.sh missing";        exit 2; }

echo "WORKSPACE=$WORKSPACE"
cd "$WORKSPACE"

# Preflight: import-test every Python module the worker needs. Catches NTFS
# write truncation and stale-code regressions BEFORE the T-step protocol
# begins. If any module fails to import, exit cleanly so the scheduled task
# shows a recoverable failure rather than entering T0 with a broken engine.
python3 scripts/nightclaw-ops.py preflight-import || {
    echo "FAIL: preflight-import detected broken imports — halt session"
    exit 2
}

# Syntax-check: AST-parse every .py file. Catches NTFS write truncation in
# modules that preflight doesn't import directly (test files, lazy-loaded
# modules). Together with preflight-import, this closes the silent-write-
# failure loop that has bitten this codebase multiple times.
python3 scripts/nightclaw-ops.py syntax-check || {
    echo "FAIL: syntax-check detected broken .py file(s) — halt session"
    exit 2
}
```

Use the discovered `$WORKSPACE` value as your workspace root for all subsequent
file operations. All Python invocations in the protocol below assume CWD is
$WORKSPACE.

## PROTOCOL

1. Read `orchestration-os/CRON-HARDLINES.md` — those rules govern this entire session.
2. Read `orchestration-os/CRON-WORKER-PROMPT.md` — follow it exactly from T0 through T9.
3. Do not improvise steps. Do not skip integrity-check at T0. Do not skip session_close at T9.
```

### 6b — Create the manager scheduled task

Same procedure, with these differences:

1. Name: `nightclaw-manager`
2. Schedule: daily at 9 AM (cron `0 9 * * *`)
3. Model: set explicitly to a capable judgment-class model (see MODEL-TIERS.md)
4. Prompt: paste the contents of the SKILL.md below

```text
# nightclaw-manager.skill.md

## COWORK ENVIRONMENT SETUP

You are a NightClaw manager session. Before doing anything else, locate your
workspace and confirm the engine surface is reachable:

```bash
# Discover the workspace root (the folder containing SOUL.md and LOCK.md).
# Cowork mounts the user's selected folder under /sessions/<id>/mnt/<folder-name>/,
# regardless of what the user named the folder. We anchor on "/mnt/" rather than
# any specific folder name so the discovery works for any workspace folder name.
WORKSPACE=$(find /sessions -type f -name "SOUL.md" -path "*/mnt/*" 2>/dev/null \
  | head -n1 | xargs -r dirname)

# Halt with a clear error if discovery returned nothing — silent fallthrough
# with WORKSPACE="" would let the rest of the script run from the wrong CWD.
if [ -z "$WORKSPACE" ]; then
    echo "FAIL: could not locate SOUL.md under /sessions/*/mnt/ — is your"
    echo "      Cowork project pointed at the NightClaw workspace folder?"
    exit 2
fi

# Confirm the three entry points exist
test -f "$WORKSPACE/scripts/nightclaw-ops.py" || { echo "FAIL: nightclaw-ops.py missing"; exit 2; }
test -f "$WORKSPACE/scripts/check-lock.py"    || { echo "FAIL: check-lock.py missing";    exit 2; }
test -f "$WORKSPACE/scripts/resign.sh"        || { echo "FAIL: resign.sh missing";        exit 2; }

echo "WORKSPACE=$WORKSPACE"
cd "$WORKSPACE"

# Preflight: import-test every Python module the worker needs. Catches NTFS
# write truncation and stale-code regressions BEFORE the T-step protocol
# begins. If any module fails to import, exit cleanly so the scheduled task
# shows a recoverable failure rather than entering T0 with a broken engine.
python3 scripts/nightclaw-ops.py preflight-import || {
    echo "FAIL: preflight-import detected broken imports — halt session"
    exit 2
}

# Syntax-check: AST-parse every .py file. Catches NTFS write truncation in
# modules that preflight doesn't import directly (test files, lazy-loaded
# modules). Together with preflight-import, this closes the silent-write-
# failure loop that has bitten this codebase multiple times.
python3 scripts/nightclaw-ops.py syntax-check || {
    echo "FAIL: syntax-check detected broken .py file(s) — halt session"
    exit 2
}
```

## PROTOCOL

1. Read `orchestration-os/CRON-HARDLINES.md` — those rules govern this entire session.
2. Read `orchestration-os/CRON-MANAGER-PROMPT.md` — follow it exactly from T0 through T9.
3. Do not improvise steps. The manager's role is governance, not execution.
```

### 6c — Verify both tasks before letting them fire

Before walking away:

- Trigger each task manually once (Cowork → scheduled-tasks → Run now)
- Confirm the worker reaches T9 cleanly and writes a SESSION-REGISTRY entry
- Confirm the manager surfaces a brief review note to NOTIFICATIONS.md (or
  records `outcome=clean` with no action if nothing required attention)
- If either fails at T0 (workspace discovery, integrity-check, or lock), fix
  the cause before allowing the schedule to fire

---

## Step 7 — Activate Pre-Approvals

Before your first overnight run, activate the standing pre-approvals so the
worker can operate autonomously without blocking on every action:

```bash
# From your Cowork interactive session or Git Bash:
bash scripts/nightclaw-admin.sh arm PA-001
bash scripts/nightclaw-admin.sh arm PA-002
```

Without these, the worker runs in conservative mode and idle cycles produce
nothing actionable.

---

## Step 8 — Optional: Start the Monitor

The browser monitor gives a live view of workspace state, pass progress, and
notifications. Start the bridge from Git Bash:

```bash
bash scripts/start-monitor.sh
```

The bridge serves the monitor over HTTP on `localhost:8080` (configurable in
`nc_config.json` and `scripts/start-monitor.sh`). Open it in your browser at:

```
http://localhost:8080/nightclaw-monitor.html
```

Do NOT open the HTML file directly via `file://` — the monitor fetches
`nc_config.json` to discover the bridge port, which `file://` blocks. The
WebSocket connection runs on `localhost:8787` by default; both ports are
served by the same `scripts/start-monitor.sh` process.

---

## Upgrading an Existing Deployment

If you set up Cowork scheduled tasks earlier and the SKILL.md content in
Step 6 has since changed (for example, when new gate commands like
`preflight-import` or `syntax-check` are added), the prompts pasted into
your scheduled tasks are NOT automatically refreshed — Cowork stores the
task prompt as a snapshot at creation time.

To upgrade:

1. Pull the latest repo contents into your workspace folder.
2. Open Claude Desktop → Cowork → your project → scheduled tasks panel.
3. For each task (`nightclaw-worker` and `nightclaw-manager`):
   - Click the task to edit it
   - Replace the prompt with the corresponding SKILL.md block from
     [Step 6](#step-6--create-the-two-scheduled-tasks) in this file
   - Save
4. Optionally trigger each task manually (Run now) to verify the new gates
   fire and the session reaches T9 cleanly.

The repo prompts (`orchestration-os/CRON-WORKER-PROMPT.md` and
`orchestration-os/CRON-MANAGER-PROMPT.md`) are read at runtime by the
session, so changes there ARE picked up automatically. Only the
COWORK ENVIRONMENT SETUP preamble in the SKILL.md requires manual
re-paste, because it controls what happens before the session reads any
repo file.

---

## Day-to-Day Operation

**What happens automatically:**
- Worker fires every 6 hours, executes one bounded pass on the top-priority
  active project, updates state, appends to audit/memory logs
- Manager fires each morning, reviews recent worker activity, surfaces
  escalations and quality concerns
- When no active projects exist, the worker's idle cycle (Tier 4 in
  `orchestration-os/OPS-IDLE-CYCLE.md`) drafts a new project proposal from
  your Domain Anchor and surfaces it to `NOTIFICATIONS.md`

**What you do:**
- Open your Cowork project each morning, check `NOTIFICATIONS.md`
- Approve or decline project proposals: `bash scripts/nightclaw-admin.sh approve <slug>`
  or `bash scripts/nightclaw-admin.sh decline <slug>`
- Approve phase transitions when the manager surfaces them
- Edit `SOUL.md` or `USER.md` when your domain focus changes (re-sign after)

---

## Troubleshooting

**Scheduled tasks not running:** Check that both tasks are enabled in Claude
Desktop. The tasks are off by default when first created.

**Integrity check failing:** A protected file was changed without re-signing.
Run `bash scripts/verify-integrity.sh` to identify which file, then
`bash scripts/resign.sh <file>` after verifying the change was intentional.

**Bridge not connecting:** Confirm `bash scripts/start-monitor.sh` is running
and nothing else is using ports 8080 or 8787. On Windows, run in Git Bash, not
PowerShell.

**`cat` or `tail` not found errors:** These are resolved in the current bridge
version — file reads now use Python directly. Update to the latest bridge code
if you see these errors.

For other issues, see `orchestration-os/OPS-FAILURE-MODES.md` for the failure
mode registry. (A `TROUBLESHOOTING.md` is not bundled with this template — open
an issue on the project's GitHub repo if you hit a failure mode not covered
by `OPS-FAILURE-MODES.md`.)
