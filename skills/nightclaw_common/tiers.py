"""nightclaw_common.tiers — shared T-step / startup tier vocabulary.

This is the single source of truth for which tier strings are valid in
telemetry events. Both surfaces 1 (engine) and 3 (bridge) import it from
this neutral location, which preserves the engine ↛ bridge DAG invariant
documented in internal_enhancement/ARCHITECTURE.md §0 and enforced by
tests/core/test_surface_boundaries.py.

  * The engine emits events with these tier values via nightclaw_ops.telemetry.
  * The bridge validates incoming events against this same set in
    build_opsstepevent / is_opsstepevent.

If a new tier is added to the cron prompt protocol, add it here and the
runtime check in preflight-import's _check_tier_consistency will keep the
engine + bridge in agreement.
"""
from __future__ import annotations

# Worker tiers: T0, T1, T1.5, T2, T2.5, T2.7, T3, T3.5, T4, T5, T5.5, T6, T7, T7a-T7d, T8, T8.3, T8.5, T9
# Plus "startup" for pre-T0 commands (integrity-check, preflight-import, syntax-check, crash-recover, next-run-id, replay).
ALLOWED_TIERS = frozenset({
    "startup",
    "T0", "T1", "T1.5", "T2", "T2.5", "T2.7", "T3", "T3.5", "T4",
    "T5", "T5.5", "T6", "T7", "T7a", "T7b", "T7c", "T7d",
    "T8", "T8.3", "T8.5", "T9",
})

__all__ = ["ALLOWED_TIERS"]
