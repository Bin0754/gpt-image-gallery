#!/usr/bin/env python3
"""Build data.json + download/resize images from raw X MCP search dumps.

Refresh workflow:
  1. Use the `x` MCP tools (search_posts_all / get_posts_by_ids) to re-fetch posts
     about GPT Image 2.5 that contain images + prompts. Save each JSON response
     first-line into raw/*.txt (same format as this repo's raw dumps).
  2. Optionally hydrate author self-replies for "prompt below" posts.
  3. Run:  python3 scrape.py
  4. Rebuild the site:  python3 build_site.py

This script does NOT call X directly — it consumes raw/*.txt already collected.
"""
from __future__ import annotations
import json, os, hashlib, concurrent.futures
from pathlib import Path
from extract import build_posts
from PIL import Image
from io import BytesIO
import requests

ROOT = Path(__file__).resolve().parent
IMG_DIR = ROOT / 'images'
THUMB_DIR = ROOT / 'thumbs'
DATA = ROOT / 'data.json'
MAX_SIDE = 1200
THUMB_SIDE = 480
SESSION = requests.Session()
SESSION.headers['User-Agent'] = 'Mozilla/5.0 GPT-Image-Gallery/1.0'

def fetch_resize(url: str, out: Path, max_side: int, quality=82) -> dict | None:
    try:
        r = SESSION.get(url, timeout=40)
        r.raise_for_status()
        im = Image.open(BytesIO(r.content)).convert('RGB')
        w, h = im.size
        scale = min(1.0, max_side / max(w, h))
        if scale < 1:
            im = im.resize((int(w*scale), int(h*scale)), Image.Resampling.LANCZOS)
        out.parent.mkdir(parents=True, exist_ok=True)
        im.save(out, 'JPEG', quality=quality, optimize=True)
        return {'w': im.width, 'h': im.height, 'bytes': out.stat().st_size}
    except Exception as e:
        print('FAIL', url, e)
        return None

def main():
    items, _ = build_posts(str(ROOT / 'raw' / '*.txt'))
    # prefer larger source images from twimg
    jobs = []
    for it in items:
        for i, img in enumerate(it['images']):
            url = img['url']
            if 'pbs.twimg.com' in url and 'name=' not in url:
                url = url + ('&' if '?' in url else '?') + 'name=large'
            stem = f"{it['id']}_{i}"
            jobs.append((it, i, url, IMG_DIR / f'{stem}.jpg', THUMB_DIR / f'{stem}.jpg'))

    def work(job):
        it, i, url, path, thumb = job
        if path.exists() and thumb.exists():   # already downloaded on a previous run
            a, b = Image.open(path), Image.open(thumb)
            return it['id'], i, path.name, thumb.name, {'w': a.width, 'h': a.height}, {'w': b.width, 'h': b.height}
        meta = fetch_resize(url, path, MAX_SIDE, 84)
        if not meta: return None
        tmeta = fetch_resize(url, thumb, THUMB_SIDE, 78)
        return it['id'], i, path.name, thumb.name, meta, tmeta

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        for res in ex.map(work, jobs):
            if not res: continue
            pid, i, name, tname, meta, tmeta = res
            results.setdefault(pid, {})[i] = {
                'file': name, 'thumb': tname,
                'w': meta['w'], 'h': meta['h'],
                'tw': (tmeta or meta)['w'], 'th': (tmeta or meta)['h'],
            }

    final = []
    for it in items:
        imgs = []
        for i, img in enumerate(it['images']):
            r = results.get(it['id'], {}).get(i)
            if not r: continue
            imgs.append({**img, **r})
        if not imgs: continue
        it = dict(it); it['images'] = imgs
        final.append(it)

    payload = {
        'title': 'GPT Image 2.5 提示词图库',
        'generated_at': __import__('datetime').datetime.now().astimezone().isoformat(timespec='seconds'),
        'count': len(final),
        'queries': [
            '("gpt image 2.5" OR "gpt-image-2.5" OR gptimage2.5 OR gptimage25) prompt has:images -is:retweet',
            '("gpt image 2.5" OR "gpt-image-2.5") (提示词 OR プロンプト OR "prompt:" OR "prompt below") has:images -is:retweet',
            '("gpt image 2.5" OR "gpt-image-2.5") ("prompt:" OR "提示词：") has:images -is:retweet -is:reply',
            'lang:zh / lang:ja variants of the above',
        ],
        'posts': final,
    }
    DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Wrote {DATA} with {len(final)} posts; images in {IMG_DIR}')

if __name__ == '__main__':
    main()
