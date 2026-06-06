# MODEL-TIERS.md — NightClaw Model Tier Configuration

<!-- Edited by {OWNER} once at install. Never written by the agent. -->
<!-- The worker reads this at T9 to set the platform default model   -->
<!-- for the next session via: python3 scripts/nightclaw-ops.py set-model-tier <tier> -->

## What This File Does

NightClaw declares one of three model tiers per project in the project's
LONGRUNNER.md (`next_pass.model_tier`). At the end of every worker session (T9),
after the session-close bundle fires, the engine reads the dispatched project's
`next_pass.model_tier` and calls `set-model-tier` to record the intended model
for the next session.

**How model tier switching works in Cowork:** the `set-model-tier` command
emits a single advisory line of the form
`SET_MODEL_TIER:ADVISORY:tier=X:model=Y:platform=cowork`, then exits 0.
There is no programmatic platform CLI to switch models in Cowork; the advisory
is informational only.
The tier mapping below remains the authoritative "what model SHOULD run on this
project's next pass." Operator action when an ADVISORY line is observed:

1. Open Claude Desktop → Cowork → your project → scheduled tasks.
2. Click the `nightclaw-worker` task. Check its configured model.
3. If it does not match the advisory's `model=<id>`, AND the project benefits
   from the advised tier, edit the task's model and save. (Cowork has no
   programmatic equivalent — this is a manual operator step.)
4. If you skip step 3, the next pass runs on whatever model Cowork currently
   has for `nightclaw-worker`. No data is lost and no T9 failure occurs.

The audit log records the advisory so the intent is preserved across sessions
even when the switch itself is not executable.

The worker scheduled task runs at whatever model Cowork assigns. The manager
scheduled task can be configured to a specific model when creating the Cowork
scheduled task (see `orchestration-os/OPS-CRON-SETUP.md`).

## Tier Assignments

```yaml
lightweight: {MODEL_LIGHTWEIGHT}
standard:    {MODEL_STANDARD}
heavy:       {MODEL_HEAVY}
```

## Tier Guidance

| Tier        | Use for                                              | Cost profile  |
|-------------|------------------------------------------------------|---------------|
| lightweight | Structured execution, file writes, data transforms   | Lowest        |
| standard    | Research, synthesis, multi-step reasoning            | Mid           |
| heavy       | Complex judgment, architecture decisions, long docs  | Highest       |

Default for new projects: `standard`. Set in LONGRUNNER-TEMPLATE.md.

## Changing Tiers

To change which model maps to a tier: edit this file and save. The mapping is
read at T9 — no cron changes required. In Cowork, the mapping is informational
only until a platform CLI mechanism becomes available.

To change which tier a project uses for its next pass: edit `next_pass.model_tier`
in the project's LONGRUNNER.md (or let the worker set it via `longrunner_update`).
