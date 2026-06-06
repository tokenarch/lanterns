"""nightclaw_bridge.state -- deterministic folds and scoped projections over the event log."""
from __future__ import annotations
from typing import Iterable, Mapping, Any, Optional


def _text(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return _text(value).lower().replace("_", "-")


def _project_slug(row: Mapping[str, Any]) -> str:
    return _text(row.get("slug") or row.get("project_slug") or row.get("project"))


def _session_run_id(row: Mapping[str, Any]) -> str:
    return _text(row.get("run_id") or row.get("runid"))


def _is_active_project(row: Mapping[str, Any]) -> bool:
    status = _norm(row.get("status"))
    return status in {"active", "running"} or status == ""


def _provenance_flag(value: Any) -> str:
    if isinstance(value, Mapping):
        return _text(value.get("project_slug") or value.get("row") or value.get("outcome"))
    return _text(value)


def derive_scope_context(*,
                         active_projects: Optional[list[Mapping[str, Any]]] = None,
                         longrunner: Optional[Mapping[str, Any]] = None,
                         session: Optional[Mapping[str, Any]] = None,
                         session_history: Optional[list[Mapping[str, Any]]] = None,
                         mode: str = "live",
                         partial: bool = False,
                         selected_project_slug: str = "",
                         force_historical_session: bool = False) -> dict:
    """Return explicit live/project/session scope metadata for UI safety.

    This is intentionally not a recommendation engine. Its job is to keep live
    feed state, selected project state, and selected/replayed session state
    structurally separate so browsers do not have to infer whether fields are
    current, project-scoped, or historical.
    """
    active_projects = list(active_projects or [])
    session_history = list(session_history or [])
    lr = dict(longrunner or {})
    sess = dict(session or {})
    warnings: list[str] = []

    live_run_id = ""
    live_project_slug = ""
    live_actor = "none"
    live_source = "none"
    if mode == "live" and sess:
        live_run_id = _session_run_id(sess)
        live_project_slug = _project_slug(sess)
        live_actor = _text(sess.get("agent_type") or sess.get("agenttype") or "worker")
        live_source = _provenance_flag(sess.get("provenance")) or "telemetry"

    project_slug = _text(selected_project_slug or lr.get("slug") or lr.get("_slug"))
    project_source = "selected_project" if selected_project_slug else "longrunner" if project_slug else "none"
    if not project_slug and mode == "live" and live_project_slug:
        project_slug = live_project_slug
        project_source = "live_session"
    if not project_slug:
        active = next((r for r in active_projects if _is_active_project(r)), None)
        if active:
            project_slug = _project_slug(active)
            project_source = "active_project"

    session_run_id = _session_run_id(sess)
    session_project_slug = _project_slug(sess)
    session_source = _provenance_flag(sess.get("provenance")) or "none"
    is_historical = mode in {"replay", "session_replay"} or force_historical_session
    if is_historical and not session_source:
        session_source = "reconstructed" if partial else "replay_payload"
    if partial:
        warnings.append("partial_reconstruction")
    if session_source in {"inferred", "unknown"}:
        warnings.append("inferred_project_slug")

    if project_slug and session_project_slug and project_slug != session_project_slug:
        warnings.append("session_project_mismatch")
    if mode == "live" and session_history:
        for row in session_history:
            rid = _session_run_id(row)
            if rid and rid != live_run_id and _norm(row.get("outcome")) in {"running", ""}:
                warnings.append("multiple_running_sessions_visible")
                break

    selected_kind = "workspace"
    if mode in {"project", "project_snapshot"}:
        selected_kind = "project"
    elif mode in {"replay", "session_replay"}:
        selected_kind = "session"
    elif project_slug:
        selected_kind = "project"

    live_events_mutate_selected = mode == "live"
    return {
        "view_scope": {
            "mode": mode,
            "selected_kind": selected_kind,
        },
        "live_context": {
            "is_live": mode == "live",
            "run_id": live_run_id,
            "project_slug": live_project_slug,
            "actor": live_actor,
            "source": live_source,
        },
        "project_context": {
            "project_slug": project_slug,
            "phase": _text(lr.get("phase_name") or lr.get("phase")),
            "phase_status": _text(lr.get("phase_status") or lr.get("status")),
            "routing": _text(lr.get("routing")),
            "source": project_source,
        },
        "session_context": {
            "run_id": session_run_id,
            "project_slug": session_project_slug,
            "actor": _text(sess.get("agent_type") or sess.get("agenttype")),
            "is_historical": is_historical,
            "is_reconstructed": bool(partial),
            "source": session_source,
        },
        "feed_policy": {
            "live_events_visible": True,
            "live_events_mutate_selected_context": live_events_mutate_selected,
        },
        "warnings": sorted(set(warnings)),
    }


def fold_eventlog_views(events: Iterable[Mapping[str, Any]]) -> dict:
    """Build shared bridge projections from the raw event log.

    Returns a dict with:
      * snapshot: legacy normalized shape {sessions, ops_timeline}
      * runs: per-run metadata used by the live /sessions runtime payload
      * step_times: per-run emitted timestamps for the sessions timeline bars

    The goal is to keep ops-event folding semantics in one place even while the
    bridge still serves two external payload contracts.
    """
    snapshot: dict = {"sessions": {}, "ops_timeline": {}}
    runs: dict[str, dict] = {}
    step_times: dict[str, list[str]] = {}
    # Track (run_id, cmd, slug) open steps so a second event with exit_code
    # closes them in-place instead of duplicating timeline entries.
    open_steps: dict[tuple, dict] = {}

    for ev in events:
        t = ev.get("type")
        run = ev.get("run_id")
        if not run:
            continue
        if t == "sessionsevent":
            s = snapshot["sessions"].setdefault(run, {"kinds": []})
            s["kinds"].append(ev.get("kind"))
            continue
        if t != "opsstepevent":
            continue

        t_emitted = ev.get("t_emitted", "")
        if t_emitted and t_emitted not in step_times.setdefault(run, []):
            step_times[run].append(t_emitted)

        tl = snapshot["ops_timeline"].setdefault(run, [])
        key = (run, ev.get("cmd"), ev.get("slug"))
        if key in open_steps and "exit_code" in ev and "exit_code" not in open_steps[key]:
            open_steps[key]["exit_code"] = ev["exit_code"]
        else:
            step = {k: v for k, v in ev.items() if k != "type"}
            tl.append(step)
            if "exit_code" not in ev:
                open_steps[key] = step

        row = runs.setdefault(run, {
            "runid": run,
            "agenttype": ev.get("session") or "worker",
            "mutationcount": 0,
            "ts": t_emitted,
            "has_t0": False,
            "saw_t9": False,
            "last_exit_code": None,
        })
        if ev.get("slug") and not row.get("project_slug"):
            row["project_slug"] = ev.get("slug")
        tier = ev.get("tier", "")
        if tier == "T0":
            row["has_t0"] = True
            row["ts"] = t_emitted
        elif t_emitted:
            row["ts"] = t_emitted
        if tier == "T9":
            row["saw_t9"] = True
            row["last_exit_code"] = ev.get("exit_code")

    return {"snapshot": snapshot, "runs": runs, "step_times": step_times}


def fold_eventlog(events: Iterable[Mapping[str, Any]]) -> dict:
    return fold_eventlog_views(events)["snapshot"]
