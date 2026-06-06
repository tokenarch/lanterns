# OPS-FAILURE-MODES.md

<!-- The system's immune memory. -->
<!-- Maintained by: agent (add entries when encountered), {OWNER} (mark RESOLVED when systemic fix deployed) -->
<!-- Read at: start of any diagnostic pass; before attempting a fix; after any unexpected agent behavior -->

---

## Purpose

A system that retries blindly after a failure is not resilient — it is expensive. Blind retries burn token budget, corrupt state further, and obscure the root cause. This file is the difference between a system that diagnoses problems and a system that thrashes.

The agent reads this registry before attempting any fix. The goal is to classify the failure first, then apply the documented remediation. Novel failures that are not in this registry must be added to it before the session ends — otherwise the system learns nothing from the incident.

This registry compounds over time. Every failure added is one less failure that will cost full-triage time in the future.

**Scope:** This file covers failure modes in the NightClaw orchestration layer itself. Failure patterns tied to specific data sources, file formats, or external APIs used by a particular deployment belong in `OPS-KNOWLEDGE-EXECUTION.md` under the **Domain Failure Patterns** section (prefixed DFM-NNN). When a domain failure pattern reaches the point where an MCP connector would eliminate it entirely, the MCP upgrade path is documented there alongside the tactical fix.

---

## How to Use

**Rule 1: Read before diagnosing.**
When something goes wrong — unexpected output, corrupted state, stale scheduler, bad data, looping agent — read this file first. Match symptoms against the `Symptom` fields. Confirm the match using the `Detection signal`. Then apply the documented `Fix`. Do not invent a custom fix when a documented one exists.

**Rule 2: Add new failure modes discovered during operation.**
If a failure occurs that is not in this registry, add it before the session ends. Use the template in the Registry Maintenance section. Assign the next sequential ID. The entry does not need to be perfect — a first draft with observed symptoms and a partial fix is better than no entry.

**Rule 3: Never delete entries. Mark as RESOLVED if fixed systemically.**
Failure mode history is audit trail. Deleting entries removes institutional memory and can mask recurrence of a supposedly fixed problem. If a systemic fix has been deployed, change `Status` to `RESOLVED` and add a `resolution_date` and `resolution_note`. The entry stays.

---

## Registry Maintenance

### How to Add a New Failure Mode

When a failure occurs that is not covered by an existing entry, add it before the session ends. Copy this template and fill in every field:

```markdown
### FM-[next sequential number]
**Name:** [short-slug-no-spaces]

**Symptom:** [What the agent observes — not the cause. What it sees, not why it happened.]

**Root cause:** [Why it happens. The underlying mechanism.]

**Detection signal:** [The specific log entry, file state, field value, or behavior pattern 
that confirms this is the failure — not just that something went wrong, but that THIS 
specific failure mode is the one occurring.]

**Fix:**
[Numbered concrete steps to resolve the current instance of this failure.]

**Prevention:** [What structural change, OPS rule, or checklist item prevents recurrence. 
Reference the relevant OPS file if applicable.]

**Status:** ACTIVE | MITIGATED | RESOLVED
```

### Status Definitions

| Status | Meaning |
|---|---|
| `ACTIVE` | This failure mode can still occur. No systemic fix exists. The agent must be vigilant. |
| `MITIGATED` | An OPS file, checklist, or structural rule addresses this failure mode. It is less likely but not impossible. |
| `RESOLVED` | A systemic fix has been implemented that makes this failure mode structurally impossible (e.g., a hard constraint in the tool, a schema validation that prevents the bad state). Add `resolution_date` and `resolution_note` when marking RESOLVED. |

### Resolution Note Format (for RESOLVED entries)

Add these fields to the entry when marking RESOLVED:

```yaml
resolution_date: "YYYY-MM-DD"
resolution_note: "Brief description of the systemic fix that makes this impossible."
```

### Index Summary

| ID | Name | Status |
|---|---|---|
| FM-001 | plan-without-scheduler | MITIGATED |
| FM-002 | scheduler-without-artifacts | MITIGATED |
| FM-003 | one-shot-subagent-fake-persistence | MITIGATED |
| FM-004 | fixed-cadence-pass-duration-mismatch | MITIGATED |
| FM-005 | endless-refinement-answered-question | MITIGATED |
| FM-006 | scheduler-outliving-phase | MITIGATED |
| FM-007 | approval-friction-silent-degradation | MITIGATED |
| FM-008 | root-heavy-artifact-sprawl | MITIGATED |
| FM-009 | agent-starting-pass-it-cannot-finish | MITIGATED |
| FM-010 | knowledge-rediscovery | MITIGATED |
| FM-011 | context-window-overflow | ACTIVE |
| FM-012 | credential-leakage | ACTIVE |
| FM-014 | infinite-clarification-loop | ACTIVE |
| FM-015 | orphaned-longrunner | ACTIVE |
| FM-016 | knowledge-staleness | ACTIVE |
| FM-017 | conflicting-control-files | ACTIVE |
| FM-018 | metric-gaming | ACTIVE |
| FM-019 | edit-string-mismatch | ACTIVE |
| FM-021 | cron-event-exec-approval-deadlock | ACTIVE |
| FM-023 | web-search-bot-challenge-soft-block | ACTIVE |
| FM-024 | exec-allowlist-opaque-deny | ACTIVE |
| FM-025 | control-plane-unblock-without-runtime-readiness | ACTIVE |
| FM-026 | allowlist-deny-on-explicit-binary-path | ACTIVE |
| FM-028 | cron-overlap-lock-conflict | MITIGATED |
| FM-029 | transition-hold-timeout-expired | MITIGATED |
| FM-030 | light-context-version-mismatch | ACTIVE |
| FM-031 | manager-first-run-audit-log-overwrite | MITIGATED |
| FM-032 | manager-notifications-overwrite-degraded | MITIGATED |
| FM-033 | model-api-rate-limit | ACTIVE |
| FM-035 | heartbeat-token-drain | ACTIVE |
| FM-036 | ops-file-context-bloat | MITIGATED |
