"""nightclaw_bridge.snapshot_contract -- bridge payload validators."""
from __future__ import annotations
from typing import Any, Mapping

REQUIRED_TOP = {"type","snapshot","t_emitted"}
SCOPED_REPLAY_EVENTS = {"state_replay", "project_snapshot", "session_replay"}
_EXPECTED_SCOPE_MODE = {
    "state_replay": "live",
    "project_snapshot": "project",
    "session_replay": "replay",
}

def build_sessionssnapshot_payload(snapshot: dict, t_emitted: str) -> dict:
    return {"type":"sessionssnapshot","snapshot": snapshot, "t_emitted": t_emitted}

def validate_sessionssnapshot_payload(p: Mapping[str, Any]) -> dict:
    if not isinstance(p, Mapping):
        raise ValueError("payload must be a mapping")
    missing = REQUIRED_TOP - set(p.keys())
    if missing:
        raise ValueError(f"missing fields: {sorted(missing)}")
    if p.get("type") != "sessionssnapshot":
        raise ValueError("type must be sessionssnapshot")
    snap = p.get("snapshot")
    if not isinstance(snap, Mapping):
        raise ValueError("snapshot must be a mapping")
    if "sessions" not in snap or "ops_timeline" not in snap:
        raise ValueError("snapshot must contain sessions and ops_timeline")
    if not isinstance(snap["sessions"], Mapping) or not isinstance(snap["ops_timeline"], Mapping):
        raise ValueError("sessions/ops_timeline must be mappings")
    return dict(p)


def validate_scoped_replay_payload(p: Mapping[str, Any]) -> dict:
    """Validate rich /ws envelopes cannot masquerade across UI scopes."""
    if not isinstance(p, Mapping):
        raise ValueError("payload must be a mapping")
    event_type = p.get("event_type")
    if event_type not in SCOPED_REPLAY_EVENTS:
        raise ValueError("event_type must be state_replay, project_snapshot, or session_replay")
    ctx = p.get("scope_context")
    if not isinstance(ctx, Mapping):
        raise ValueError("scope_context must be a mapping")
    view = ctx.get("view_scope")
    feed = ctx.get("feed_policy")
    session = ctx.get("session_context")
    if not isinstance(view, Mapping):
        raise ValueError("scope_context.view_scope must be a mapping")
    if not isinstance(feed, Mapping):
        raise ValueError("scope_context.feed_policy must be a mapping")
    if not isinstance(session, Mapping):
        raise ValueError("scope_context.session_context must be a mapping")
    expected_mode = _EXPECTED_SCOPE_MODE[event_type]
    if view.get("mode") != expected_mode:
        raise ValueError(f"{event_type} requires scope_context.view_scope.mode={expected_mode}")
    may_mutate = feed.get("live_events_mutate_selected_context")
    if event_type == "state_replay":
        if may_mutate is not True:
            raise ValueError("state_replay must allow live selected-context mutation")
    else:
        if may_mutate is not False:
            raise ValueError(f"{event_type} must not allow live selected-context mutation")
    if event_type == "session_replay" and session.get("is_historical") is not True:
        raise ValueError("session_replay requires historical session_context")
    return dict(p)
