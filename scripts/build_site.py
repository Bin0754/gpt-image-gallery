#!/usr/bin/env python3
"""Build the static gallery from data.json (run from anywhere; paths are relative to the repo root).

Outputs (repo root):
  index.html      the website (uses images/ + thumbs/)
  prompts.json    clean download: id, prompt, author, author_url, post_url, date (UTC+8), likes, language, images, prompt_source
  prompts.csv     same as CSV, UTF-8 with BOM (opens correctly in Excel)
  gallery.html    single-file offline version, images embedded as base64 (not committed; shipped in the release zip)

Maintainer-only (when ./site exists = the git checkout published to GitHub Pages, or --export):
  mirrors the public site into site/ and renders repo/ templates (README, LICENSE, docs, issue templates).
  --release-zip  also writes ../gpt-image-gallery.zip (site + gallery.html) for a GitHub Release.
"""
import argparse, base64, csv, io, json, shutil, zipfile
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from PIL import Image

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
TPL = (SCRIPTS / 'template.html').read_text(encoding='utf-8')

REPO = 'Bin0754/gpt-image-gallery'
REPO_URL = f'https://github.com/{REPO}'
SITE_URL = 'https://bin0754.github.io/gpt-image-gallery/'
ZIP_NAME = 'gpt-image-gallery.zip'
ZIP_URL = f'{REPO_URL}/releases/latest/download/{ZIP_NAME}'
REMOVAL_URL = f'{REPO_URL}/issues/new?template=removal-request.yml'
SUBMIT_URL = f'{REPO_URL}/issues/new?template=submit-prompt.yml'

EMBED_SIDE, EMBED_Q = 560, 68          # gallery.html embedded image size / JPEG quality
INCLUDE_NSFW = False
# Not caught by the NSFW keyword filter but too suggestive for a public page (manual review).
HIDE_IDS = {
    "2108846811213660260",  # MissDelulu9 - sultry pose (2026-10-11 review)
    "2108863558587211992",  # liyue_ai - low-cut pose (2026-10-11 review)
    "2108942140273512735",  # Adam38363368936 - suggestive bed selfie (2026-10-11 review)
    "2108930767342784953",  # NoravaleAI - cleavage focus (2026-10-11 review)
    '2098106479710441558',                         # @Hamburgerai boudoir photo
    '2107518927693611115', '2107923039229038753',  # @livybabie
    '2107525779185664150',                         # @RougeHalo_AI lingerie
    # 2026-10-09 refresh review (contact sheet)
    '2108194229193461879',                         # @DeepBlueX0 skin-imprint body close-ups
    '2108228677561426262', '2108421965539094969',  # @johnAGI168 short skirt / crop top portraits
    '2108185506643394640',                         # @liyue_ai low-rise shorts, prompt stresses neckline
    '2108151822711988360',                         # @livybabie cosplay cleavage
    '2108178171409621286',                         # @YUNTJP cleavage reference close-up
    '2108290949994414098',                         # @SDDFounder bikini beach selfie
    '2108414043396469036',                         # @Bozibozai bare-back apron series
    '2108089762015760819',                         # @imGopalTiwari shirtless couple in water
    # 2026-10-10 refresh review (contact sheet)
    '2108523802435137614',                         # @chetaslua Epstein-island grid, bikini/intimate frames
    '2108629489295266035',                         # @DeepBlueX0 flight-attendant cleavage / short skirt low-angle
    '2108505251934326870',                         # @spark_chenlin short skirt / low-neckline sitting portraits
    '2108523890393715127',                         # @lipsticksplus curvy crop-top midriff full-body
}
SITE_DIR = ROOT / 'site'
REPO_STATIC = ROOT / 'repo'
SITE_SCRIPTS = ['fetch_x.py', 'scrape.py', 'extract.py', 'build_site.py', 'template.html', 'queries.json',
                'publish.sh', 'refresh.sh', 'requirements.txt']
SH = timezone(timedelta(hours=8))
LANG_NAMES = {'zh': '中文', 'ja': '日本語', 'en': 'English', 'other': '其他'}
SRC_NAMES = {'post': '帖子正文', 'reply': '作者回复', 'alt': '图片 ALT 文本'}


def lang_of(p):
    if p.get('lang') in ('zh', 'ja', 'en'): return p['lang']
    t = p['prompt']
    if any('\u3040' <= c <= '\u30ff' for c in t): return 'ja'
    if any('\u4e00' <= c <= '\u9fff' for c in t): return 'zh'
    return 'en' if p.get('lang') in ('', 'und', 'qme', 'zxx', None) or t.isascii() else 'other'


def load():
    d = json.loads((ROOT / 'data.json').read_text(encoding='utf-8'))
    posts = [p for p in d['posts'] if (INCLUDE_NSFW or not p.get('nsfw_flag')) and p['id'] not in HIDE_IDS]
    for p in posts: p['language'] = lang_of(p)
    return d, posts


def stats(d, posts):
    dates = sorted(p['created_at_sh'] for p in posts)
    gen = datetime.fromisoformat(d['generated_at']).astimezone(SH)
    return {
        'count': len(posts), 'images': sum(len(p['images']) for p in posts),
        'first': dates[0][:10], 'last': dates[-1][:10], 'authors': len({p['author'] for p in posts}),
        'langs': Counter(p['language'] for p in posts), 'sources': Counter(p['prompt_source'] for p in posts),
        'updated': gen.strftime('%Y-%m-%d %H:%M'),
    }


def render(d, posts, st):
    payload = {k: v for k, v in d.items() if k not in ('posts', 'queries')}
    payload.update(posts=posts, count=len(posts), images=st['images'], first=st['first'], last=st['last'],
                   updated=st['updated'], repo_url=REPO_URL, zip_url=ZIP_URL, removal_url=REMOVAL_URL, submit_url=SUBMIT_URL)
    js = json.dumps(payload, ensure_ascii=False).replace('</', '<\\/')
    top = max(posts, key=lambda p: p['likes'])
    og = SITE_URL + 'thumbs/' + top['images'][0]['thumb']
    desc = (f"收录 {st['count']} 组 X 上公开分享的 GPT Image 2.5 作品与完整提示词：支持中/英/日搜索、按点赞或时间排序、"
            f"一键复制，并可下载 JSON/CSV 数据。开源项目，内容版权归原作者。")
    rep = {'__DESC__': desc, '__SITE_URL__': SITE_URL, '__OG_IMAGE__': og, '__REPO_URL__': REPO_URL,
           '__ZIP_URL__': ZIP_URL, '__REMOVAL_URL__': REMOVAL_URL, '__SUBMIT_URL__': SUBMIT_URL,
           '__COUNT__': str(st['count']), '__UPDATED__': st['updated']}
    html = TPL
    for k, v in rep.items(): html = html.replace(k, v)
    return html.replace('__DATA__', js)


def prompt_records(posts):
    out = []
    for p in sorted(posts, key=lambda p: -p['likes']):
        dt = datetime.strptime(p['created_at_utc'], '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc).astimezone(SH)
        out.append({
            'id': p['id'], 'prompt': p['prompt'], 'author': p['author'],
            'author_url': f"https://x.com/{p['author']}", 'post_url': p['url'],
            'date': dt.isoformat(timespec='seconds'), 'likes': p['likes'], 'language': p['language'],
            'images': ['images/' + im['file'] for im in p['images']], 'prompt_source': p['prompt_source'],
        })
    return out


def write_downloads(dest: Path, d, posts, st):
    recs = prompt_records(posts)
    meta = {
        'name': 'GPT Image 2.5 提示词图库 / GPT Image 2.5 Prompt Gallery',
        'homepage': SITE_URL, 'repository': REPO_URL, 'generated_at': datetime.fromisoformat(d['generated_at']).astimezone(SH).isoformat(timespec='seconds'),
        'count': len(recs),
        'license': 'Code: MIT. Images and prompts belong to their original authors on X; each record links to the original post.',
        'fields': {'id': 'X post id', 'prompt': 'full prompt text as shared by the author', 'author': 'X username',
                   'author_url': 'X profile', 'post_url': 'original post', 'date': 'post time, ISO 8601, UTC+8',
                   'likes': 'like count at collection time', 'language': 'zh | ja | en | other',
                   'images': 'image paths relative to the site root (max 1200px JPEG)',
                   'prompt_source': 'post = post text, reply = author\'s own reply, alt = image ALT text'},
        'prompts': recs,
    }
    (dest / 'prompts.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    cols = ['id', 'date', 'author', 'author_url', 'post_url', 'likes', 'language', 'prompt_source', 'prompt', 'images']
    with open(dest / 'prompts.csv', 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in recs: w.writerow({**{c: r[c] for c in cols}, 'images': ' | '.join(r['images'])})


def b64img(path: Path, side: int, q: int):
    im = Image.open(path).convert('RGB')
    s = min(1.0, side / max(im.size))
    if s < 1: im = im.resize((int(im.width * s), int(im.height * s)), Image.Resampling.LANCZOS)
    buf = io.BytesIO(); im.save(buf, 'JPEG', quality=q, optimize=True, progressive=True)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode(), im.width, im.height


def site_posts(posts):
    out = []
    for p in posts:
        p = json.loads(json.dumps(p))
        for im in p['images']:
            im['thumb_src'] = 'thumbs/' + im['thumb']; im['full_src'] = 'images/' + im['file']
        out.append(p)
    return out


def fill(text, st):
    langs = '，'.join(f"{LANG_NAMES[k]} {v}" for k, v in st['langs'].most_common())
    langs_en = ', '.join(f"{ {'zh':'Chinese','ja':'Japanese','en':'English','other':'other'}[k] } {v}" for k, v in st['langs'].most_common())
    s = st['sources']
    for k, v in {'{{COUNT}}': st['count'], '{{IMAGES}}': st['images'], '{{AUTHORS}}': st['authors'],
                 '{{FIRST}}': st['first'], '{{LAST}}': st['last'], '{{UPDATED}}': st['updated'],
                 '{{LANGS}}': langs, '{{LANGS_EN}}': langs_en,
                 '{{SRC_POST}}': s.get('post', 0), '{{SRC_REPLY}}': s.get('reply', 0), '{{SRC_ALT}}': s.get('alt', 0),
                 '{{SITE_URL}}': SITE_URL, '{{REPO_URL}}': REPO_URL, '{{ZIP_URL}}': ZIP_URL,
                 '{{REMOVAL_URL}}': REMOVAL_URL, '{{SUBMIT_URL}}': SUBMIT_URL}.items():
        text = text.replace(k, str(v))
    return text


def export_site(d, posts, st):
    """Mirror the public site into site/ (git checkout published by publish.sh)."""
    SITE_DIR.mkdir(exist_ok=True)
    (SITE_DIR / 'index.html').write_text(render(d, site_posts(posts), st), encoding='utf-8')
    pub = {k: v for k, v in d.items() if k != 'posts'}
    pub.update(posts=[{k: v for k, v in p.items() if k != 'language'} for p in posts], count=len(posts))
    (SITE_DIR / 'data.json').write_text(json.dumps(pub, ensure_ascii=False, indent=2), encoding='utf-8')
    write_downloads(SITE_DIR, d, posts, st)
    for sub, key in [('images', 'file'), ('thumbs', 'thumb')]:
        want = {im[key] for p in posts for im in p['images']}
        (SITE_DIR / sub).mkdir(exist_ok=True)
        for f in (SITE_DIR / sub).glob('*'):
            if f.name not in want: f.unlink()
        for name in want:
            src, dst = ROOT / sub / name, SITE_DIR / sub / name
            if not dst.exists() or dst.stat().st_size != src.stat().st_size: shutil.copy2(src, dst)
    for f in ['favicon.svg', 'apple-touch-icon.png']:
        if (ROOT / f).exists(): shutil.copy2(ROOT / f, SITE_DIR / f)
    (SITE_DIR / 'scripts').mkdir(exist_ok=True)
    for f in SITE_SCRIPTS:
        if (SCRIPTS / f).exists(): shutil.copy2(SCRIPTS / f, SITE_DIR / 'scripts' / f)
    if REPO_STATIC.exists():   # README / LICENSE / docs / .github templates, with {{placeholders}} filled
        for src in REPO_STATIC.rglob('*'):
            if src.is_dir(): continue
            dst = SITE_DIR / src.relative_to(REPO_STATIC); dst.parent.mkdir(parents=True, exist_ok=True)
            if src.suffix in ('.md', '.yml', '.txt', '') and src.stat().st_size < 200_000:
                dst.write_text(fill(src.read_text(encoding='utf-8'), st), encoding='utf-8')
            else:
                shutil.copy2(src, dst)
    (SITE_DIR / '.nojekyll').write_text('')
    print(f"site/ exported: {st['count']} posts, {st['images']} images")


def release_zip(path: Path):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(SITE_DIR.rglob('*')):
            rel = f.relative_to(SITE_DIR)
            if f.is_dir() or rel.parts[0] == '.git': continue
            z.write(f, f'gpt-image-gallery/{rel.as_posix()}',
                    compress_type=zipfile.ZIP_STORED if f.suffix in ('.jpg', '.png') else zipfile.ZIP_DEFLATED)
        if (ROOT / 'gallery.html').exists():
            z.write(ROOT / 'gallery.html', 'gpt-image-gallery/gallery.html')
    print('release zip', path, round(path.stat().st_size / 1e6, 1), 'MB')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--no-gallery', action='store_true', help='skip the single-file gallery.html')
    ap.add_argument('--export', action='store_true', help='force export to site/ (default: only if site/ exists)')
    ap.add_argument('--release-zip', action='store_true', help=f'write ../{ZIP_NAME} for a GitHub Release')
    a = ap.parse_args()
    d, posts = load()
    st = stats(d, posts)
    (ROOT / 'index.html').write_text(render(d, site_posts(posts), st), encoding='utf-8')
    write_downloads(ROOT, d, posts, st)
    print(f"index.html + prompts.json/csv: {st['count']} posts, {st['images']} images")
    if not a.no_gallery:
        single = []
        for p in posts:
            p = json.loads(json.dumps(p))
            for im in p['images']:
                src, w, h = b64img(ROOT / 'images' / im['file'], EMBED_SIDE, EMBED_Q)
                im['thumb_src'] = im['full_src'] = src; im['tw'], im['th'] = w, h
            single.append(p)
        html = render(d, single, st)
        (ROOT / 'gallery.html').write_text(html, encoding='utf-8')
        print('gallery.html', round(len(html.encode()) / 1e6, 1), 'MB')
    if a.export or SITE_DIR.exists():
        export_site(d, posts, st)
        if a.release_zip: release_zip(ROOT.parent / ZIP_NAME)


if __name__ == '__main__':
    main()
