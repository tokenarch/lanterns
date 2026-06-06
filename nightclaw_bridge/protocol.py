"""nightclaw_bridge.protocol -- opsstepevent payload contract."""
from __future__ import annotations
from typing import Any, Mapping

# ALLOWED_TIERS lives in nightclaw_common.tiers as the single source of truth
# both the engine (telemetry emitter) and the bridge (validator) agree on.
# Worker tiers: T0..T9 with half-steps (T1.5, T2.5, T2.7, T3.5, T5.5, T8.3, T8.5)
# and T7a..T7d substeps, plus "startup" for pre-T0 startup-gate commands.
# Sourced from orchestration-os/CRON-WORKER-PROMPT.md and CRON-MANAGER-PROMPT.md.
# Re-exported here for back-compat with external code that imports from this module.
from nightclaw_common.tiers import ALLOWED_TIERS  # noqa: E402,F401

def build_opsstepevent(*, run_id: str, tier: str, cmd: str, t_emitted: str,
                       slug: str | None = None, pid: int | None = None,
                       session: str | None = None, exit_code: int | None = None) -> dict:
    if not run_id: raise ValueError("run_id required")
    if not cmd: raise ValueError("cmd required")
    if tier not in ALLOWED_TIERS: raise ValueError(f"bad tier {tier!r}")
    if not t_emitted: raise ValueError("t_emitted required")
    p: dict = {"type":"opsstepevent","run_id":run_id,"tier":tier,"cmd":cmd,"t_emitted":t_emitted}
    if slug is not None: p["slug"]=slug
    if pid is not None: p["pid"]=pid
    if session is not None: p["session"]=session
    if exit_code is not None: p["exit_code"]=exit_code
    return p

def is_opsstepevent(p: Mapping[str, Any]) -> bool:
    try:
        return (p.get("type")=="opsstepevent"
                and bool(p.get("run_id")) and bool(p.get("cmd"))
                and p.get("tier") in ALLOWED_TIERS
                and bool(p.get("t_emitted")))
    except Exception:
        return False
