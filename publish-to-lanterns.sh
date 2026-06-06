#!/usr/bin/env bash
# publish-to-lanterns.sh — one-shot bootstrap for github.com/tokenarch/lanterns
#
# Run this ONCE from inside the lanterns-publish-ready directory to:
#   1. Initialize a fresh git repo
#   2. Stage every file (respecting .gitignore)
#   3. Make one initial commit
#   4. Wire up the lanterns remote
#
# Then you run `git push -u origin main` separately (the push is the only step
# that needs your GitHub credentials, so it can't be scripted blind).
#
# PREREQUISITES:
#   - The github.com/tokenarch/lanterns repo exists (create it empty on GitHub
#     first; no auto-README, no .gitignore, no license — we ship all of those).
#   - Your local git is authenticated for the tokenarch GitHub account
#     (SSH key or HTTPS PAT configured).

set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# Sanity: we should be inside the staging directory
[[ -f SOUL.md && -f DEPLOY-CLAUDE.md && -d nightclaw_engine ]] \
  || error "Run this from inside the lanterns-publish-ready directory."

# Refuse to run if there's already a .git here (would mean already initialized)
[[ -d .git ]] && error ".git already exists here. If you really want to redo, rm -rf .git first."

info "Initializing fresh git repo on branch 'main'..."
git init -b main

info "Staging files (gitignored content excluded)..."
git add -A

# Sanity-check the staged set
N=$(git ls-files | wc -l | tr -d ' ')
info "Staged $N files. Confirming none are gitignored leak..."
if git ls-files | grep -qE "(__pycache__|\.pytest_cache|Zone\.Identifier|\.pyc$)"; then
    error "Staged set contains gitignored artifacts. Inspect with: git ls-files | grep -E '__pycache__|Zone\\.Identifier|\\.pyc'"
fi

info "Creating initial commit..."
git commit -m "Initial release: Lanterns — NightClaw for Claude Desktop Cowork

Lanterns is the Claude-specific build of the NightClaw protocol: a
file-based operating protocol that gives an LLM agent a governed,
self-improving workspace inside Claude Desktop Cowork. Two scheduled
tasks (worker + manager) execute a deterministic T0-T9 protocol against
a workspace folder mounted from disk.

Includes:
- 39-command deterministic engine (nightclaw_engine/)
- Schema-driven bundle executor with 8 named transactions
- Optional WebSocket monitor (nightclaw_bridge/, apps/monitor/)
- 11 protected files with SHA-256 integrity manifest
- Pre-flight import gate, syntax-check, crash-recover, audit replay
- Curated bootstrap command for fresh LLM session onboarding

Codebase retains the NightClaw name throughout; Lanterns is the public
build name for this Cowork-tuned distribution.
"

info "Wiring lanterns remote..."
git remote add origin https://github.com/tokenarch/lanterns.git

cat <<NEXT

${GREEN}====================================================================${NC}
${GREEN}  DONE.${NC}  Repo initialized, staged, committed, remote wired.

  Next (run from this directory):

      git push -u origin main

  That's the only step that needs your GitHub credentials.

  If the push fails with 'updates were rejected (fetch first)', the
  GitHub repo isn't empty. Either delete the repo on github.com and
  recreate it empty, or:

      git push -u --force origin main

  (force is safe here because lanterns is a fresh repo)
${GREEN}====================================================================${NC}
NEXT
