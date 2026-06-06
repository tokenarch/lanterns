"""nightclaw_engine.commands.model_tier — Model tier advisory emission (Cowork).

Single command:

* ``set-model-tier`` — reads MODEL-TIERS.md, resolves model ID for the given
  tier, and emits an ADVISORY line naming the intended model for the next
  worker session.

Design contract:
  - Called at T9.5, after BUNDLE:session_close fires and LOCK.md is released.
  - Cowork has no programmatic CLI for switching the active model — the
    output is an audit-log advisory the operator (or future Cowork API)
    consumes to set the next scheduled-task model.
  - Never raises — all failures emit clean output lines so the session
    audit record captures them without crashing T9.
  - Does not write to any workspace file.
  - Manager scheduled task is unaffected: it carries its own model
    configuration at task-creation time.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from . import _shared


# ---------------------------------------------------------------------------
# MODEL-TIERS.md parser
# ---------------------------------------------------------------------------

_TIER_RE = re.compile(
    r"^(lightweight|standard|heavy)\s*:\s*(.+)$",
    re.IGNORECASE,
)

_VALID_TIERS = frozenset({"lightweight", "standard", "heavy"})


def _parse_model_tiers(root: Path) -> dict[str, str]:
    """Parse MODEL-TIERS.md and return {tier: model_id}.

    Reads the yaml block between ```yaml and ``` fences.
    Returns empty dict if the file is missing or unparseable.
    """
    path = root / "MODEL-TIERS.md"
    if not path.exists():
        return {}

    tiers: dict[str, str] = {}
    in_yaml = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "```yaml":
            in_yaml = True
            continue
        if stripped == "```" and in_yaml:
            break
        if not in_yaml:
            continue
        m = _TIER_RE.match(stripped)
        if not m:
            continue
        tier = m.group(1).lower()
        model_id = m.group(2).strip()
        # Skip unfilled install placeholders
        if model_id.startswith("{") and model_id.endswith("}"):
            continue
        tiers[tier] = model_id

    return tiers


# ---------------------------------------------------------------------------
# Command entry point
# ---------------------------------------------------------------------------

def cmd_set_model_tier():
    """Switch the platform default model to the one mapped to a given tier.

    Usage: set-model-tier <tier>
    Tier:  lightweight | standard | heavy

    Reads MODEL-TIERS.md for the model ID mapping.
    On Cowork the call emits an ADVISORY line; no platform CLI is invoked.
    All emissions are non-fatal — T9 never aborts on this step.
    """
    if len(sys.argv) < 3:
        print("ERROR:USAGE: set-model-tier <lightweight|standard|heavy>", file=sys.stderr)
        sys.exit(2)

    tier = sys.argv[2].strip().lower()
    if tier not in _VALID_TIERS:
        print(
            f"ERROR:SET_MODEL_TIER:invalid tier {tier!r}"
            f" — must be one of: {', '.join(sorted(_VALID_TIERS))}",
            file=sys.stderr,
        )
        sys.exit(2)

    tiers = _parse_model_tiers(_shared.ROOT)

    if not tiers:
        print(
            "WARN:SET_MODEL_TIER:MODEL-TIERS.md missing or empty"
            " — model tier switch skipped. Create MODEL-TIERS.md to enable."
        )
        sys.exit(0)  # non-fatal — feature simply not configured

    model_id = tiers.get(tier)
    if not model_id:
        print(
            f"WARN:SET_MODEL_TIER:tier={tier} not found in MODEL-TIERS.md"
            " — model tier switch skipped"
        )
        sys.exit(0)  # non-fatal — tier not mapped

    # Cowork emits an ADVISORY line — no platform CLI exists to programmatically
    # switch the active model. The operator (or a future Cowork API) consumes
    # this line and updates the scheduled-task model if needed.
    print(f"SET_MODEL_TIER:ADVISORY:tier={tier}:model={model_id}:platform=cowork")
    sys.exit(0)


__all__ = ["cmd_set_model_tier"]
