#!/usr/bin/env bash
# One-shot, non-interactive refresh: [fetch] -> scrape -> build -> publish -> verify live site.
# Safe to run from cron / an agent: absolute paths, lock file, log file, no interactive prompts.
#
#   scripts/refresh.sh                 # full run
#   scripts/refresh.sh --no-publish    # build only (dry run)
#
# X data: if X_BEARER_TOKEN is set, scripts/fetch_x.py --recent appends new raw/*.txt files.
# Otherwise raw/ must already contain the new search results (e.g. saved by an agent using the X MCP);
# the script then just rebuilds from whatever is in raw/.
set -euo pipefail
export GH_PROMPT_DISABLED=1 GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/true TZ=Asia/Shanghai
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"
ROOT="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
cd "$ROOT"
PUBLISH=1; [ "${1:-}" = "--no-publish" ] && PUBLISH=0
mkdir -p logs
LOG="logs/refresh-$(date +%Y%m%d-%H%M).log"
exec > >(tee -a "$LOG") 2>&1
exec 9>"$ROOT/logs/.refresh.lock"
flock -n 9 || { echo "another refresh is running"; exit 3; }
echo "== refresh start $(date '+%F %T') UTC+8  root=$ROOT"

# ---- preflight ----
command -v python3 >/dev/null || { echo "python3 missing"; exit 2; }
python3 -c "import PIL, requests" || { echo "pip install -r scripts/requirements.txt"; exit 2; }
ls raw/*.txt >/dev/null 2>&1 || { echo "raw/ is empty - nothing to build"; exit 2; }
if [ "$PUBLISH" = 1 ]; then
  command -v gh >/dev/null || { echo "gh CLI missing"; exit 2; }
  gh auth status >/dev/null 2>&1 || { echo "gh not logged in (gh auth login) - aborting before build"; exit 2; }
  [ -d site/.git ] || { echo "site/ is not a git checkout (git clone https://github.com/Bin0754/gpt-image-gallery site)"; exit 2; }
fi
BEFORE=$(python3 -c "import json;print(len(json.load(open('data.json'))['posts']))" 2>/dev/null || echo 0)

# ---- fetch (optional) ----
if [ -n "${X_BEARER_TOKEN:-}" ]; then
  timeout 900 python3 scripts/fetch_x.py --recent
else
  echo "X_BEARER_TOKEN not set: skipping fetch, using existing raw/ ($(ls raw/*.txt | wc -l) files)"
fi

# ---- build ----
timeout 1800 python3 scripts/scrape.py
timeout 600 python3 scripts/build_site.py
AFTER=$(python3 -c "import json;print(len(json.load(open('data.json'))['posts']))")
SHOWN=$(python3 -c "import json;print(json.load(open('prompts.json'))['count'])")
echo "posts: $BEFORE -> $AFTER (shown on site: $SHOWN)"
[ "$PUBLISH" = 1 ] || { echo "== done (no publish)"; exit 0; }

# ---- publish + verify ----
timeout 600 scripts/publish.sh
SHA=$(git -C site rev-parse HEAD)
for i in $(seq 1 40); do
  ST=$(gh api repos/Bin0754/gpt-image-gallery/pages/builds/latest --jq '.status+" "+.commit' 2>/dev/null || true)
  [ "$ST" = "built $SHA" ] && break
  [ "${ST%% *}" = "errored" ] && { echo "Pages build errored: $ST"; exit 4; }
  sleep 15
done
echo "pages: $ST"
LIVE=$(curl -fsS "https://bin0754.github.io/gpt-image-gallery/prompts.json?t=$(date +%s)" | python3 -c "import json,sys;print(json.load(sys.stdin)['count'])") || { echo "live site not reachable"; exit 5; }
echo "live count: $LIVE (expected $SHOWN)"
[ "$LIVE" = "$SHOWN" ] || { echo "WARNING: live count differs (CDN cache?)"; exit 6; }
echo "== refresh ok $(date '+%F %T') UTC+8"
