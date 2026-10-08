#!/usr/bin/env python3
"""Collect GPT Image 2.5 posts from the X API v2 into raw/*.txt (input for scrape.py).

Usage (from the repo root):
  export X_BEARER_TOKEN=...            # your own X API app token
  python3 scripts/fetch_x.py           # full-archive search  (/2/tweets/search/all, needs Pro/Enterprise access)
  python3 scripts/fetch_x.py --recent  # recent search, last 7 days (/2/tweets/search/recent, Basic tier and up)
  python3 scripts/fetch_x.py --dry-run # print the requests without calling the API

Steps: 1) run every query in scripts/queries.json (pages via next_token);
       2) for posts that say "prompt below 👇" etc. and have no prompt yet, search the author's own
          replies in the same conversation (from:user conversation_id:... is:reply -has:mentions).
Each API response is saved verbatim as one JSON line in raw/<name>.txt.
"""
from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path
import requests

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
RAW = ROOT / 'raw'
API = 'https://api.x.com/2/tweets/search/'
CFG = json.loads((SCRIPTS / 'queries.json').read_text(encoding='utf-8'))


def call(params: dict, recent: bool, dry: bool, token: str | None):
    url = API + ('recent' if recent else 'all')
    if dry:
        print('GET', url, json.dumps(params, ensure_ascii=False)[:300]); return None
    for attempt in range(5):
        r = requests.get(url, params=params, headers={'Authorization': f'Bearer {token}'}, timeout=60)
        if r.status_code == 429:
            reset = int(r.headers.get('x-rate-limit-reset', time.time() + 60))
            wait = max(5, reset - int(time.time()) + 1); print(f'rate limited, sleeping {wait}s'); time.sleep(wait); continue
        r.raise_for_status()
        time.sleep(1.1)   # full-archive search allows ~1 request/second
        return r.json()
    raise SystemExit('too many 429s')


def run(name: str, query: str, pages: int, sort: str, start: str, end: str | None, a) -> int:
    params = {'query': query, 'max_results': 100 if not a.recent else 100, 'sort_order': sort,
              'start_time': start, **CFG['fields']}
    if a.recent: params.pop('start_time')
    if end: params['end_time'] = end
    n = 0
    for page in range(1, pages + 1):
        d = call(params, a.recent, a.dry_run, a.token)
        if d is None: return 0
        (RAW / f'{name}_p{page}.txt').write_text(json.dumps(d, ensure_ascii=False) + '\n', encoding='utf-8')
        n += d.get('meta', {}).get('result_count', 0)
        nt = d.get('meta', {}).get('next_token')
        if not nt: break
        params['next_token'] = nt
    print(f'{name}: {n} posts'); return n


def reply_queries(missing: list[tuple[str, str]], limit=1000) -> list[str]:
    by_user: dict[str, list[str]] = {}
    for user, conv in missing:
        if user: by_user.setdefault(user, []).append(conv)
    groups, cur = [], []
    for user, convs in by_user.items():
        for i in range(0, len(convs), 8):
            part = f"(from:{user} ({' OR '.join('conversation_id:' + c for c in convs[i:i+8])}))"
            q = '(' + ' OR '.join(cur + [part]) + ') is:reply -has:mentions'
            if cur and len(q) > limit:
                groups.append('(' + ' OR '.join(cur) + ') is:reply -has:mentions'); cur = []
            cur.append(part)
    if cur: groups.append('(' + ' OR '.join(cur) + ') is:reply -has:mentions')
    return groups


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--recent', action='store_true', help='use recent search (last 7 days)')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--skip-replies', action='store_true')
    a = ap.parse_args()
    a.token = os.environ.get('X_BEARER_TOKEN')
    if not a.token and not a.dry_run:
        sys.exit('Set X_BEARER_TOKEN (X API v2 app bearer token), or use --dry-run.')
    RAW.mkdir(exist_ok=True)
    start = CFG['start_time']
    for q in CFG['queries']:
        for wi, (s, e) in enumerate(q.get('windows') or [(start, None)]):
            name = q['name'] + (f'_w{wi+1}' if q.get('windows') else '')
            run(name, q['query'], q['pages'], q['sort_order'], s, e, a)
    if a.skip_replies or a.dry_run: return
    sys.path.insert(0, str(SCRIPTS))
    import extract
    extract.build_posts(str(RAW / '*.txt'))
    groups = reply_queries(extract.LAST_MISSING)
    print(f'{len(extract.LAST_MISSING)} posts without a prompt yet -> {len(groups)} self-reply queries')
    for i, q in enumerate(groups, 1):
        run(f'replies_{i:02d}', q, 1, 'recency', start, None, a)


if __name__ == '__main__':
    main()
