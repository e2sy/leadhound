#!/usr/bin/env bash
# ============================================================
#  leadhound → GitHub, one command.
#
#    ./push-to-github.sh
#
#  Creates the repo, sets description + topics, replaces the
#  YOUR_GITHUB_USERNAME placeholders, pushes main + the v0.1.0 tag.
#
#  Prereqs (Option A): GitHub CLI  ->  https://cli.github.com
#      gh auth login
#  No gh? The script prints exact manual steps (Option B).
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

GITHUB_USER="${GITHUB_USER:-}"
REPO_NAME="${1:-leadhound}"
DESCRIPTION="🐺 The gig sniper — watches freelance job boards 24/7, scores every gig against your profile, drafts proposals in your voice. You just approve and send."
TOPICS="freelance,freelancer,upwork,remote-work,job-search,job-board,automation,cli,python,python3,llm,telegram-bot,productivity,ai-tools"

# --- 1. Ask for the GitHub username once -------------------------------
if [[ -z "$GITHUB_USER" ]]; then
  read -rp "GitHub username: " GITHUB_USER
fi
[[ "$GITHUB_USER" == "YOUR_GITHUB_USERNAME" || -z "$GITHUB_USER" ]] && {
  echo "✗ A real username is required."; exit 1; }
SLUG="${GITHUB_USER}/${REPO_NAME}"

# --- 2. Replace placeholders (idempotent) ------------------------------
if grep -rq "YOUR_GITHUB_USERNAME" README.md pyproject.toml CONTRIBUTING.md .github leadhound 2>/dev/null; then
  echo "→ Linking docs and badges to ${SLUG} ..."
  if sed --version >/dev/null 2>&1; then SED="sed -i"; else SED="sed -i ''"; fi
  grep -rl "YOUR_GITHUB_USERNAME" README.md pyproject.toml CONTRIBUTING.md .github leadhound 2>/dev/null \
    | while read -r f; do $SED "s|YOUR_GITHUB_USERNAME|${GITHUB_USER}|g" "$f"; done
  git add -A
  git diff --cached --quiet || git commit -q -m "docs: point badges and URLs at ${SLUG}"
fi

# --- 3. Push ------------------------------------------------------------
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  echo "→ Creating public repo ${SLUG} via gh ..."
  gh repo create "$SLUG" --public --source=. --remote=origin --push \
     --description "$DESCRIPTION" 2>/dev/null \
  || { git remote add origin "https://github.com/${SLUG}.git" 2>/dev/null || true; }

  echo "→ Pushing main + tags ..."
  git push -u origin main
  git push origin --tags

  echo "→ Setting repo topics ..."
  gh repo edit "$SLUG" --add-topic "${TOPICS//,/ --add-topic }" >/dev/null
  gh repo edit "$SLUG" --homepage "" >/dev/null 2>&1 || true

  echo ""
  echo "✅ DONE. Repo live at: https://github.com/${SLUG}"
  echo "   Next: upload a social preview image (Repo → Settings → Social preview)"
  echo "   Then: create the release -> gh release create v0.1.0 --generate-notes"
else
  git remote remove origin 2>/dev/null || true
  git remote add origin "https://github.com/${SLUG}.git"
  cat <<EOF

  No gh CLI found (or not logged in). Manual path — 60 seconds:

  1) Create the repo (NO readme/license init — we have everything):
        https://github.com/new
     Name:        ${REPO_NAME}
     Description: ${DESCRIPTION}
     Topics (add in the About ⚙️ after creation):
        ${TOPICS//,/  }

  2) Push from here:
        git push -u origin main
        git push origin --tags

  3) Verify the CI badge is green, then:
     Repo → Settings → Social preview → upload a 1280×640 image
     Releases → Draft new release → choose tag v0.1.0 → "Generate release notes" → Publish

  Done: https://github.com/${SLUG}
EOF
fi
