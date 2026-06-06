"""tests/core/test_protocol_drift.py — prompt <-> engine command linkage.

Complementary to the runtime ``preflight-import`` consistency check, which
catches STEP_CMD_MAP <-> ALLOWED_TIERS drift between the engine and the
bridge. This test catches drift between the cron PROMPTS (markdown) and the
engine COMMANDS (Python) — a class of bug that only surfaces when a worker
session actually fires the prompt step and the LLM tries to execute a
command that no longer exists.

Failure modes pinned here:
  * Prompt references ``nightclaw-ops.py X`` for an X that is not in
    COMMANDS. The LLM would error out at runtime with "Unknown command".
  * A command in COMMANDS that is not referenced by any prompt, SKILL.md,
    or whitelisted maintenance use. Reported as INFO only; some commands
    are intentionally human/CI-only (bootstrap, schema-*, validate-*).

The whitelist is the contract: editing it requires intent, which is the
point.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# Commands that are intentionally NOT referenced in cron prompts. These are
# human/CI-only entry points (developer bootstrap, schema maintenance, query
# tools). If you add a new command in this category, add it here too.
NON_PROMPT_COMMANDS = {
    # Developer/CI tools
    "bootstrap",
    "schema-lint",
    "schema-render",
    "schema-sync",
    "validate-bundles",
    # Query / introspection tools (callable from admin shell)
    "cascade-read",
    "registry-route",
    "validate-field",
    "os-file-sizes",
    # Engine-internal commands used by other commands or bundles
    "lock-acquire",
    "lock-release",
    "dispatch-validate",
    "phase-validate",
    "longrunner-render",
    # Startup gates wired via SKILL.md (DEPLOY-CLAUDE.md Step 6), not CRON-*-PROMPT.md
    "preflight-import",
    "syntax-check",
    # Admin/debug command, callable from operator shell
    "replay",
}


def _cron_prompt_paths():
    return [
        REPO_ROOT / "orchestration-os" / "CRON-WORKER-PROMPT.md",
        REPO_ROOT / "orchestration-os" / "CRON-MANAGER-PROMPT.md",
    ]


def _commands_referenced_in_prompts():
    """Parse cron prompts for ``nightclaw-ops.py <cmd>`` patterns."""
    pattern = re.compile(r"nightclaw-ops\.py\s+([a-z][a-z0-9-]*)")
    referenced = set()
    for path in _cron_prompt_paths():
        text = path.read_text(encoding="utf-8")
        for match in pattern.findall(text):
            # Filter narrative noise: "call" appears in "every nightclaw-ops.py
            # call so telemetry…" — it is English, not a command name.
            if match in {"call"}:
                continue
            referenced.add(match)
    return referenced


def test_every_prompt_command_exists_in_COMMANDS():
    """Every command name a cron prompt invokes must be in COMMANDS.

    If a refactor removes a command but the prompt still references it,
    the LLM hits "Unknown command" at the affected T-step and the pass
    fails. This pins the linkage.
    """
    from nightclaw_engine.commands import COMMANDS
    referenced = _commands_referenced_in_prompts()
    missing = sorted(referenced - set(COMMANDS.keys()))
    assert not missing, (
        f"Cron prompt references commands not in COMMANDS: {missing}. "
        f"Either restore the command or update the prompt."
    )


def test_every_command_is_referenced_or_whitelisted():
    """Every command in COMMANDS must be either referenced by a prompt or
    explicitly whitelisted as non-prompt (developer/CI/internal).

    This catches: a command added without any caller, AND a command
    accidentally orphaned by a prompt edit.
    """
    from nightclaw_engine.commands import COMMANDS
    referenced = _commands_referenced_in_prompts()
    orphaned = sorted(set(COMMANDS.keys()) - referenced - NON_PROMPT_COMMANDS)
    assert not orphaned, (
        f"Commands in COMMANDS are neither prompt-referenced nor whitelisted: "
        f"{orphaned}.\n\n"
        f"To resolve: either (a) add them to the NON_PROMPT_COMMANDS set at "
        f"the top of this file (tests/core/test_protocol_drift.py) if they "
        f"are intentionally developer/CI-only, OR (b) wire them into a "
        f"prompt under orchestration-os/CRON-*-PROMPT.md so a cron session "
        f"actually invokes them."
    )


def test_step_cmd_map_tiers_are_in_allowed_tiers():
    """Every tier value in STEP_CMD_MAP must appear in bridge ALLOWED_TIERS.

    Otherwise the bridge silently drops the telemetry event tagged with
    that tier — monitor shows missing steps with no warning. This duplicates
    the runtime check in preflight-import's _check_tier_consistency so the
    drift is caught at CI time too.
    """
    from nightclaw_engine.commands import STEP_CMD_MAP
    from nightclaw_bridge.protocol import ALLOWED_TIERS
    step_tiers = set(STEP_CMD_MAP.values())
    bridge_tiers = set(ALLOWED_TIERS)
    missing = sorted(step_tiers - bridge_tiers)
    assert not missing, (
        f"STEP_CMD_MAP uses tier(s) {missing} that are not in "
        f"nightclaw_bridge.protocol.ALLOWED_TIERS. Bridge will drop these "
        f"telemetry events silently."
    )


def test_every_command_has_step_cmd_map_entry():
    """Every command in COMMANDS should have an explicit STEP_CMD_MAP entry.

    Without one, the engine defaults the telemetry tier to "T4" — fine for
    bundle-exec, wrong for everything else.
    """
    from nightclaw_engine.commands import COMMANDS, STEP_CMD_MAP
    missing = sorted(set(COMMANDS.keys()) - set(STEP_CMD_MAP.keys()))
    assert not missing, (
        f"COMMANDS entries with no STEP_CMD_MAP tier: {missing}. "
        f"Add the appropriate tier (T0..T9 or 'startup') to STEP_CMD_MAP."
    )
