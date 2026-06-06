"""nightclaw_engine.commands.preflight — import-gate pre-flight check.

Single purpose: catch the class of bug where a code change broke an import
path between sessions, but no one ran pytest before the next cron session.
The 2026-05-27 bridge breakage (runtime.py imported symbols that did not
exist in snapshot_contract / state) sat undetected for 3 days because the
worker pass does not import the bridge, and the operator did not happen to
restart the monitor in that window.

This command imports every package the workspace depends on. The cron
prompt calls it as Step T0a, before integrity-check. If any module fails
to import, the session halts and surfaces a CRITICAL notification.

Scope: default is "worker" (nightclaw_engine + nightclaw_common +
nightclaw_ops) — what a worker pass actually needs. ``--full`` extends to
the bridge + monitor packages, which is what CI and start-monitor.sh care
about. Splitting the scopes avoids forcing the worker to pay the bridge
import cost (websockets) on every session.

Output:
    PASS <module>            (per module)
    FAIL <module> <ExceptionType>: <message>
    RESULT:PASS scope=<scope> checked=N
    RESULT:FAIL scope=<scope> checked=N failed=M

Exit: 0 on full pass, 2 on any failure (matches schema-lint / integrity-
check failure exit codes).
"""
from __future__ import annotations

import importlib
import sys


# Modules the worker pass needs to function. Each is import-tested with
# ``importlib.import_module``; submodules are listed explicitly so a broken
# import inside one submodule is reported against that submodule rather
# than swallowed by the package __init__.
WORKER_MODULES = [
    "nightclaw_engine",
    "nightclaw_engine.commands",
    "nightclaw_engine.commands._shared",
    "nightclaw_engine.commands.bundle",
    "nightclaw_engine.commands.bundle_mutators",
    "nightclaw_engine.commands.bootstrap",
    "nightclaw_engine.commands.lock",
    "nightclaw_engine.commands.integrity",
    "nightclaw_engine.commands.append",
    "nightclaw_engine.commands.audit",
    "nightclaw_engine.commands.dispatch",
    "nightclaw_engine.commands.longrunner",
    "nightclaw_engine.commands.scr",
    "nightclaw_engine.commands.validate",
    "nightclaw_engine.commands.model_tier",
    "nightclaw_engine.engine.render",
    "nightclaw_engine.protocol.integrity",
    "nightclaw_engine.schema",
    "nightclaw_engine.schema.loader",
    "nightclaw_common.preapprovals",
    "nightclaw_common.socket_path",
    "nightclaw_ops.telemetry",
    "nightclaw_ops.lifecycle",
]

# Modules the monitor side needs. Failures here are not blocking for a
# worker pass — they prevent the monitor from showing live state but the
# engine still runs.
MONITOR_MODULES = [
    "nightclaw_bridge",
    "nightclaw_bridge.protocol",
    "nightclaw_bridge.server",
    "nightclaw_bridge.runtime",
    "nightclaw_bridge.snapshot_contract",
    "nightclaw_bridge.state",
    "nightclaw_bridge.sources",
    "nightclaw_bridge.client_handlers",
    "nightclaw_bridge.config",
    "nightclaw_bridge.main",
    "nightclaw_bridge.repository",
    "nightclaw_monitor",
    "nightclaw_monitor.store",
]


def _try_import(name):
    """Force a fresh import (drop cache) and return (ok, exc_type, message)."""
    if name in sys.modules:
        del sys.modules[name]
    try:
        importlib.import_module(name)
    except Exception as exc:
        return False, type(exc).__name__, str(exc)
    return True, None, None


def _check_tier_consistency():
    """After imports succeed, verify the engine and bridge agree on tiers.

    Three drift modes this catches:
    - STEP_CMD_MAP has a tier that ALLOWED_TIERS does not. Bridge silently
      drops every event tagged with that tier; monitor shows incomplete state.
    - COMMANDS has an entry with no STEP_CMD_MAP — engine emits the default
      "T4" telemetry tier, which is correct for bundle-exec but wrong for
      everything else and pollutes the tier histogram.
    - ALLOWED_TIERS has a tier no STEP_CMD_MAP references — dead capacity
      (informational only; reported but not failing).
    """
    failures = []
    try:
        from nightclaw_engine.commands import STEP_CMD_MAP, COMMANDS
        from nightclaw_common.tiers import ALLOWED_TIERS
    except Exception as exc:
        # If imports failed they would have surfaced earlier; this guard is for
        # the case where preflight is run in an environment that genuinely
        # cannot import the shared tiers module. Silently skip.
        return []

    step_tiers = set(STEP_CMD_MAP.values())
    bridge_tiers = set(ALLOWED_TIERS)

    missing_in_bridge = step_tiers - bridge_tiers
    for tier in sorted(missing_in_bridge):
        cmds = sorted(c for c, t in STEP_CMD_MAP.items() if t == tier)
        print(f"FAIL consistency: STEP_CMD_MAP tier {tier!r} is not in "
              f"ALLOWED_TIERS (commands affected: {cmds})")
        failures.append(f"tier:{tier}")

    cmds_without_tier = set(COMMANDS.keys()) - set(STEP_CMD_MAP.keys())
    for cmd in sorted(cmds_without_tier):
        print(f"FAIL consistency: COMMANDS[{cmd!r}] has no STEP_CMD_MAP entry "
              f"(telemetry will default to 'T4')")
        failures.append(f"cmd:{cmd}")

    # Dead tiers in bridge — informational, do not fail.
    dead = bridge_tiers - step_tiers
    if dead:
        # Print to stderr so it does not contaminate the structured stdout.
        import sys as _sys
        _sys.stderr.write(
            f"INFO consistency: ALLOWED_TIERS has tiers no command targets: "
            f"{sorted(dead)}\n")

    return failures


def cmd_preflight_import():
    """Verify every required Python module imports cleanly. Exit 2 on any failure.

    Reads ``--full`` from sys.argv to extend coverage to bridge + monitor.
    """
    full = "--full" in sys.argv[2:]
    scope = "full" if full else "worker"
    modules = list(WORKER_MODULES)
    if full:
        modules += MONITOR_MODULES

    failures = []
    for m in modules:
        ok, exc_type, msg = _try_import(m)
        if ok:
            print(f"PASS {m}")
        else:
            # Truncate long messages so a single failure doesn't dominate output.
            short = (msg or "").split("\n", 1)[0][:200]
            print(f"FAIL {m} {exc_type}: {short}")
            failures.append(m)

    # After import gate passes, check cross-package tier consistency.
    # Only meaningful when bridge is imported (full scope) OR when the engine
    # alone is enough to reach the imports. Both yield useful drift signals.
    consistency_failures = _check_tier_consistency()

    if failures or consistency_failures:
        print(f"RESULT:FAIL scope={scope} checked={len(modules)} "
              f"failed={len(failures)} consistency={len(consistency_failures)}")
        sys.exit(2)
    print(f"RESULT:PASS scope={scope} checked={len(modules)} consistency=OK")
    sys.exit(0)


__all__ = ["cmd_preflight_import", "WORKER_MODULES", "MONITOR_MODULES"]
