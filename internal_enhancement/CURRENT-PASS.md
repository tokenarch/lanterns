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
