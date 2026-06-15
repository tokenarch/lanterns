#!/usr/bin/env bash
set -euo pipefail

# NightClaw — Installation Script
# Automates placeholder substitution and first-sign hash generation.
# Run from the workspace root after copying NightClaw files.

# --- Color output ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# --- Input validation ---
validate_input() {
    local name="$1"
    local value="$2"
    # Allow alphanumeric, hyphens, underscores, forward slashes, periods, tildes
    # Spaces are intentionally excluded — they break downstream sed substitutions
    if [[ ! "$value" =~ ^[a-zA-Z0-9_./~-]+$ ]]; then
        error "$name contains invalid characters. Use only: a-z A-Z 0-9 _ - . / ~"
    fi
    if [[ "$value" =~ \.\.  ]]; then
        error "$name contains a path traversal sequence (..) which is not allowed"
    fi
}

# --- Path validation ---
# Like validate_input, but additionally requires an absolute path. Used for
# WORKSPACE_ROOT only — avoids `realpath -m`, which is a GNU coreutils
# extension not available on macOS's BSD realpath.
validate_path() {
    local name="$1"
    local value="$2"
    validate_input "$name" "$value"
    if [[ "$value" != /* ]]; then
        error "$name must be an absolute path (got: $value)"
    fi
}

# --- Pre-flight: required tools and Python version ---
for cmd in sed find sha256sum; do
    command -v "$cmd" >/dev/null 2>&1 || error "required tool '$cmd' not found in PATH"
done

# Portable in-place sed: GNU sed takes `-i` with no argument, BSD/macOS sed
# requires `-i ''`. Detect by checking for GNU's --version flag.
if sed --version >/dev/null 2>&1; then
    SED_INPLACE=(-i)
else
    SED_INPLACE=(-i '')
fi

# Python 3.10+ is a hard requirement. Ubuntu 22.04 ships 3.10; 24.04 ships 3.12.
# The default `python3` on PATH may be older than 3.10 (or absent) even when a
# suitable interpreter is installed under a versioned name, so discover all
# python3.N binaries on PATH (newest first) instead of hardcoding a version list.
VERSIONED_PYTHONS=$(compgen -c python3. 2>/dev/null | grep -E '^python3\.[0-9]+$' | sort -t. -k2 -rn -u || true)
PY_CANDIDATES="python3"
[[ -n "$VERSIONED_PYTHONS" ]] && PY_CANDIDATES="python3 $VERSIONED_PYTHONS"

PY_BIN=""
for cand in $PY_CANDIDATES; do
    command -v "$cand" >/dev/null 2>&1 || continue
    if [[ "$("$cand" -c 'import sys; print("ok" if sys.version_info >= (3,10) else "")' 2>/dev/null)" == "ok" ]]; then
        PY_BIN="$cand"
        break
    fi
done
[[ -n "$PY_BIN" ]] || error "Python 3.10+ is required (tried: $PY_CANDIDATES). On Ubuntu: 'sudo apt install python3'; see README.md § Install."

# --- Set up the virtual environment ---
# Isolates the runtime/test dependencies (PyYAML, pytest, websockets — see
# requirements.txt) from the system Python. Prefers uv (fast, already used
# for this repo's own venv/), falling back to the stdlib venv module + pip.
if command -v uv >/dev/null 2>&1; then
    if [[ ! -d venv ]]; then
        info "Creating virtual environment at ./venv (uv, $PY_BIN)..."
        uv venv venv --python "$PY_BIN" || error "uv venv failed"
    fi
    info "Installing dependencies from requirements.txt (uv)..."
    uv pip install -r requirements.txt --python venv/bin/python || error "uv pip install -r requirements.txt failed"
else
    if [[ ! -d venv ]]; then
        info "Creating virtual environment at ./venv ($PY_BIN)..."
        "$PY_BIN" -m venv venv || error "$PY_BIN -m venv failed"
    fi
    info "Installing dependencies from requirements.txt (pip)..."
    venv/bin/python -m pip install --upgrade pip -q
    venv/bin/python -m pip install -r requirements.txt -q || error "pip install -r requirements.txt failed"
fi

# PYBIN is used for the rest of this script and is the interpreter operators
# should use afterwards (see "Next steps" at the end).
PYBIN="venv/bin/python3"
"$PYBIN" -c 'import yaml' 2>/dev/null || \
    error "PyYAML still not importable in ./venv after install — check requirements.txt and the pip output above."

# --- Collect values ---
echo ""
echo "NightClaw — Installation"
echo "==============================="
echo ""
echo "This script will substitute placeholders and generate integrity hashes."
echo "Values must contain only alphanumeric characters, hyphens, underscores,"
echo "forward slashes, periods, and tildes."
echo ""

read -rp "Your name or handle (OWNER): " OWNER
validate_input "OWNER" "$OWNER"

read -rp "Workspace root path [~/nightclaw-workspace]: " WORKSPACE_ROOT
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$HOME/nightclaw-workspace}"
# Expand ~ if the user typed it literally; validate_input expects an absolute path.
WORKSPACE_ROOT="${WORKSPACE_ROOT/#\~/$HOME}"
validate_path "WORKSPACE_ROOT" "$WORKSPACE_ROOT"
# Warn (non-fatal) if the workspace root we're running in doesn't match the
# value the user provided. This is a common source of confusion: install.sh
# must be run FROM the workspace root after copying NightClaw files into it.
if [[ "$(pwd)" != "$WORKSPACE_ROOT" ]]; then
    warn "You are running install.sh from $(pwd)"
    warn "but you entered WORKSPACE_ROOT=$WORKSPACE_ROOT."
    warn "Placeholders will be written with $WORKSPACE_ROOT, and scripts will look"
    warn "for files under $WORKSPACE_ROOT at runtime. Make sure that is where you"
    warn "actually copied NightClaw before proceeding."
fi

# Cowork install — no cron or logs directories needed (Cowork manages scheduling).
read -rp "Platform (e.g., Ubuntu/WSL2, macOS, Linux): " PLATFORM
PLATFORM="${PLATFORM:-Linux}"
validate_input "PLATFORM" "$PLATFORM"

INSTALL_DATE=$(date +%Y-%m-%d)

echo ""
info "Configuration:"
echo "  OWNER:          $OWNER"
echo "  WORKSPACE_ROOT: $WORKSPACE_ROOT"
echo "  PLATFORM:       $PLATFORM"
echo "  INSTALL_DATE:   $INSTALL_DATE"
echo ""
read -rp "Proceed? (y/N): " CONFIRM
[[ "$CONFIRM" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

# --- Step 1: Substitute placeholders ---
info "Substituting placeholders across all .md files..."

# Substitute placeholders in all .md files EXCEPT scripts/ — validate.sh contains
# placeholder patterns that must not be substituted (they are the search patterns).
find . -name "*.md" -not -path './scripts/*' -exec sed "${SED_INPLACE[@]}" \
    -e "s|{OWNER}|$OWNER|g" \
    -e "s|{WORKSPACE_ROOT}|$WORKSPACE_ROOT|g" \
    -e "s|{PLATFORM}|$PLATFORM|g" \
    -e "s|{INSTALL_DATE}|$INSTALL_DATE|g" \
    {} \;

# Also substitute in VERSION file (not .md)
sed "${SED_INPLACE[@]}" \
    -e "s|{INSTALL_DATE}|$INSTALL_DATE|g" \
    -e "s|{WORKSPACE_ROOT}|$WORKSPACE_ROOT|g" \
    VERSION 2>/dev/null || true

info "Placeholders substituted."

# --- Step 1b: Restore schema-rendered sections in REGISTRY.md ---
# install.sh substitutes {OWNER} across every *.md, including the rendered
# marker bodies in orchestration-os/REGISTRY.md. Those bodies are a projection
# of orchestration-os/schema/*.yaml, which intentionally keep {OWNER} literal
# as a doctrine token. Post-substitution REGISTRY.md therefore diverges from
# schema-render and breaks tests/core/test_schema_sync.py (R1). Running
# schema-sync after substitution restores byte-equality before we hash.
if "$PYBIN" scripts/nightclaw-ops.py schema-sync >/dev/null 2>&1; then
    info "REGISTRY.md rendered sections restored from schema."
else
    warn "schema-sync failed — REGISTRY.md may diverge from schema render."
fi

# --- Step 2: Generate integrity hashes ---
info "Generating SHA-256 hashes for protected files..."

PROTECTED_FILES=(
    "SOUL.md"
    "USER.md"
    "IDENTITY.md"
    "MEMORY.md"
    "AGENTS-CORE.md"
    "orchestration-os/CRON-WORKER-PROMPT.md"
    "orchestration-os/CRON-MANAGER-PROMPT.md"
    "orchestration-os/OPS-PREAPPROVAL.md"
    "orchestration-os/OPS-AUTONOMOUS-SAFETY.md"
    "orchestration-os/CRON-HARDLINES.md"
    "orchestration-os/REGISTRY.md"
)

MANIFEST="audit/INTEGRITY-MANIFEST.md"
HASHES_OK=true

for f in "${PROTECTED_FILES[@]}"; do
    if [[ -f "$f" ]]; then
        HASH=$(sha256sum "$f" | cut -d' ' -f1)
        # Update the manifest: replace the placeholder line for this file
        # Use Python to update the manifest row; sed pipe-delimiter conflicts make
        # inline sed unreliable here.  Falls back gracefully if the row is not found.
        "$PYBIN" -c "
import sys, re, pathlib
f, h, d, o, m = sys.argv[1:]
p = pathlib.Path(m)
t = p.read_text()
pat = r'(\| \x60' + re.escape(f) + r'\x60 \|)[^\n]*'
rep = r'\1 ' + h + ' | ' + d + ' | ' + o + '-signed-2026.4.23 |'
p.write_text(re.sub(pat, rep, t))
" "$f" "$HASH" "$INSTALL_DATE" "$OWNER" "$MANIFEST" 2>/dev/null || \
            warn "  Could not auto-update manifest row for $f — paste the hash manually."
        info "  $f: $HASH"
    else
        warn "  $f: NOT FOUND"
        HASHES_OK=false
    fi
done

if $HASHES_OK; then
    info "All hashes generated. Paste them into $MANIFEST if auto-update failed."
else
    warn "Some protected files were not found. Check your file structure."
fi

# --- Step 3: Create directories ---
info "Ensuring required directories exist..."
mkdir -p memory/ skills/ PROJECTS/

# --- Step 4: Model tier configuration ---
echo ""
echo "NightClaw Model Tier Configuration"
echo "===================================="
echo "NightClaw automatically switches the worker to the right model between"
echo "sessions based on each project's next_pass.model_tier (lightweight/standard/heavy)."
echo ""
echo "Enter the model ID for each tier. See MODEL-TIERS.md for the Claude model IDs."
echo "Press Enter to skip a tier — you can edit MODEL-TIERS.md later."
echo ""

read -rp "Lightweight model ID (fast, cheap — e.g. google/gemini-2.5-flash): " MODEL_LIGHTWEIGHT
MODEL_LIGHTWEIGHT="${MODEL_LIGHTWEIGHT:-{MODEL_LIGHTWEIGHT}}"

read -rp "Standard model ID   (balanced — e.g. openai/gpt-4o):               " MODEL_STANDARD
MODEL_STANDARD="${MODEL_STANDARD:-{MODEL_STANDARD}}"

read -rp "Heavy model ID      (most capable — e.g. anthropic/claude-opus-4): " MODEL_HEAVY
MODEL_HEAVY="${MODEL_HEAVY:-{MODEL_HEAVY}}"

# Write MODEL-TIERS.md substituting tier values
sed "${SED_INPLACE[@]}" \
    -e "s|{MODEL_LIGHTWEIGHT}|${MODEL_LIGHTWEIGHT}|g" \
    -e "s|{MODEL_STANDARD}|${MODEL_STANDARD}|g" \
    -e "s|{MODEL_HEAVY}|${MODEL_HEAVY}|g" \
    MODEL-TIERS.md 2>/dev/null || warn "Could not write model tier values to MODEL-TIERS.md — edit manually."

info "MODEL-TIERS.md written."

# Cowork manages model selection at scheduled-task creation time.
# MODEL-TIERS.md is advisory metadata — the model the worker actually runs
# on is whatever the operator configures in the scheduled-task UI.

# --- Done ---
echo ""
info "Installation complete."
info "A Python virtual environment was set up at ./venv with requirements.txt installed."
echo ""
echo "Next steps:"
echo "  0. Activate the virtual environment: source venv/bin/activate"
echo "     (or prefix python3/pytest commands below with venv/bin/, e.g. venv/bin/python3, venv/bin/pytest)"
echo "  1. Confirm hashes: bash scripts/verify-integrity.sh  (must show 11/11 PASS)"
echo "     If any file shows FAIL, re-run: bash scripts/resign.sh <file>"
echo "  2. Edit SOUL.md — replace {DOMAIN_ANCHOR} with your domain focus (2-3 sentences)"
echo "     Then re-sign: bash scripts/resign.sh SOUL.md"
echo "  3. Edit USER.md — fill in your name, timezone, and domain restrictions"
echo "     Then re-sign: bash scripts/resign.sh USER.md"
echo "  4. Run: bash scripts/validate.sh to check internal consistency"
echo "  5. Create the two Cowork scheduled tasks — see DEPLOY-CLAUDE.md § Step 6"
echo "  6. Start a new project: bash scripts/new-project.sh <slug>"
echo ""
echo "Full install guide: see README.md and DEPLOY-CLAUDE.md."
