# INTEGRITY-MANIFEST.md
<!-- Session state verification — SHA-256 drift detection for core framework files. -->
<!-- Purpose: detect accidental drift between sessions. Not a tamper-prevention mechanism. -->
<!-- For tamper-proof integrity, use signed git commits. -->
<!-- Reader: worker T0 (verify), manager T1 (verify + timestamp). -->
<!-- Writer: {OWNER} (hash values), manager (last_verified timestamps only). -->
<!-- APPEND-ONLY for timestamp updates. Hash values: {OWNER} only. -->

---

## Protected Files

| File | SHA256 | Last verified | Verified by |
|------|--------|---------------|-------------|
| `SOUL.md` | 8915d2eab0a7103c305bdc152af361557d618551d82bf2ce45259e029304a9d7 | 2026-06-06 | computer-signed-2026.4.22 |
| `USER.md` | 75268773fdb4a367d656b5f4b7c5438b102fb6d154ca1836a7ae5a3059d576bc | 2026-04-22 | computer-signed-2026.4.22 |
| `IDENTITY.md` | 4a0cc004c9963a83dcdcf56bb0b10db36525e52b22bef90db616dcfe89bf457d | 2026-06-06 | computer-signed-2026.4.22 |
| `MEMORY.md` | c7e3cacece78d2ea95e665c61656396b1f595bdc109b88ac1fe8b59c3e360848 | 2026-06-06 | computer-signed-2026.4.22 |
| `AGENTS-CORE.md` | 6a7ef7e8a43693c231a84147950e21e9863a31a562b99b6e39e66ab382f2d700 | 2026-06-04 | computer-signed-2026.4.22 |
| `orchestration-os/CRON-WORKER-PROMPT.md` | ec4ce2e91a1db03bf1c4226a68424dfe6e2386a60dd3603f911c463b804055b5 | 2026-06-06 | computer-signed-2026.4.22a |
| `orchestration-os/CRON-MANAGER-PROMPT.md` | 6de08efa7a924326b0a731d7206deaed3dac5369045e59c7929615d63f118ad3 | 2026-06-06 | computer-signed-2026.4.22a |
| `orchestration-os/OPS-PREAPPROVAL.md` | 6a0e63eeb47cec63f163af99c85a82e680ca9a527a8f06f063de4f397486dda6 | 2026-04-24 | computer-signed-2026.4.22 |
| `orchestration-os/OPS-AUTONOMOUS-SAFETY.md` | 1c22c18624f0d774151b3bdfed6f8145328761d52cca6a32d1430c0f9b1ca37b | 2026-06-04 | computer-signed-2026.4.22 |
| `orchestration-os/CRON-HARDLINES.md` | e90ec4f7c4b866c15be99e739c6b1e856cedd22fc551f8a51b01731273c2ed80 | 2026-06-04 | computer-signed-2026.4.22 |
| `orchestration-os/REGISTRY.md` | 794b7586dc514818bb71fdd5bbbffe886596495ed232c7fe67fcf5033a091f98 | 2026-06-07 | computer-signed-2026.4.22 |

---

## First-Sign Instructions (run once after install)

<!-- Human operation: run from workspace root in your terminal. -->
<!-- Uses sha256sum (standard shell tool) for interactive use. -->
<!-- The install script (scripts/install.sh) runs this step automatically -->
<!-- and updates this file; manual execution is only needed if the script -->
<!-- fails or if you are doing a manual install. -->

In your workspace root, run:

```bash
for f in SOUL.md USER.md IDENTITY.md MEMORY.md AGENTS-CORE.md \
  orchestration-os/CRON-WORKER-PROMPT.md \
  orchestration-os/CRON-MANAGER-PROMPT.md \
  orchestration-os/OPS-PREAPPROVAL.md \
  orchestration-os/OPS-AUTONOMOUS-SAFETY.md \
  orchestration-os/CRON-HARDLINES.md \
  orchestration-os/REGISTRY.md; do
  echo "$(sha256sum "$f" | cut -d' ' -f1)  $f"
done
```

Paste each hash into the SHA256 column above. Set Last verified to today's date. Set Verified by to `{OWNER}-signed-[version]` (e.g. `yourname-signed-2026.4.16`).

**Only {OWNER} updates hash values in this file. Never delegate to the agent.**

---

## Worker T0 Protocol

<!-- Agent operation: runs inside a cron session via tool call. -->
<!-- Uses Python (not sha256sum) because the agent resolves {WORKSPACE_ROOT} at runtime -->
<!-- as a fully-qualified path. sha256sum is equivalent but less portable across agent -->
<!-- execution environments where shell PATH may differ. Both methods produce identical hashes. -->

For each file in the table above, substitute its exact relative path for FILENAME:
  `python3 -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path('{WORKSPACE_ROOT}/FILENAME').expanduser().read_bytes()).hexdigest())"`

Each output MUST be exactly 64 hex characters. Empty or error = FAIL (treat as hash mismatch).

PASS (all valid + match): continue to step 1 (lock acquisition).
FAIL (any mismatch or invalid output): STOP IMMEDIATELY. No lock, no writes, no T9. {OWNER} investigates.

---

## Manager T1 Protocol

Same hash computation as worker T0.
PASS: update Last verified + Verified by to today's date + nightclaw-manager. BUNDLE:manifest_verify.
FAIL: STOP IMMEDIATELY. No lock, no writes, no T9. {OWNER} investigates.

---

## Re-sign After Any Edit to a Protected File

<!-- Human operation: run from your terminal (same sha256sum tool as First-Sign). -->
<!-- Do not delegate this step to the agent — hash values in this file are {OWNER}-only. -->

Run this in your terminal after editing any file in the table:
  `cd {WORKSPACE_ROOT} && sha256sum [edited-file] | cut -d' ' -f1`

Replace the hash value in this file. Do not update via agent — {OWNER} only.
