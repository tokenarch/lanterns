# CURRENT-PASS.md

<!--
Handoff-state surface. This file is the only place in the repo where open
issues and active-work pointers live. When a fresh LLM needs to know "what
should I be aware of before editing," this is the file to read.

Discipline: append to "Known issues" when a live footgun is identified;
remove entries when they are fixed. Do not turn this file into a journal.
The repo is the source of truth for what the system IS; this file is the
source of truth for what requires attention RIGHT NOW.
-->

## Lanterns — repo identity and platform scope (read first)

This template is the **Lanterns** distribution of NightClaw — published at
`https://github.com/tokenarch/lanterns`. It is **Cowork-only by design.**
The following decisions are intentional and should NOT be "fixed" by future
LLM sessions:

1. **Repo name is `lanterns`; codebase name is `nightclaw`.** The README
   explains the relationship in its opening section. Do not rename engine
   modules, command names, session IDs (`session:nightclaw-worker`,
   `session:nightclaw-manager`), or schema namespaces. The NightClaw name
   is intentional in the codebase and may be retained even if the repo
   itself is re-forked under a different name in the future.

2. **OpenClaw support has been removed and must not be re-introduced.**
   This template was forked from `tokenarch/nightclaw` and stripped of every
   OpenClaw-specific code path, prompt section, and documentation reference.
   If a contributor PR adds OpenClaw compatibility or dual-platform
   abstraction, reject it. The Cowork-only scope is a load-bearing
   simplification: it lets `install.sh` skip cron/logs prompts, lets
   `set-model-tier` emit a single ADVISORY line instead of conditionally
   calling a missing CLI, and lets `SOUL.md`/`CRON-HARDLINES.md` drop two
   OpenClaw-specific hard-line bullets.

3. **Two openclaw references that ARE intentional:**
   - `nightclaw_engine/commands/model_tier.py` mentions openclaw in its
     module docstring as historical context for what the ADVISORY mechanism
     replaced. The actual code path no longer calls openclaw.
   - `scripts/validate.sh` may include a defensive check that WARNs if
     `openclaw` is found in `PATH` — telling the operator they may have
     installed the wrong template. (Currently removed; do not re-add unless
     the Cowork-vs-OpenClaw distinction becomes confusing again.)

4. **Sync direction is one-way: maintainer's local `publictemplate/` → published
   `lanterns` repo.** The lanterns GitHub repo is a fresh-history publication
   target. Changes ride from the maintainer's local staging copy (the working
   tree where this file lives) outward; do not pull from lanterns back into
   publictemplate without conscious review.

5. **Protected-file workflow.** When editing any file in
   `audit/INTEGRITY-MANIFEST.md`'s protected list (SOUL.md, AGENTS-CORE.md,
   IDENTITY.md, MEMORY.md, USER.md, the four `orchestration-os/CRON-*` and
   `OPS-*` prompts, and `orchestration-os/REGISTRY.md`), you MUST run
   `bash scripts/resign.sh <file>` after the edit and then
   `python3 scripts/nightclaw-ops.py integrity-check` to confirm. The worker
   refuses to start if integrity-check fails at T0.

6. **NTFS write hazard.** If this template is checked out on a Windows host
   with the workspace on an NTFS mount accessed from WSL or a Linux sandbox,
   the Edit/Write file tools can silently truncate large writes. The
   workaround: use `python3` heredocs via bash for any multi-line write.
   `scripts/nightclaw-ops.py syntax-check` and `preflight-import` were added
   specifically to catch this failure mode at the next session boundary.

7. **Bootstrap command is the LLM onboarding entry point.** A fresh LLM
   session landing on this repo should run
   `python3 scripts/nightclaw-ops.py bootstrap --track=general` before
   reading individual doctrine files. The bootstrap output is ~27K
   characters / ~6.8K tokens of curated context. Reading every `.md` by
   hand is the failure mode this command was built to prevent.

---
## Active pass

None. This is a fresh template install — see [`README.md`](../README.md) and
[`DEPLOY-CLAUDE.md`](../DEPLOY-CLAUDE.md) for the post-install steps. When you start your first project,
edit this section to record the active pass context.

---

## Known issues

None at install time. Append entries here whenever you identify a live
footgun a future session would need to know about before editing. Run
`python3 scripts/nightclaw-ops.py bootstrap --track=general` to see how
this file is surfaced into the bootstrap output.

---

## Next actions for incoming session

Whatever the install's post-setup checklist surfaces. For Cowork users:

1. Complete the [`DEPLOY-CLAUDE.md`](../DEPLOY-CLAUDE.md) Step 6 scheduled-task
   configuration if not yet done.
2. Verify gates: `bash scripts/verify-integrity.sh`, then
   `python3 scripts/nightclaw-ops.py preflight-import` and `syntax-check`.
3. Edit `SOUL.md` § Domain Anchor, then re-sign:
   `bash scripts/resign.sh SOUL.md`.

---

## File write discipline

If you are on Windows with the workspace on an NTFS-mounted volume (common
under WSL2): use `python3 ... write` patterns rather than the editor's
Edit/Write tools, which can silently truncate large writes on that
filesystem. See `internal_enhancement/ARCHITECTURE.md` for the full
context on this constraint and the NTFS-aware workflows.
