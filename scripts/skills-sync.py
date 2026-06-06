#!/usr/bin/env python3
"""skills-sync.py — copy canonical engine artifacts into ``skills/`` for packaging.

G4 FIX (part 2): ``skills/`` used to hold hand-maintained duplicates of the
engine. That drifted. Going forward the canonical source is:

    scripts/nightclaw-ops.py          (thin CLI dispatcher)
    nightclaw_engine/                 (engine implementation)
    nightclaw_common/                 (shared runtime helpers imported by engine/bridge)

``skills/nightclaw-ops.py`` is a re-executor forwarder that never needs to
change. For distribution channels that ship a self-contained ``skills/``
bundle, run this script to copy the canonical files verbatim:

    python3 scripts/skills-sync.py

Run from the workspace root (where ``scripts/`` and ``skills/`` both exist).
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _abort(msg: str) -> "None":
    sys.stderr.write(f"ERROR: {msg}\n")
    sys.exit(2)


def main() -> int:
    root = Path.cwd()
    if not (root / "scripts").is_dir() or not (root / "skills").is_dir():
        _abort("run from the workspace root where scripts/ and skills/ both exist")

    # Strategy: copy the forwarder (which already lives in skills/) is a no-op.
    # We distribute the canonical packages by copying them into skills/ so
    # packaged skill bundles remain self-
    # contained. The scripts/ shell also gets mirrored for legacy callers that
    # invoke `skills/nightclaw-ops.py` directly (the forwarder already covers
    # that case; we still leave a copy so a standalone skill bundle works
    # without any scripts/ present).
    copied: list[tuple[str, Path]] = []
    for package in ("nightclaw_engine", "nightclaw_common"):
        package_src = root / package
        package_dst = root / "skills" / package
        if not package_src.is_dir():
            _abort(f"missing source package at {package_src}")

        if package_dst.exists():
            shutil.rmtree(package_dst)
        shutil.copytree(package_src, package_dst,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        copied.append((package, package_dst))

    # Also mirror the canonical dispatcher script as a pure copy (not the
    # forwarder) so a skills-only distribution keeps working.
    script_src = root / "scripts" / "nightclaw-ops.py"
    script_dst = root / "skills" / "nightclaw-ops-canonical.py"
    shutil.copy2(script_src, script_dst)

    print("skills-sync: OK")
    for package, package_dst in copied:
        print(f"  {package} -> {package_dst.relative_to(root)}")
    print(f"  canonical script copy -> {script_dst.relative_to(root)}")
    print("  forwarder stays at skills/nightclaw-ops.py (do not hand-edit)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
