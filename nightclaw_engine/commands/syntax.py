"""nightclaw_engine.commands.syntax — AST parse gate for the Python tree.

Catches NTFS write truncation and other "file got cut off" failures that
are silent under the Edit/Write tools used in some agent environments.

Distinct from ``preflight-import``:
  * ``preflight-import`` executes ``importlib.import_module(name)`` —
    catches runtime errors that happen at import time (e.g. a missing
    symbol referenced at module top level).
  * ``syntax-check`` ``ast.parse()``s the source — catches truncation
    that would fail to import, AND files that are only imported lazily
    or by tests (which preflight does not exercise).

Scope: every ``.py`` under the four packages (nightclaw_engine,
nightclaw_bridge, nightclaw_monitor, nightclaw_ops), ``nightclaw_common``,
``scripts/``, and ``tests/``. Excludes ``__pycache__`` and any path with
``Zone.Identifier`` (a Windows NTFS artifact that is not Python source).

Output:
    PASS <path>                (per file)
    FAIL <path> <SyntaxError>: <message>  (per failure)
    RESULT:PASS files=N
    RESULT:FAIL files=N failed=M

Exit: 0 on full pass, 2 on any failure.
"""
from __future__ import annotations

import ast
import pathlib
import sys

from . import _shared


# Roots that contain hand-authored Python source. Anything outside these is
# either generated, third-party, or doctrine — not the syntax-check's job.
SOURCE_ROOTS = [
    "nightclaw_engine",
    "nightclaw_bridge",
    "nightclaw_monitor",
    "nightclaw_ops",
    "nightclaw_common",
    "scripts",
    "tests",
]

# Filename patterns to skip. Zone.Identifier is the NTFS ADS marker file
# that WSL exposes alongside the real file — it is not Python.
SKIP_NAME_PARTS = ("Zone.Identifier",)
SKIP_DIRS = ("__pycache__", ".pytest_cache", ".git")


def _iter_py_files(root):
    """Yield every .py file under root excluding the skip patterns."""
    base = _shared.ROOT / root
    if not base.exists():
        return
    for path in base.rglob("*.py"):
        if any(skip in path.parts for skip in SKIP_DIRS):
            continue
        if any(part in path.name for part in SKIP_NAME_PARTS):
            continue
        yield path


def cmd_syntax_check():
    """Parse every workspace .py file with ast.parse(). Exit 2 on any failure."""
    failures = []
    pass_count = 0
    total = 0
    for root in SOURCE_ROOTS:
        for path in _iter_py_files(root):
            total += 1
            rel = path.relative_to(_shared.ROOT)
            try:
                source = path.read_text(encoding="utf-8")
                ast.parse(source, filename=str(rel))
            except SyntaxError as exc:
                # SyntaxError exposes lineno + msg; both are stable.
                msg = (exc.msg or "").split("\n", 1)[0][:200]
                print(f"FAIL {rel} line={exc.lineno or 0} SyntaxError: {msg}")
                failures.append(rel)
            except (OSError, UnicodeDecodeError) as exc:
                # A file we cannot read at all (permission, decode) is also
                # a failure mode worth surfacing.
                print(f"FAIL {rel} {type(exc).__name__}: {exc}")
                failures.append(rel)
            else:
                # Don't spam stdout with PASS for every file — the count
                # is in the RESULT line. Operators who want per-file output
                # can use --verbose.
                if "--verbose" in sys.argv[2:]:
                    print(f"PASS {rel}")
                pass_count += 1

    if failures:
        print(f"RESULT:FAIL files={total} failed={len(failures)}")
        sys.exit(2)
    print(f"RESULT:PASS files={total}")
    sys.exit(0)


__all__ = ["cmd_syntax_check", "SOURCE_ROOTS"]
