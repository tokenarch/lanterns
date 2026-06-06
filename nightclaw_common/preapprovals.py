from __future__ import annotations

from datetime import datetime, timezone
import re


def now_utc():
    return datetime.now(timezone.utc)


def parse_iso(s):
    if not s or str(s).strip() in ("—", "-", "~", "null", "None", "none", ""):
        return None
    try:
        dt = datetime.fromisoformat(str(s).strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def local_tzinfo():
    return datetime.now().astimezone().tzinfo or timezone.utc


def parse_preapproval_expiry(expires_str):
    """Parse a pre-approval expiry into a UTC datetime.

    Supported Phase A forms:
      - YYYY-MM-DD                    → local end of day
      - YYYY-MM-DD HH:MM[:SS]         → local wall clock time
      - YYYY-MM-DDTHH:MM[:SS]         → local wall clock time
      - ISO8601 with timezone / Z     → exact instant

    Unsupported forms (including on-condition: ...) return None.
    """
    if not expires_str:
        return None
    raw = str(expires_str).strip()
    if raw in ("—", "-", "~", "null", "None", "none", ""):
        return None
    if raw.lower().startswith("on-condition:"):
        return None

    local_tz = local_tzinfo()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=local_tz).astimezone(timezone.utc)
        except ValueError:
            pass
    try:
        return datetime.strptime(raw, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=local_tz
        ).astimezone(timezone.utc)
    except ValueError:
        pass

    if re.search(r"(?:Z|[+-]\d{2}:\d{2})$", raw):
        dt = parse_iso(raw)
        if dt is not None:
            return dt.astimezone(timezone.utc)
    return None


def preapproval_is_active(status, expires_str, *, now=None):
    if str(status or "").strip().upper() != "ACTIVE":
        return False
    exp_dt = parse_preapproval_expiry(expires_str)
    if exp_dt is None:
        return False
    return (now or now_utc()) <= exp_dt
