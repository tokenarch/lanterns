import pytest
from nightclaw_bridge.snapshot_contract import (
    build_sessionssnapshot_payload,
    validate_scoped_replay_payload,
    validate_sessionssnapshot_payload,
)

def test_build_then_validate_roundtrip():
    snap = {"sessions": {"RUN-1": {"kinds": ["open"]}},
            "ops_timeline": {"RUN-1": [{"tier":"T1","cmd":"dispatch"}]}}
    p = build_sessionssnapshot_payload(snap, "2026-04-17T16:51:00Z")
    out = validate_sessionssnapshot_payload(p)
    assert out["type"] == "sessionssnapshot"
    assert out["snapshot"]["ops_timeline"]["RUN-1"][0]["cmd"] == "dispatch"

def test_validate_rejects_missing_fields():
    with pytest.raises(ValueError):
        validate_sessionssnapshot_payload({"type":"sessionssnapshot"})

def test_validate_rejects_wrong_type():
    with pytest.raises(ValueError):
        validate_sessionssnapshot_payload(
            {"type":"other","snapshot":{"sessions":{},"ops_timeline":{}},
             "t_emitted":"2026-04-17T16:51:00Z"})

def test_validate_rejects_bad_snapshot_shape():
    with pytest.raises(ValueError):
        validate_sessionssnapshot_payload(
            {"type":"sessionssnapshot","snapshot":{"sessions":{}},
             "t_emitted":"2026-04-17T16:51:00Z"})


def _scoped(event_type, mode, *, mutates, historical=False):
    return {
        "event_type": event_type,
        "scope_context": {
            "view_scope": {"mode": mode, "selected_kind": "session" if historical else mode},
            "live_context": {"is_live": mode == "live", "run_id": "", "project_slug": ""},
            "project_context": {"project_slug": "demo"},
            "session_context": {"run_id": "RUN-1", "project_slug": "demo", "is_historical": historical},
            "feed_policy": {
                "live_events_visible": True,
                "live_events_mutate_selected_context": mutates,
            },
            "warnings": [],
        },
    }


def test_validate_scoped_replay_accepts_expected_modes():
    assert validate_scoped_replay_payload(_scoped("state_replay", "live", mutates=True))["event_type"] == "state_replay"
    assert validate_scoped_replay_payload(_scoped("project_snapshot", "project", mutates=False))["event_type"] == "project_snapshot"
    assert validate_scoped_replay_payload(_scoped("session_replay", "replay", mutates=False, historical=True))["event_type"] == "session_replay"


def test_validate_scoped_replay_rejects_scope_masquerade():
    with pytest.raises(ValueError):
        validate_scoped_replay_payload(_scoped("state_replay", "replay", mutates=False, historical=True))
    with pytest.raises(ValueError):
        validate_scoped_replay_payload(_scoped("session_replay", "live", mutates=True))


def test_validate_scoped_replay_rejects_mutation_policy_mixing():
    with pytest.raises(ValueError):
        validate_scoped_replay_payload(_scoped("project_snapshot", "project", mutates=True))
    with pytest.raises(ValueError):
        validate_scoped_replay_payload(_scoped("session_replay", "replay", mutates=False, historical=False))
