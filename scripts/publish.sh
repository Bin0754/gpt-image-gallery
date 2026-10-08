#!/usr/bin/env bash
# Publish the latest build (site/, produced by build_site.py) to GitHub Pages.
# Usage:  python3 build_site.py && ./publish.sh ["optional commit message"]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
SITE="$ROOT/site"
REPO="${GALLERY_REPO:-Bin0754/gpt-image-gallery}"
BRANCH=main
[ -f "$SITE/index.html" ] || { echo "site/index.html missing - run python3 build_site.py first" >&2; exit 1; }
cd "$SITE"
if [ ! -d .git ]; then
  git init -q -b "$BRANCH"
  git remote add origin "https://github.com/$REPO.git"
fi
git config user.name  >/dev/null || git config user.name  "$(gh api user --jq .login)"
git config user.email >/dev/null || git config user.email "$(gh api user --jq '.id|tostring')+$(gh api user --jq .login)@users.noreply.github.com"
gh auth setup-git >/dev/null 2>&1 || true
git add -A
if git diff --cached --quiet; then
  echo "No changes to publish."
else
  COUNT=$(python3 -c "import json;print(json.load(open('data.json'))['count'])")
  git commit -q -m "${1:-Update gallery: $COUNT posts ($(date '+%Y-%m-%d %H:%M') UTC+8)}"
  git push -q origin "$BRANCH"
  echo "Pushed $(git rev-parse --short HEAD) to $REPO ($COUNT posts)."
fi
OWNER="${REPO%%/*}"; NAME="${REPO##*/}"
echo "Live: https://${OWNER,,}.github.io/$NAME/  (Pages rebuild usually takes ~1 min)"
