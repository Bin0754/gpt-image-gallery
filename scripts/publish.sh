#!/usr/bin/env bash
# Maintainer: publish the latest build to GitHub Pages.
#   python3 scripts/build_site.py && scripts/publish.sh ["commit message"]
# build_site.py mirrors the public site (index.html, data.json, prompts.json, prompts.csv, images, README, ...)
# into ./site, which is a git checkout of the repo; this script commits and pushes it to main.
set -euo pipefail
# never block on a prompt when run unattended (cron / agent)
export GH_PROMPT_DISABLED=1 GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/true
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SITE="$ROOT/site"
REPO="${GALLERY_REPO:-Bin0754/gpt-image-gallery}"
BRANCH=main
for f in index.html data.json prompts.json prompts.csv; do
  [ -f "$SITE/$f" ] || { echo "site/$f missing - run python3 scripts/build_site.py first" >&2; exit 1; }
done
cd "$SITE"
if [ ! -d .git ]; then
  git init -q -b "$BRANCH"
  git remote add origin "https://github.com/$REPO.git"
fi
git config user.name  >/dev/null || git config user.name  "$(gh api user --jq .login)"
git config user.email >/dev/null || git config user.email "$(gh api user --jq '.id|tostring')+$(gh api user --jq .login)@users.noreply.github.com"
gh auth status >/dev/null 2>&1 || { echo "gh is not logged in (run: gh auth login) - cannot push" >&2; exit 2; }
gh auth setup-git >/dev/null 2>&1 || true
git add -A
if git diff --cached --quiet; then
  echo "No changes to publish."
else
  COUNT=$(python3 -c "import json;print(json.load(open('prompts.json'))['count'])")
  git commit -q -m "${1:-数据更新：$COUNT 组作品（$(TZ=Asia/Shanghai date '+%Y-%m-%d %H:%M') UTC+8）}"
  git pull -q --rebase origin "$BRANCH"   # pick up README/issue-template edits made on github.com
  git push -q origin "$BRANCH"
  echo "Pushed $(git rev-parse --short HEAD) to $REPO ($COUNT posts)."
fi
OWNER="${REPO%%/*}"; NAME="${REPO##*/}"
echo "Live: https://${OWNER,,}.github.io/$NAME/  (Pages rebuild usually takes 1-3 min)"
