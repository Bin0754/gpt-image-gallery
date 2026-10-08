#!/usr/bin/env python3
"""Build index.html (uses images/ + thumbs/), gallery.html (single self-contained file, base64 images),
the zip, and the publishable GitHub Pages folder site/ (pushed by publish.sh)."""
import json, base64, zipfile, io, shutil
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent
TPL = (ROOT / 'template.html').read_text(encoding='utf-8')
EMBED_SIDE = 560      # px, longest side for images embedded in gallery.html
EMBED_Q = 68
INCLUDE_NSFW = False
# Posts not flagged by the NSFW keyword filter but visually too suggestive for a public page (manual review).
HIDE_IDS = {
    '2098106479710441558',  # @Hamburgerai boudoir photo
    '2107518927693611115', '2107923039229038753',  # @livybabie
    '2107525779185664150',  # @RougeHalo_AI lingerie
}
SITE_URL = 'https://bin0754.github.io/gpt-image-gallery/'
SITE_DIR = ROOT / 'site'
SITE_FILES = ['favicon.svg', 'apple-touch-icon.png', 'README.md']
SITE_SCRIPTS = ['scrape.py', 'extract.py', 'build_site.py', 'template.html', 'publish.sh']

def load():
    d = json.loads((ROOT / 'data.json').read_text(encoding='utf-8'))
    posts = [p for p in d['posts'] if (INCLUDE_NSFW or not p.get('nsfw_flag')) and p['id'] not in HIDE_IDS]
    return d, posts

def render(d, posts):
    payload = {k: v for k, v in d.items() if k != 'posts'}
    payload['posts'] = posts
    payload['count'] = len(posts)
    js = json.dumps(payload, ensure_ascii=False).replace('</', '<\\/')
    top = max(posts, key=lambda p: p['likes'])
    og = SITE_URL + 'thumbs/' + top['images'][0]['thumb'] if top['images'][0].get('thumb') else ''
    desc = f"从 X 收集的 {len(posts)} 条 GPT Image 2.5 作品与完整提示词，可搜索、按点赞/时间排序、一键复制提示词。"
    return (TPL.replace('__DESC__', desc).replace('__SITE_URL__', SITE_URL)
               .replace('__OG_IMAGE__', og).replace('__DATA__', js))

def b64img(path: Path, side: int, q: int):
    im = Image.open(path).convert('RGB')
    s = min(1.0, side / max(im.size))
    if s < 1: im = im.resize((int(im.width*s), int(im.height*s)), Image.Resampling.LANCZOS)
    buf = io.BytesIO(); im.save(buf, 'JPEG', quality=q, optimize=True, progressive=True)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode(), im.width, im.height

def export_site(d, posts, site_posts):
    """Mirror the public site into site/ (a git repo published to GitHub Pages). Only images of shown posts are copied."""
    SITE_DIR.mkdir(exist_ok=True)
    (SITE_DIR / 'index.html').write_text(render(d, site_posts), encoding='utf-8')
    pub = {k: v for k, v in d.items() if k != 'posts'}
    pub['posts'] = posts; pub['count'] = len(posts)
    (SITE_DIR / 'data.json').write_text(json.dumps(pub, ensure_ascii=False, indent=2), encoding='utf-8')
    for sub, key in [('images', 'file'), ('thumbs', 'thumb')]:
        want = {im[key] for p in posts for im in p['images']}
        (SITE_DIR / sub).mkdir(exist_ok=True)
        for f in (SITE_DIR / sub).glob('*'):
            if f.name not in want: f.unlink()
        for name in want:
            dst = SITE_DIR / sub / name
            if not dst.exists() or dst.stat().st_size != (ROOT / sub / name).stat().st_size:
                shutil.copy2(ROOT / sub / name, dst)
    for f in SITE_FILES:
        if (ROOT / f).exists(): shutil.copy2(ROOT / f, SITE_DIR / f)
    (SITE_DIR / 'scripts').mkdir(exist_ok=True)
    for f in SITE_SCRIPTS:
        if (ROOT / f).exists(): shutil.copy2(ROOT / f, SITE_DIR / 'scripts' / f)
    (SITE_DIR / '.nojekyll').write_text('')
    print('site/ exported:', len(posts), 'posts')

def main():
    d, posts = load()
    # 1) index.html (multi-file site)
    site = []
    for p in posts:
        p = json.loads(json.dumps(p))
        for im in p['images']:
            im['thumb_src'] = 'thumbs/' + im['thumb']; im['full_src'] = 'images/' + im['file']
        site.append(p)
    (ROOT / 'index.html').write_text(render(d, site), encoding='utf-8')
    export_site(d, posts, site)
    # 2) gallery.html (self-contained)
    single = []
    for p in posts:
        p = json.loads(json.dumps(p))
        for im in p['images']:
            src, w, h = b64img(ROOT / 'images' / im['file'], EMBED_SIDE, EMBED_Q)
            im['thumb_src'] = im['full_src'] = src; im['tw'], im['th'] = w, h
        single.append(p)
    html = render(d, single)
    (ROOT / 'gallery.html').write_text(html, encoding='utf-8')
    print('gallery.html', round(len(html.encode())/1e6, 1), 'MB;', len(posts), 'posts')
    # 3) zip of the full site
    zp = ROOT.parent / 'gpt-image-gallery.zip'
    with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in ['index.html', 'gallery.html', 'data.json', 'scrape.py', 'extract.py', 'build_site.py', 'template.html', 'publish.sh', 'README.md', 'favicon.svg', 'apple-touch-icon.png']:
            if (ROOT / f).exists(): z.write(ROOT / f, f'gpt-image-gallery/{f}')
        for sub in ['images', 'thumbs']:
            for f in sorted((ROOT / sub).glob('*.jpg')):
                z.write(f, f'gpt-image-gallery/{sub}/{f.name}', compress_type=zipfile.ZIP_STORED)
        for f in sorted((ROOT / 'raw').glob('*')):
            z.write(f, f'gpt-image-gallery/raw/{f.name}')
    print('zip', zp, round(zp.stat().st_size/1e6, 1), 'MB')

if __name__ == '__main__':
    main()
