"""nightclaw_common.socket_path -- derive a workspace-unique ops socket path.

Why this exists
---------------
The original default ``/tmp/nightclaw-ops.sock`` is a flat, hardcoded name.
If a user runs two NightClaw workspaces on the same machine the bridge and
engine instances collide on the same socket path and events cross-contaminate.

The fix: derive the socket filename from a short hash of the canonical
workspace root path.  Both the engine telemetry emitter and the bridge CLI
call this function independently; because both resolve from the same real
path they produce the same socket name and connect correctly without any
shared state or explicit coordination.

Socket placement: ``/tmp/`` (Linux tmpfs / macOS ``/private/tmp``)
-------------------------------------------------------------------
The socket must live on a filesystem that supports Unix-domain socket files.
On Windows/WSL2 the workspace is on an NTFS DrvFs mount that does NOT support
socket files (``EOPNOTSUPP``).  ``/tmp/`` is always tmpfs -- safe on every
supported platform (Linux, macOS, WSL2).

Override
--------
Set ``NIGHTCLAW_OPS_SOCK`` to an absolute path to bypass derivation entirely.
The bridge ``--ops-sock`` flag also overrides (it sets the env var before
calling this function isn't needed; the bridge passes the value explicitly).
"""
from __future__ import annotations

import hashlib
import os


def ops_socket_path(workspace_root: str | None = None) -> str:
    """Return the Unix-domain socket path for the given workspace.

    Args:
        workspace_root: Absolute path to the NightClaw workspace root.
            If *None*, uses ``NIGHTCLAW_ROOT`` env var or ``os.getcwd()``.

    Returns:
        An absolute path such as ``/tmp/nightclaw-a3f7c91b2e.sock``.
        If ``NIGHTCLAW_OPS_SOCK`` is set it is returned unchanged (override).

    The path length is always ≤ 40 characters — well under the 104-char
    macOS and 108-char Linux ``sun_path`` limits.
    """
    override = os.environ.get("NIGHTCLAW_OPS_SOCK", "")
    if override:
        return override

    if workspace_root is None:
        workspace_root = os.environ.get("NIGHTCLAW_ROOT") or os.getcwd()

    canonical = os.path.realpath(workspace_root)
    tag = hashlib.md5(canonical.encode("utf-8")).hexdigest()[:10]
    return f"/tmp/nightclaw-{tag}.sock"
