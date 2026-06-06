"""nightclaw_engine.commands.replay — audit-log replay for a single run.

Reconstructs what a worker or manager session DID from the append-only
audit logs. Closes a documented gap in the "files are memory, everything
is inspectable" thesis: previously, debugging a crashed pass meant reading
``audit/AUDIT-LOG.md`` and ``audit/CHANGE-LOG.md`` by hand and correlating
on run_id.

Usage:
    replay <run_id>              # full replay
    replay <run_id> --from T2    # from a T-step onward
    replay <run_id> --to T6      # up to and including a T-step
    replay <run_id> --json       # NDJSON output, one event per line

Output (text mode) — one line per event:
    <step>  <type>  <kv pairs>
    CHANGE  <field>  <old_value> -> <new_value>

Final summary lines:
    SUMMARY:steps=N changes=M completed=<yes|no|recovered>
    SUMMARY:first_step=<step> last_step=<step>
    SUMMARY:recovered_by=<later_run_id>   (only if recovery happened)

Exit:
    0 on any output (including "no events found")
    2 on usage / invalid run_id format
"""
from __future__ import annotations

import re
import sys

from . import _shared


_RUN_ID_RE = re.compile(r"^RUN-\d{8}-\d{3}$")
_T_STEP_RE = re.compile(r"^T\d+(\.\d+)?[a-z]?$")


def _parse_audit_events(audit_text: str, run_id: str) -> list[tuple[str, str, str]]:
    """Return [(step, type, raw_line)] for entries matching run_id, in file order."""
    events = []
    # Pattern: TASK:RUN-XXX.Tstep | TYPE:X | ...
    rx = re.compile(
        r"TASK:" + re.escape(run_id) + r"\.(?P<step>T\d+(?:\.\d+)?[a-z]?|STARTUP)\s*\|\s*"
        r"TYPE:(?P<type>[A-Z_][A-Z0-9_]*)"
    )
    for line in audit_text.splitlines():
        m = rx.search(line)
        if not m:
            continue
        events.append((m.group("step"), m.group("type"), line.strip()))
    return events


def _parse_change_events(change_text: str, run_id: str) -> list[tuple[str, str, str, str]]:
    """Return [(t_written, field, old, new)] from CHANGE-LOG for run_id, in file order."""
    events = []
    for line in change_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("<!--"):
            continue
        # field|old|new|agent|run_id|t_written|t_valid|reason|bundle
        parts = line.split("|")
        if len(parts) < 6:
            continue
        try:
            field, old, new, _agent, line_run_id, t_written = parts[:6]
        except ValueError:
            continue
        if line_run_id.strip() != run_id:
            continue
        events.append((t_written.strip(), field.strip(), old.strip(), new.strip()))
    return events


def _step_in_range(step: str, lo: str | None, hi: str | None) -> bool:
    """Compare T-step strings numerically. T1.5 is between T1 and T2."""
    if step == "STARTUP":
        # STARTUP is always pre-T0; include unless --from explicitly excludes it
        return lo is None
    def _num(s):
        if s == "STARTUP":
            return -1.0
        m = re.match(r"^T(\d+)(?:\.(\d+))?[a-z]?$", s)
        if not m:
            return 1e9
        major = int(m.group(1))
        minor = int(m.group(2) or 0)
        return major + minor / 100.0
    s = _num(step)
    if lo is not None and s < _num(lo):
        return False
    if hi is not None and s > _num(hi):
        return False
    return True


def cmd_replay():
    """Replay one run's audit + change events in chronological order."""
    if len(sys.argv) < 3:
        print("ERROR:USAGE: replay <run_id> [--from Tx] [--to Tx] [--json]", file=sys.stderr)
        sys.exit(2)

    run_id = sys.argv[2].strip()
    if not _RUN_ID_RE.match(run_id):
        print(f"ERROR:INVALID_RUN_ID:{run_id} (expected RUN-YYYYMMDD-NNN)", file=sys.stderr)
        sys.exit(2)

    args = sys.argv[3:]
    json_mode = "--json" in args
    from_step = None
    to_step = None
    for i, a in enumerate(args):
        if a == "--from" and i + 1 < len(args):
            from_step = args[i + 1]
        elif a == "--to" and i + 1 < len(args):
            to_step = args[i + 1]

    audit_log = _shared.read_file("audit/AUDIT-LOG.md") or ""
    change_log = _shared.read_file("audit/CHANGE-LOG.md") or ""
    registry = _shared.read_file("audit/SESSION-REGISTRY.md") or ""

    audit_events = _parse_audit_events(audit_log, run_id)
    change_events = _parse_change_events(change_log, run_id)

    if not audit_events and not change_events:
        print(f"NO_EVENTS:{run_id}")
        sys.exit(0)

    # Filter by step range. Change events keep all (no step on a field mutation).
    audit_filtered = [(s, t, l) for s, t, l in audit_events if _step_in_range(s, from_step, to_step)]

    if json_mode:
        import json as _json
        for step, type_, raw in audit_filtered:
            print(_json.dumps({"kind": "audit", "step": step, "type": type_, "raw": raw}))
        for t_written, field, old, new in change_events:
            print(_json.dumps({"kind": "change", "t_written": t_written,
                              "field": field, "old": old, "new": new}))
    else:
        for step, type_, raw in audit_filtered:
            # Show key=value pairs only (drop TASK: and TYPE: prefixes for readability)
            tail = raw.split("|", 2)[2].strip() if raw.count("|") >= 2 else ""
            # Drop the redundant TYPE: cell from tail
            tail = re.sub(r"^TYPE:[A-Z_]+\s*\|\s*", "", tail)
            print(f"  {step:<10s} {type_:<22s} {tail}")
        if change_events:
            print("  --- field changes ---")
            for t_written, field, old, new in change_events:
                ts = t_written if t_written else "?"
                # Truncate long values
                old_s = (old[:60] + "...") if len(old) > 63 else old
                new_s = (new[:60] + "...") if len(new) > 63 else new
                print(f"  {ts:<25s} CHANGE     {field}: {old_s} -> {new_s}")

    # Summary
    completed = run_id in registry
    # Look for a LOCK_RECOVERED entry that names this run as RECOVERED_RUN
    recovered_by = None
    rec_rx = re.compile(
        r"TASK:(?P<recoverer>RUN-\d{8}-\d{3})\.STARTUP[^\n]*LOCK_RECOVERED[^\n]*"
        r"RECOVERED_RUN:" + re.escape(run_id)
    )
    m = rec_rx.search(audit_log)
    if m:
        recovered_by = m.group("recoverer")

    if completed:
        status = "yes"
    elif recovered_by:
        status = "recovered"
    else:
        status = "no"
    print(f"SUMMARY:steps={len(audit_events)} changes={len(change_events)} completed={status}")
    if audit_events:
        first_step = audit_events[0][0]
        last_step = audit_events[-1][0]
        print(f"SUMMARY:first_step={first_step} last_step={last_step}")
    if recovered_by:
        print(f"SUMMARY:recovered_by={recovered_by}")
    sys.exit(0)


__all__ = ["cmd_replay"]
