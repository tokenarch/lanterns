"""nightclaw_bridge.sources — read-only adapters that surface repo
governance/audit/notification state to the monitor UI without coupling
the core engine to the bridge.

Everything in this module is read-only. Parsers tolerate missing files,
empty files, malformed or truncated entries, and always cap the number
of items they return so a very large file cannot blow up the ops path.
No parser writes to the filesystem or shells out — they only open a
file, read bytes, and return dicts.

The output shapes are tuned to the event vocabulary the shipped
apps/monitor/nightclaw-monitor.html already consumes (see
``handleEvent`` + the render helpers there). If the repo lacks a
source file we return an empty list; the UI shows its honest empty
state rather than fabricated data.
"""
from __future__ import annotations

import os
import re
import subprocess
import json
from typing import Any, Iterable, Optional

from nightclaw_common import preapprovals as pa_shared


# ---------------------------------------------------------------------------
# NOTIFICATIONS.md  →  list[{ts, message, priority, project, status}]
# ---------------------------------------------------------------------------

_NOTIF_HEADER_RE = re.compile(
    # Timestamp: three supported formats:
    #   [2026-04-21 09:00]   — bracketed, space-separated (legacy template)
    #   [2026-04-23T16:40:00Z] — bracketed ISO8601
    #   2026-04-23T16:40:00Z — bare ISO8601 (actual worker prompt format, no brackets)
    r"^\[?(?P<ts>[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9:]+Z?)\]?\s*\|\s*Priority:\s*(?P<prio>[^|]+?)\s*"
    r"(?:\|\s*Project:\s*(?P<project>[^|]+?)\s*)?"
    r"(?:\|\s*Status:\s*(?P<status>[^|]+?)\s*)?$"
)


def parse_notifications(path: str, *, max_entries: int = 40) -> list[dict]:
    """Parse NOTIFICATIONS.md and return the most recent alert entries.

    Each entry is a dict matching the UI's notifications inbox shape:
      {ts, message, priority, project, status}
    Entries flagged '[DONE …] ' at the start of the header line are
    filtered out — the inbox only shows unresolved items.
    """
    lines = _read_lines(path)
    if not lines:
        return []
    entries: list[dict] = []
    current: Optional[dict] = None
    for raw in lines:
        line = raw.rstrip("\n")
        # Skip archived/resolved entries (but flush the pending one first).
        if line.startswith("[DONE"):
            if current is not None:
                entries.append(current)
                current = None
            continue
        m = _NOTIF_HEADER_RE.match(line.strip())
        if m:
            if current is not None:
                entries.append(current)
            raw_status = (m.group("status") or "").strip()
            # Worker prompt writes message body inline after a literal '\n'
            # on the same header line, e.g.:
            #   ... | Status: SCR-FAIL \nSCR-05 FAIL: details here
            # Split on the literal two-character sequence backslash-n.
            if "\\n" in raw_status:
                status_part, _, msg_part = raw_status.partition("\\n")
            else:
                status_part, msg_part = raw_status, ""
            current = {
                "ts": _normalize_ts(m.group("ts")),
                "priority": (m.group("prio") or "").strip(),
                "project": (m.group("project") or "").strip(),
                "status": status_part.strip(),
                "message": msg_part.strip(),
            }
            continue
        if current is None:
            continue
        stripped = line.strip()
        if not stripped:
            # blank line → header only
            continue
        # Accumulate the body (first 3 substantive lines is plenty for UI).
        if current["message"]:
            current["message"] += " | " + stripped
        else:
            current["message"] = stripped
    if current is not None:
        entries.append(current)

    # Return the most recent entries, newest last in file, but UI reverses.
    return entries[-max_entries:]


def has_pending_phase_transition(entries: Iterable[dict]) -> list[dict]:
    """Return the subset of notification entries flagged as phase transitions.

    The admin CLI ``done <line>`` verb approves phase transitions when the
    targeted line mentions TRANSITION-HOLD / phase-transition / phase-complete.
    """
    out: list[dict] = []
    for e in entries:
        blob = " ".join((e.get("status", ""), e.get("message", ""))).upper()
        if ("TRANSITION-HOLD" in blob or "PHASE-TRANSITION" in blob
                or "PHASE-COMPLETE" in blob):
            out.append(e)
    return out


# ---------------------------------------------------------------------------
# audit/AUDIT-LOG.md  →  list[{ts, line, severity, type, result}]
# ---------------------------------------------------------------------------

_AUDIT_V19_RE = re.compile(
    r"^TASK:(?P<task>[^|]+)\|\s*TYPE:(?P<type>[^|]+?)\s*(?:\|\s*(?P<rest>.*))?$"
)
_AUDIT_RESULT_RE = re.compile(r"\bRESULT:\s*([A-Z_]+)")


def parse_audit_tail(path: str, *, count: int = 30) -> list[dict]:
    """Return the last `count` audit entries as structured dicts.

    Each entry: {line, ts, severity, type, result, task}
    Severity: 'ok' for PASS/SUCCESS, 'err' for FAIL/BLOCKED, else 'info'.
    """
    lines = _read_content_lines(path)
    entries: list[dict] = []
    for raw in lines[-max(count * 3, 200):]:
        line = raw.strip()
        if not line.startswith("TASK:"):
            continue
        m = _AUDIT_V19_RE.match(line)
        type_ = result = ""
        task = ""
        if m:
            task = m.group("task").strip()
            type_ = m.group("type").strip()
            rm = _AUDIT_RESULT_RE.search(line)
            if rm:
                result = rm.group(1).strip()
        severity = "info"
        up = result.upper()
        if up in ("PASS", "SUCCESS"):
            severity = "ok"
        elif up in ("FAIL", "BLOCKED"):
            severity = "err"
        entries.append({
            "line": line,
            "ts": _ts_from_run_id(task),
            "severity": severity,
            "type": type_,
            "result": result,
            "task": task,
        })
    return entries[-count:]


# ---------------------------------------------------------------------------
# audit/CHANGE-LOG.md  →  list[{file, field, old_val, new_val, ts, reason}]
# ---------------------------------------------------------------------------

def parse_change_log(path: str, *, count: int = 30) -> list[dict]:
    """Parse the pipe-delimited field-level change log.

    Format: field_path|old|new|agent|run_id|t_written|t_valid|reason|bundle
    Returns the UI shape: {file, field, old_val, new_val, ts, reason}.
    """
    lines = _read_content_lines(path)
    out: list[dict] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith(("#", "<!--", "---", "```", "FIELD:")):
            continue
        if "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            continue
        field_path = parts[0]
        old_val = parts[1] if len(parts) > 1 else ""
        new_val = parts[2] if len(parts) > 2 else ""
        run_id = parts[4] if len(parts) > 4 else ""
        ts = parts[5] if len(parts) > 5 else _ts_from_run_id(run_id)
        reason = parts[7] if len(parts) > 7 else ""
        bundle = parts[8] if len(parts) > 8 else ""
        file_, _, field = field_path.partition("#")
        if file_.upper().startswith("FILE:"):
            file_ = file_[5:]
        out.append({
            "file": file_,
            "field": field,
            "old_val": old_val,
            "new_val": new_val,
            "ts": ts,
            "reason": reason,
            "bundle": bundle,
            "run_id": run_id,
        })
    return out[-count:]


# ---------------------------------------------------------------------------
# audit/AUDIT-LOG.md (BUNDLE lines)  →  list[{bundle_name, ok, ts, run_id,
#                                              mutations_applied, guards_checked}]
# ---------------------------------------------------------------------------

def parse_bundle_history(audit_path: str, *, count: int = 10) -> list[dict]:
    """Scan AUDIT-LOG.md for TYPE:BUNDLE entries and adapt to the UI shape.

    The UI's ``renderBundles()`` expects: {bundle_name, ok, run_id,
    mutations_applied: [str], guards_checked: [str]}. Guards aren't
    carried by the v19 compact format; we leave them empty so the UI
    renders the row without a guard count instead of faking one.
    """
    lines = _read_content_lines(audit_path)
    out: list[dict] = []
    for raw in lines:
        line = raw.strip()
        if not line.startswith("TASK:") or "TYPE:BUNDLE" not in line:
            continue
        m = _AUDIT_V19_RE.match(line)
        if not m:
            continue
        task = m.group("task").strip()
        rest = m.group("rest") or ""
        rm = _AUDIT_RESULT_RE.search(line)
        result = (rm.group(1).strip().upper() if rm else "")
        bundle_name = _extract_kv(line, "BUNDLE") or _extract_kv(rest, "BUNDLE") or "?"
        file_ = _extract_kv(line, "FILE") or ""
        mutations = [file_] if file_ else []
        run_id = task.split(".", 1)[0]
        out.append({
            "bundle_name": bundle_name,
            "ok": result in ("SUCCESS", "PASS"),
            "ts": _ts_from_run_id(run_id),
            "run_id": run_id,
            "mutations_applied": mutations,
            "guards_checked": [],
        })
    return out[-count:]


# ---------------------------------------------------------------------------
# audit/SESSION-REGISTRY.md + audit/AUDIT-LOG.md + session_close_RUN-*.json
#   → canonical completed-session index for the sessions page
# ---------------------------------------------------------------------------

_SESSION_REGISTRY_COMPACT_RE = re.compile(
    r"^(?P<run>RUN-\d{8}-\d{3})\s*\|\s*(?P<agent>[^|]+?)\s*\|\s*(?P<model>[^|]+?)\s*\|\s*(?P<tokens>[^|]+?)\s*\|\s*(?P<integrity>[^|]+?)\s*\|\s*(?P<outcome>.+)$"
)


def _coerce_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip().lower().replace(",", "")
    if not text:
        return None
    mult = 1
    if text.endswith("k"):
        mult = 1000
        text = text[:-1]
    try:
        return int(float(text) * mult)
    except ValueError:
        return None


def _coerce_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    if text.startswith("$"):
        text = text[1:]
    try:
        return float(text)
    except ValueError:
        return None


def _parse_token_summary(raw: str) -> dict:
    """Best-effort normalization for legacy free-text token summaries.

    SESSION-REGISTRY.md historically stores values like ``4.0k in / 49 out``,
    ``173k tokens``, ``~6500``, ``unknown``, or ``n/a``. Keep the original text
    for display, but expose numeric fields whenever the string is parseable so
    the monitor can aggregate without guessing in the browser.
    """
    text = (raw or "").strip()

    def to_int(value: str) -> Optional[int]:
        value = value.strip().lower().replace(",", "")
        mult = 1
        if value.endswith("k"):
            mult = 1000
            value = value[:-1]
        try:
            return int(float(value) * mult)
        except ValueError:
            return None

    result = {
        "text": text,
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "cost_usd": None,
    }
    if not text or text.lower() in {"unknown", "n/a", "na", "—", "-"}:
        return result
    in_m = re.search(r"\bin\s*[=:]\s*(~?\d+(?:\.\d+)?k?)", text, re.IGNORECASE)
    if not in_m:
        in_m = re.search(r"(~?\d+(?:\.\d+)?k?)\s*in\b", text, re.IGNORECASE)
    out_m = re.search(r"\bout\s*[=:]\s*(~?\d+(?:\.\d+)?k?)", text, re.IGNORECASE)
    if not out_m:
        out_m = re.search(r"(~?\d+(?:\.\d+)?k?)\s*out\b", text, re.IGNORECASE)
    if in_m:
        result["input_tokens"] = to_int(in_m.group(1).lstrip("~"))
    if out_m:
        result["output_tokens"] = to_int(out_m.group(1).lstrip("~"))
    total_m = re.search(r"(?:total\s*[=:]\s*|\b)(~?\d+(?:\.\d+)?k?)\s*(?:tokens?|total)?\b", text, re.IGNORECASE)
    if result["input_tokens"] is not None or result["output_tokens"] is not None:
        result["total_tokens"] = (result["input_tokens"] or 0) + (result["output_tokens"] or 0)
    elif total_m:
        result["total_tokens"] = to_int(total_m.group(1).lstrip("~"))
    cost_m = re.search(r"(?:cost(?:_usd)?|usd)\s*[=:]\s*\$?(\d+(?:\.\d+)?)|\$(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if cost_m:
        raw_cost = cost_m.group(1) or cost_m.group(2)
        try:
            result["cost_usd"] = float(raw_cost)
        except (TypeError, ValueError):
            pass
    return result


def parse_session_registry(path: str, *, max_entries: int = 200) -> list[dict]:
    """Parse compact recent session-registry rows.

    Output shape: {run_id, agent_type, model, tokens, integrity, outcome_summary, ts}
    """
    lines = _read_content_lines(path)
    out: list[dict] = []
    for raw in lines:
        line = raw.strip()
        m = _SESSION_REGISTRY_COMPACT_RE.match(line)
        if not m:
            continue
        run_id = m.group("run").strip()
        token_summary = _parse_token_summary(m.group("tokens"))
        out.append({
            "run_id": run_id,
            "agent_type": m.group("agent").strip(),
            "model": m.group("model").strip(),
            "tokens": m.group("tokens").strip(),
            "token_usage": token_summary,
            "input_tokens": token_summary["input_tokens"],
            "output_tokens": token_summary["output_tokens"],
            "total_tokens": token_summary["total_tokens"],
            "cost_usd": token_summary["cost_usd"],
            "integrity": m.group("integrity").strip(),
            "outcome_summary": m.group("outcome").strip(),
            "ts": _ts_from_run_id(run_id),
        })
    return out[-max_entries:]


def parse_audit_session_closes(path: str) -> dict[str, dict]:
    """Return run_id -> {result, ts} for TYPE:SESSION_CLOSE audit rows."""
    out: dict[str, dict] = {}
    for raw in _read_content_lines(path):
        line = raw.strip()
        if not line.startswith("TASK:") or "TYPE:SESSION_CLOSE" not in line:
            continue
        m = _AUDIT_V19_RE.match(line)
        if not m:
            continue
        task = m.group("task").strip()
        run_id = task.split(".", 1)[0]
        rm = _AUDIT_RESULT_RE.search(line)
        result = (rm.group(1).strip().upper() if rm else "")
        out[run_id] = {"result": result, "ts": _ts_from_run_id(run_id)}
    return out


def parse_session_close_artifacts(workspace: str) -> dict[str, dict]:
    """Best-effort enrichment from session_close_RUN-*.json artifacts."""
    out: dict[str, dict] = {}
    try:
        names = sorted(n for n in os.listdir(workspace) if n.startswith("session_close_RUN-") and n.endswith(".json"))
    except Exception:
        return out
    for name in names:
        path = os.path.join(workspace, name)
        try:
            data = json.loads(open(path, "r", encoding="utf-8").read())
        except Exception:
            continue
        run_id = str(data.get("run_id") or "").strip()
        if not run_id:
            continue
        memory_entry = str(data.get("memory_entry") or "")
        session_entry = str(data.get("session_entry") or "")
        ts = str(data.get("ts") or "").strip()
        m_ts = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)", memory_entry)
        if not ts and m_ts:
            ts = m_ts.group(1)
        project_slug = str(data.get("project_slug") or data.get("project") or "").strip()
        m_proj = re.search(r"project=([a-z0-9][a-z0-9-]*)", memory_entry)
        if not project_slug and m_proj:
            project_slug = m_proj.group(1)
        if not project_slug:
            m_proj = re.search(r"project=([a-z0-9][a-z0-9-]*)", session_entry)
            if m_proj:
                project_slug = m_proj.group(1)
        token_usage = _parse_token_summary(str(data.get("tokens") or ""))
        structured_usage = data.get("token_usage")
        if isinstance(structured_usage, dict):
            merged_usage = dict(token_usage)
            structured_text = structured_usage.get("text")
            if structured_text not in (None, ""):
                merged_usage["text"] = str(structured_text)
            for key in ("input_tokens", "output_tokens", "total_tokens"):
                value = _coerce_int(structured_usage.get(key))
                if value is not None:
                    merged_usage[key] = value
            value = _coerce_float(structured_usage.get("cost_usd"))
            if value is not None:
                merged_usage["cost_usd"] = value
            if merged_usage["total_tokens"] is None and (
                merged_usage["input_tokens"] is not None or merged_usage["output_tokens"] is not None
            ):
                merged_usage["total_tokens"] = (merged_usage["input_tokens"] or 0) + (merged_usage["output_tokens"] or 0)
            token_usage = merged_usage
        explicit_input = _coerce_int(data.get("input_tokens"))
        explicit_output = _coerce_int(data.get("output_tokens"))
        explicit_total = _coerce_int(data.get("total_tokens"))
        explicit_cost = _coerce_float(data.get("cost_usd"))
        if explicit_input is not None:
            token_usage["input_tokens"] = explicit_input
        if explicit_output is not None:
            token_usage["output_tokens"] = explicit_output
        if explicit_total is not None:
            token_usage["total_tokens"] = explicit_total
        elif explicit_input is not None or explicit_output is not None:
            token_usage["total_tokens"] = (explicit_input or 0) + (explicit_output or 0)
        if explicit_cost is not None:
            token_usage["cost_usd"] = explicit_cost
        out[run_id] = {
            "ts": ts or _ts_from_run_id(run_id),
            "project_slug": project_slug,
            "session_key": str(data.get("session_key") or data.get("session") or "").strip(),
            "model": str(data.get("model") or "").strip(),
            "tokens": str(data.get("tokens") or "").strip(),
            "token_usage": token_usage,
            "input_tokens": token_usage["input_tokens"],
            "output_tokens": token_usage["output_tokens"],
            "total_tokens": token_usage["total_tokens"],
            "cost_usd": token_usage["cost_usd"],
            "session_entry": session_entry,
            "memory_entry": memory_entry,
        }
    return out


def list_project_slugs(workspace: str) -> list[str]:
    """Return known project slugs from PROJECTS/ directory."""
    root = os.path.join(workspace, "PROJECTS")
    try:
        names = [n for n in os.listdir(root) if os.path.isdir(os.path.join(root, n))]
    except Exception:
        return []
    return sorted(n for n in names if re.match(r"^[a-z0-9][a-z0-9-]*$", n))


def infer_project_slug(*texts: str, known_slugs: Optional[list[str]] = None) -> str:
    """Best-effort slug inference from recorded summary/body text."""
    corpus = " | ".join(t for t in texts if t).lower()
    if not corpus:
        return ""
    known = list(known_slugs or [])
    allow = set(known) | {"idle-cycle", "notifications", "system-idle"}
    for slug in known:
        if slug.lower() in corpus:
            return slug
    m = re.search(r"project=([a-z0-9][a-z0-9-]*)", corpus)
    if m:
        candidate = m.group(1)
        return candidate if candidate in allow else ""
    m = re.search(r"project\s+([a-z0-9][a-z0-9-]*)", corpus)
    if m:
        candidate = m.group(1)
        return candidate if candidate in allow else ""
    return ""


# ---------------------------------------------------------------------------
# orchestration-os/OPS-PREAPPROVAL.md  →  list[{id, status, expires,
#                                                action_class, scope,
#                                                condition, boundary}]
# ---------------------------------------------------------------------------

_PA_HEADER_RE = re.compile(
    r"^##\s*(?P<id>PA-[0-9A-Za-z]+)\s*\|\s*Status:\s*(?P<status>[^|]+?)\s*"
    r"(?:\|\s*Expires:\s*(?P<expires>.*?))?\s*$"
)


def parse_preapprovals(path: str, *, max_entries: int = 32) -> list[dict]:
    """Extract real pre-approval entries from OPS-PREAPPROVAL.md.

    Phase A behavior:
      * only entries in the "Active Pre-Approvals" section are operational
      * example blocks later in the document are ignored
      * returned rows include live/effective status fields aligned with the
        engine's executable semantics
    """
    lines = _read_lines(path)
    in_active_section = False
    out: list[dict] = []
    current: Optional[dict] = None
    now = pa_shared.now_utc()

    def _finalize(entry: Optional[dict]) -> Optional[dict]:
        if entry is None:
            return None
        is_live = pa_shared.preapproval_is_active(entry.get("status"), entry.get("expires"), now=now)
        status = (entry.get("status") or "").strip()
        effective = "ACTIVE" if is_live else ("EXPIRED" if status.upper() == "ACTIVE" else status)
        entry["is_live"] = is_live
        entry["effective_status"] = effective
        return entry

    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()
        if stripped.lower().startswith("## active pre-approvals"):
            in_active_section = True
            current = None
            continue
        if in_active_section and stripped.startswith("## ") and stripped.lower() in (
            "## approved action classes",
            "## usage example — overnight run setup",
            "## conservative mode (no pre-approvals active)",
            "## security constraints on this file",
        ):
            if current is not None:
                finalized = _finalize(current)
                if finalized is not None:
                    out.append(finalized)
                current = None
            break
        if not in_active_section:
            continue
        m = _PA_HEADER_RE.match(stripped)
        if m:
            if current is not None:
                finalized = _finalize(current)
                if finalized is not None:
                    out.append(finalized)
            current = {
                "id": m.group("id").strip(),
                "status": m.group("status").strip(),
                "expires": (m.group("expires") or "").strip() or "—",
                "action_class": "",
                "scope": "",
                "condition": "",
                "boundary": "",
            }
            continue
        if current is None:
            continue
        if stripped.startswith("## "):
            finalized = _finalize(current)
            if finalized is not None:
                out.append(finalized)
            current = None
            continue
        for key, label in (
            ("action_class", "**Action class:**"),
            ("scope",        "**Scope:**"),
            ("condition",    "**Condition:**"),
            ("boundary",     "**Boundary:**"),
        ):
            if stripped.startswith(label):
                current[key] = stripped[len(label):].strip()
                break
    if current is not None:
        finalized = _finalize(current)
        if finalized is not None:
            out.append(finalized)
    return out[:max_entries]


# ---------------------------------------------------------------------------
# audit/APPROVAL-CHAIN.md  →  list[{pa_id, invocation, ts, result, by,
#                                    action}]
# ---------------------------------------------------------------------------

_PA_INVOCATION_RE = re.compile(
    r"^##\s*\[?(?P<pa>PA-[0-9A-Za-z]+)\]?-INVOCATION-\[?(?P<n>[0-9A-Za-z]+)\]?\s*"
    r"\|\s*(?P<ts>[^\s|]+)\s*$"
)

_PA_COMPACT_INVOCATION_RE = re.compile(
    r"^(?P<pa>PA-[0-9A-Za-z]+)-INV-(?P<n>[0-9A-Za-z]+)\s*\|\s*(?P<fields>.+)$"
)


def _parse_pipe_kv_fields(blob: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in blob.split("|"):
        key, sep, value = part.strip().partition("=")
        if sep and key:
            out[key.strip().lower()] = value.strip()
    return out


def parse_approval_chain(path: str, *, max_entries: int = 20) -> list[dict]:
    """Return recent PA invocation blocks.

    Supports both the documented block format and the compact invocation rows
    produced by older bundle flows, e.g. ``PA-003-INV-008 | action=...``.
    """
    lines = _read_lines(path)
    out: list[dict] = []
    current: Optional[dict] = None
    for raw in lines:
        line = raw.rstrip("\n")
        cm = _PA_COMPACT_INVOCATION_RE.match(line.strip())
        if cm:
            if current is not None:
                out.append(current)
                current = None
            fields = _parse_pipe_kv_fields(cm.group("fields"))
            out.append({
                "pa_id": cm.group("pa"),
                "invocation": cm.group("n"),
                "ts": fields.get("ts", ""),
                "by": fields.get("by", ""),
                "action": fields.get("action", ""),
                "result": fields.get("result", ""),
                "slug": fields.get("slug", ""),
                "successor": fields.get("successor", ""),
                "format": "compact",
            })
            continue
        m = _PA_INVOCATION_RE.match(line.strip())
        if m:
            if current is not None:
                out.append(current)
            current = {
                "pa_id": m.group("pa"),
                "invocation": m.group("n"),
                "ts": m.group("ts"),
                "by": "",
                "action": "",
                "result": "",
                "slug": "",
                "successor": "",
                "format": "block",
            }
            continue
        if current is None:
            continue
        stripped = line.strip()
        if stripped.startswith("## "):
            out.append(current)
            current = None
            continue
        for key, label in (
            ("by",     "**Invoked by:**"),
            ("action", "**Action authorized:**"),
            ("result", "**Result:**"),
        ):
            if stripped.startswith(label):
                current[key] = stripped[len(label):].strip()
                break
    if current is not None:
        out.append(current)
    return out[-max_entries:]


# ---------------------------------------------------------------------------
# ACTIVE-PROJECTS.md  →  list[{priority, slug, phase, status, last_pass,
#                               escalation}]
# ---------------------------------------------------------------------------

def parse_active_projects(path: str) -> list[dict]:
    """Parse the markdown scoreboard table."""
    lines = _read_lines(path)
    out: list[dict] = []
    seen_header = False
    for raw in lines:
        line = raw.rstrip("\n").strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not seen_header:
            # First row with 'Priority' / 'Project Slug' is header
            if any("Priority" in c for c in cells) and any("Slug" in c for c in cells):
                seen_header = True
            continue
        # skip separator row of dashes
        if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
            continue
        # Only rows with 7 cells match the scoreboard shape.
        if len(cells) < 7:
            continue
        priority, slug, path_, phase, status, last_pass, escalation = cells[:7]
        # Skip the placeholder "(no projects yet)" row
        if slug.startswith("_(") or slug == "—":
            continue
        out.append({
            "priority": priority,
            "slug": slug,
            "longrunner_path": path_,
            "phase": phase,
            "status": status,
            "last_pass": last_pass,
            "escalation": escalation,
        })
    return out


# ---------------------------------------------------------------------------
# PROJECTS/<slug>/LONGRUNNER.md  →  UI-shaped longrunner dict
# ---------------------------------------------------------------------------

def _parse_longrunner_md(path: str) -> dict:
    """Parse LONGRUNNER.md directly, extracting YAML blocks under each section.

    Reads ## Current Phase, ## Last Pass, ## Next Pass, ## Blockers.
    Returns a flat dict keyed the same way extract_longrunner returns.
    """
    try:
        body = open(path, encoding="utf-8").read()
    except Exception:
        return {}

    def _yaml_block(section_header: str) -> dict:
        """Extract the first ```yaml block under a given ## header."""
        pat = re.compile(
            r"##\s+" + re.escape(section_header) + r"\s*\n.*?```yaml\s*\n(.*?)```",
            re.DOTALL | re.IGNORECASE,
        )
        m = pat.search(body)
        if not m:
            return {}
        block = m.group(1)
        # Simple key: value parser — handles nested keys like phase.name
        result: dict = {}
        _parse_yaml_flat(block, result, prefix="")
        return result

    def _parse_yaml_flat(text: str, out: dict, prefix: str) -> None:
        """Flatten YAML-ish key: value lines into dot-notation dict."""
        indent_stack: list[tuple[int, str]] = []  # (indent, prefix)
        for raw in text.splitlines():
            if not raw.strip() or raw.strip().startswith("#"):
                continue
            stripped = raw.lstrip()
            indent = len(raw) - len(stripped)
            # Pop stack entries that are deeper
            while indent_stack and indent_stack[-1][0] >= indent:
                indent_stack.pop()
            cur_prefix = (indent_stack[-1][1] + ".") if indent_stack else ""
            if prefix:
                cur_prefix = prefix + "." + cur_prefix if cur_prefix else prefix + "."
            if ":" not in stripped:
                continue
            k, _, v = stripped.partition(":")
            k = k.strip().strip('"\'')
            v = v.strip().strip('"\'')
            full_key = (cur_prefix + k).strip(".")
            if v and v not in ("~", "null", "[]"):
                out[full_key] = v
            else:
                # Might be a parent key — push onto stack
                indent_stack.append((indent, full_key))

    cp  = _yaml_block("Current Phase")
    lp  = _yaml_block("Last Pass")
    np_ = _yaml_block("Next Pass")

    open_questions_pat = re.compile(
        r"##\s+Open Questions\s*\n(.*?)(?=\n##|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    open_questions: list[str] = []
    oqm = open_questions_pat.search(body)
    if oqm:
        for row in oqm.group(1).splitlines():
            stripped = row.strip()
            if not stripped.startswith("- "):
                continue
            item = stripped[2:].strip()
            if item:
                open_questions.append(item)

    # Normalise: the YAML nests under phase: / last_pass: / next_pass:
    # After flattening we get keys like "phase.name", "last_pass.date" etc.
    ph = {k.split(".", 1)[1]: v for k, v in cp.items()  if "." in k}
    la = {k.split(".", 1)[1]: v for k, v in lp.items()  if "." in k}
    nx = {k.split(".", 1)[1]: v for k, v in np_.items() if "." in k}

    # Blockers table — any non-empty rows
    blocker_pat = re.compile(
        r"##\s+Blockers\s*\n.*?\|\s*Blocker\s*\|.*?\n\|[-| ]+\|\n(.*?)(?=\n##|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    blockers: list[str] = []
    bm = blocker_pat.search(body)
    if bm:
        for row in bm.group(1).splitlines():
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            if cells and cells[0] and cells[0] not in ("", "Blocker"):
                blockers.append(cells[0])

    tools_raw = nx.get("tools_required", "")
    # Strip YAML list brackets if present
    tools_raw = tools_raw.strip("[]").replace('"', '').replace("'", "")

    weak = la.get("weak_pass", "").lower() == "true"
    valid = la.get("validation_passed", "").lower() == "true"

    return {
        "phase_name":      ph.get("name", ""),
        "phase_objective": ph.get("objective", ""),
        "phase_stop":      ph.get("stop_condition", ""),
        "phase_status":    ph.get("status", ""),
        "phase_successor": ph.get("successor", ""),
        "next_pass":       nx.get("objective", ""),
        "next_tier":       nx.get("model_tier", ""),
        "next_budget":     nx.get("context_budget", ""),
        "next_tools":      tools_raw,
        "last_objective":  la.get("objective", ""),
        "last_output":     la.get("output_files", ""),
        "last_quality":    "weak" if weak else ("ok" if valid else ""),
        "last_date":       la.get("date", ""),
        "routing":         "",
        "is_draft":        "",
        "has_blockers":    "true" if blockers else "false",
        "blockers":        blockers,
        "open_questions":  open_questions,
        "pa_active":       "",
    }


def extract_longrunner(workspace: str, slug: str,
                       *, timeout: float = 5.0) -> Optional[dict]:
    """Extract longrunner state for slug.

    Strategy:
      1. Parse LONGRUNNER.md directly (full fidelity, no subprocess).
      2. Supplement with ops-script flat keys (routing, is_draft, etc.)
         if nightclaw-ops.py is available — those override blanks only.
    """
    lr_path = os.path.join(workspace, "PROJECTS", slug, "LONGRUNNER.md")
    result = _parse_longrunner_md(lr_path) if os.path.isfile(lr_path) else {}

    # Supplement with ops-script output for keys it uniquely provides
    ops_py = os.path.join(workspace, "scripts", "nightclaw-ops.py")
    if os.path.isfile(ops_py):
        import sys as _sys
        try:
            p = subprocess.run(
                [_sys.executable, ops_py, "longrunner-extract", slug],
                cwd=workspace, capture_output=True, text=True, timeout=timeout,
                encoding="utf-8",
                env={**os.environ, "NIGHTCLAW_NO_TELEMETRY": "1",
                     "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
            )
            if p.returncode == 0:
                kv: dict[str, str] = {}
                for line in (p.stdout or "").splitlines():
                    if "=" in line:
                        k, _, v = line.partition("=")
                        kv[k.strip()] = v.strip()
                # Ops script has authoritative routing / is_draft / has_blockers
                for field, key in [("routing", "routing"),
                                   ("is_draft", "is_draft"),
                                   ("has_blockers", "has_blockers"),
                                   ("next_budget", "next_pass.context_budget")]:
                    if key in kv:
                        result[field] = kv[key]
        except Exception:
            pass

    # Supplement with ACTIVE-PROJECTS.md runtime status and escalation.
    # The LONGRUNNER.md yaml only knows phase.status (COMPLETE/active/etc.),
    # but the dispatch table carries the live orchestrator state such as
    # TRANSITION-HOLD and the escalation_pending token that drives the
    # monitor's phase-transition "done" button.
    ap_path = os.path.join(workspace, "ACTIVE-PROJECTS.md")
    if os.path.isfile(ap_path):
        try:
            ap_rows = parse_active_projects(ap_path)
            ap_row = next(
                (r for r in ap_rows if r.get("slug", "").strip() == slug), None
            )
            if ap_row:
                active_status = ap_row.get("status", "").strip()
                escalation = ap_row.get("escalation", "").strip()
                if active_status:
                    result["active_status"] = active_status
                if escalation and escalation.lower() not in ("none", "—", "-", ""):
                    result["escalation_pending"] = escalation
        except Exception:
            pass

    if result:
        result["slug"] = slug  # Always stamp slug so the monitor can display it
    return result if result else None


# ---------------------------------------------------------------------------
# scripts/nightclaw-ops.py scr-verify  →  UI-shaped SCR dict
# ---------------------------------------------------------------------------

_SCR_LINE_RE = re.compile(
    r"^(?:SCR-(?P<num>\d+)|(?P<cl>CL\d+)):(?P<status>PASS|FAIL|SKIP|INFO)(?:\s+(?P<detail>.*))?$"
)

_AUDIT_SPINE_ROW_RE = re.compile(
    r"^(?P<status>CLEAN_PASS|ROUTING_HALT|CRASH|UNKNOWN):(?P<run>RUN-\d{8}-\d{3})(?:(?::|\s+)(?P<detail>.*))?$"
)
_AUDIT_SPINE_SUMMARY_RE = re.compile(
    r"^SUMMARY:\s*clean=(?P<clean>\d+)\s+crashes=(?P<crashes>\d+)\s+routing_halts=(?P<routing_halts>\d+)"
)
_AUDIT_ANOMALY_RE = re.compile(
    r"^ANOMALY:(?P<severity>[^:]+):(?P<type>[^:]+)(?::(?P<detail>.*))?$"
)
_CRASH_DETECT_RE = re.compile(
    r"^(?P<status>CRASH|ROUTING_HALT):(?P<run>RUN-\d{8}-\d{3})(?::(?P<detail>.*))?$"
)


def parse_scr_verify_output(stdout: str) -> Optional[dict]:
    """Parse ``nightclaw-ops.py scr-verify`` output for monitor rendering.

    Shape: {ts, checks:{SCR-NN: bool}, statuses:{SCR-NN: str}, details:{SCR-NN: str}, passed, failed}
    ``checks`` maps each rule to True (PASS) or False (FAIL only).
    INFO and SKIP rules are excluded from checks so they never render red.
    ``statuses`` carries the raw status string for all rules so the UI can
    distinguish PASS / FAIL / INFO / SKIP and colour them appropriately.
    Lines the UI does not key on (indented context, CL5/RESULT trailers) are
    ignored rather than fabricated into fields.
    """
    checks: dict[str, bool] = {}
    statuses: dict[str, str] = {}
    details: dict[str, str] = {}
    for line in (stdout or "").splitlines():
        m = _SCR_LINE_RE.match(line.strip())
        if not m:
            continue
        # Build key: SCR-NN for numbered rules, raw CL5/CLN for CL checks.
        if m.group('num') is not None:
            key = f"SCR-{int(m.group('num')):02d}"
        else:
            key = m.group('cl')  # e.g. "CL5"
        status = m.group("status")
        detail = (m.group("detail") or "").strip()
        statuses[key] = status
        # INFO and SKIP are not failures — exclude from checks dict so the
        # monitor never renders them red. PASS → True, FAIL → False.
        if status in ("PASS", "FAIL"):
            checks[key] = (status == "PASS")
        if detail:
            details[key] = f"{status}: {detail}"
        else:
            details[key] = status
    if not statuses:
        return None
    passed = sum(1 for s in statuses.values() if s == "PASS")
    failed = sum(1 for s in statuses.values() if s == "FAIL")
    import datetime
    return {
        "event_type": "scr_verify_result",
        "checks": checks,
        "statuses": statuses,
        "details": details,
        "passed": passed,
        "failed": failed,
        "ts": datetime.datetime.now(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def parse_audit_spine_output(stdout: str) -> dict:
    """Parse ``nightclaw-ops.py audit-spine`` into typed run evidence.

    The engine command is authoritative for run sequencing. Keep raw lines for
    drill-down, but expose counts and per-run statuses so the monitor can stop
    treating routing halts / unknown manager-only paths as anonymous text.
    """
    rows: list[dict] = []
    summary = {"clean": 0, "crashes": 0, "routing_halts": 0, "unknown": 0}
    raw_lines: list[str] = []
    for raw in (stdout or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        raw_lines.append(line)
        sm = _AUDIT_SPINE_SUMMARY_RE.match(line)
        if sm:
            summary["clean"] = int(sm.group("clean"))
            summary["crashes"] = int(sm.group("crashes"))
            summary["routing_halts"] = int(sm.group("routing_halts"))
            continue
        m = _AUDIT_SPINE_ROW_RE.match(line)
        if not m:
            continue
        status = m.group("status")
        if status == "UNKNOWN":
            summary["unknown"] += 1
        rows.append({
            "run_id": m.group("run"),
            "status": status,
            "detail": (m.group("detail") or "").strip(),
            "line": line,
        })
    if not summary["clean"]:
        summary["clean"] = sum(1 for r in rows if r["status"] == "CLEAN_PASS")
    if not summary["routing_halts"]:
        summary["routing_halts"] = sum(1 for r in rows if r["status"] == "ROUTING_HALT")
    if not summary["crashes"]:
        summary["crashes"] = sum(1 for r in rows if r["status"] == "CRASH")
    return {
        "event_type": "engine_audit_result",
        "kind": "audit_spine",
        "summary": summary,
        "rows": rows,
        "raw_lines": raw_lines,
    }


def parse_audit_anomalies_output(stdout: str) -> dict:
    """Parse ``nightclaw-ops.py audit-anomalies`` output.

    Proven shapes from the engine are ``CLEAN`` or one/more
    ``ANOMALY:<severity>:<type>:<details>`` rows followed by
    ``TOTAL_ANOMALIES:<n>``.
    """
    rows: list[dict] = []
    raw_lines: list[str] = []
    total: Optional[int] = None
    clean = False
    reason = ""
    for raw in (stdout or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        raw_lines.append(line)
        if line.startswith("CLEAN"):
            clean = True
            _, _, reason = line.partition("reason=")
            continue
        if line.startswith("TOTAL_ANOMALIES:"):
            try:
                total = int(line.split(":", 1)[1])
            except ValueError:
                total = None
            continue
        m = _AUDIT_ANOMALY_RE.match(line)
        if not m:
            continue
        rows.append({
            "severity": m.group("severity"),
            "type": m.group("type"),
            "detail": (m.group("detail") or "").strip(),
            "line": line,
        })
    if total is None:
        total = len(rows)
    return {
        "event_type": "engine_audit_result",
        "kind": "audit_anomalies",
        "ok": clean and not rows,
        "summary": {"anomalies": total, "clean": 1 if clean and not rows else 0},
        "rows": rows,
        "raw_lines": raw_lines,
        "reason": reason,
    }


def parse_crash_detect_output(stdout: str) -> dict:
    """Parse ``nightclaw-ops.py crash-detect`` output.

    Proven shapes from the engine are ``CLEAN`` or ``CRASH:<run>:...`` rows,
    optional ``TOTAL_CRASHES:<n>``, and optional ``ROUTING_HALT:<run>`` rows.
    """
    rows: list[dict] = []
    raw_lines: list[str] = []
    clean = False
    reason = ""
    total_crashes: Optional[int] = None
    for raw in (stdout or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        raw_lines.append(line)
        if line.startswith("CLEAN"):
            clean = True
            _, _, reason = line.partition("reason=")
            continue
        if line.startswith("TOTAL_CRASHES:"):
            try:
                total_crashes = int(line.split(":", 1)[1])
            except ValueError:
                total_crashes = None
            continue
        m = _CRASH_DETECT_RE.match(line)
        if not m:
            continue
        rows.append({
            "run_id": m.group("run"),
            "status": m.group("status"),
            "detail": (m.group("detail") or "").strip(),
            "line": line,
        })
    crashes = total_crashes if total_crashes is not None else sum(1 for r in rows if r["status"] == "CRASH")
    routing_halts = sum(1 for r in rows if r["status"] == "ROUTING_HALT")
    return {
        "event_type": "engine_audit_result",
        "kind": "crash_detect",
        "ok": clean and crashes == 0,
        "summary": {"crashes": crashes, "routing_halts": routing_halts, "clean": 1 if clean and not rows else 0},
        "rows": rows,
        "raw_lines": raw_lines,
        "reason": reason,
    }


def _run_ops_command(workspace: str, args: list[str], *, timeout: float) -> Optional[subprocess.CompletedProcess]:
    ops_py = os.path.join(workspace, "scripts", "nightclaw-ops.py")
    if not os.path.isfile(ops_py):
        return None
    # Use sys.executable so the bridge and ops share the same Python interpreter.
    # "python3" is not guaranteed on Windows (may be "python" or "py"), and using
    # a hard-coded name causes FileNotFoundError which is silently caught → None,
    # producing the misleading "ops.py not found" error in the monitor console.
    #
    # Force UTF-8 I/O on the child process. On Windows the default stdout
    # encoding is the system codepage (typically cp1252), which cannot encode
    # Unicode characters like → (U+2192) that appear in SCR-07 REF lines.
    # Without this, ops.py crashes after printing "SCR-07:INFO …" and before
    # the REF lines, so SCR-08 through CL5 are never emitted — the monitor
    # shows only 6p instead of 11p.
    import sys as _sys
    try:
        return subprocess.run(
            [_sys.executable, ops_py, *args],
            cwd=workspace, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8",
            env={**os.environ, "NIGHTCLAW_NO_TELEMETRY": "1",
                 "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
    except Exception:
        return None


def run_scr_verify(workspace: str, *, timeout: float = 30.0) -> Optional[dict]:
    """Invoke ops.py scr-verify and return a dict the monitor can render."""
    p = _run_ops_command(workspace, ["scr-verify"], timeout=timeout)
    if p is None:
        return None
    return parse_scr_verify_output(p.stdout or "")


def run_audit_spine(workspace: str, *, timeout: float = 10.0) -> Optional[dict]:
    """Invoke ops.py audit-spine and return typed engine-audit evidence."""
    p = _run_ops_command(workspace, ["audit-spine"], timeout=timeout)
    if p is None:
        return None
    result = parse_audit_spine_output(p.stdout or "")
    result["ok"] = p.returncode == 0
    return result


def run_audit_anomalies(workspace: str, *, timeout: float = 10.0) -> Optional[dict]:
    """Invoke ops.py audit-anomalies and return typed anomaly evidence."""
    p = _run_ops_command(workspace, ["audit-anomalies"], timeout=timeout)
    if p is None:
        return None
    result = parse_audit_anomalies_output(p.stdout or "")
    result["ok"] = p.returncode == 0 and not result.get("rows")
    return result


def run_crash_detect(workspace: str, *, timeout: float = 10.0) -> Optional[dict]:
    """Invoke ops.py crash-detect and return typed crash/routing evidence."""
    p = _run_ops_command(workspace, ["crash-detect"], timeout=timeout)
    if p is None:
        return None
    result = parse_crash_detect_output(p.stdout or "")
    result["ok"] = p.returncode == 0 and result.get("summary", {}).get("crashes", 0) == 0
    return result


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _read_lines(path: str) -> list[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.readlines()
    except (FileNotFoundError, IsADirectoryError, PermissionError):
        return []
    except OSError:
        return []


def _read_content_lines(path: str) -> list[str]:
    """Return non-empty, non-comment lines."""
    out: list[str] = []
    for line in _read_lines(path):
        s = line.strip()
        if not s:
            continue
        if s.startswith(("#", "<!--", "```", "---")):
            continue
        out.append(line)
    return out


def _ts_from_run_id(run_id: str) -> str:
    """Best-effort: RUN-YYYYMMDD-NNN -> 'YYYY-MM-DDT00:00:00Z'.

    BUG-4: fmtTs() in the monitor expects an ISO-8601 string including a time
    component; returning only YYYY-MM-DD produces 'Invalid Date' in some
    browsers (Safari, mobile Chrome) because Date.parse() requires a full
    timestamp for ISO strings without an explicit time zone.  Append
    T00:00:00Z so the string always parses cleanly.
    """
    m = re.match(r"^RUN-(\d{4})(\d{2})(\d{2})", run_id or "")
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}T00:00:00Z"
    return ""


def _normalize_ts(raw: str) -> str:
    """'2026-04-21 14:05' → '2026-04-21T14:05:00Z' (best-effort)."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?", raw)
    if not m:
        return raw
    sec = m.group(4) or "00"
    return f"{m.group(1)}T{m.group(2)}:{m.group(3)}:{sec}Z"


_KV_RE = re.compile(r"\b([A-Z][A-Z_]*)\s*:\s*([^|]+?)(?=\s*\||\s*$)")


def _extract_kv(blob: str, key: str) -> Optional[str]:
    for k, v in _KV_RE.findall(blob or ""):
        if k == key:
            return v.strip()
    return None
