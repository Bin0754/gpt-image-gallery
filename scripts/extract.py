"""Prompt extraction + post assembly from raw X API v2 JSON responses (raw/*.txt)."""
import json, glob, re, html
from datetime import datetime, timezone, timedelta

GPT25 = re.compile(r'gpt[\s\-_]?image[\s\-_]?2\.?5|gptimage\s?2\.?5|gptimage25|chatgpt images? 2\.5|gpt[\s-]?2\.5', re.I)
MARK = re.compile(r'(?:prompt|提示词|プロンプト|咒语)\s*(?:\([^)\n]{0,30}\))?\s*(?:[:：;]|-\s|\n(?=\S))\s*', re.I)
NSFW = re.compile(r'nsfw|breast|nipple|lustify|上围|巨乳|bikini|👙|lingerie', re.I)
CTA = re.compile(r'see for yourself|try it|which one|which do you|评论|👇|⤵|comment|follow me|save this|下面是之前|目前，@|感谢 @', re.I)
EXCLUDE_IDS = {'2097483045221917131','2102350916435288244','2101391707702964652','2105601628078543292'}
# inline 'prompt' that is really a how-to step list / pointer ("3️⃣ Paste the prompt 4️⃣ Generate", "Prompt below 👇")
STEP_STUB = re.compile(r'^\s*(\d+\s*\ufe0f?\u20e3|[\u2460-\u2473]|\d+\s*[\.\)、])', re.I)
POINTER = re.compile(r'prompt\s*(below|⤵|👇|in (the )?(reply|replies|comments?|alt))|new scenes waiting below|下面|评论区', re.I)
EXCLUDE_TEXT = re.compile(r'full JSON prompt 👆', re.I)
VIDEO_ONLY = re.compile(r'^\W*(\d\W*)?(video prompt|sedance|seedance|video prompt（grok）)', re.I)
TCO = re.compile(r'https://t\.co/\S+')
SH = timezone(timedelta(hours=8))

def load_responses(paths):
    out = []
    for f in paths:
        for line in open(f, encoding='utf-8'):
            line = line.strip()
            if line.startswith('{'):
                try: out.append(json.loads(line))
                except Exception: pass
    return out

def fulltext(p):
    return html.unescape((p.get('note_tweet') or {}).get('text') or p.get('text', ''))

def clean_prompt(s):
    s = TCO.sub('', s)
    s = s.replace('\r', '')
    lines = s.split('\n')
    # strip leading boilerplate lines like "1.. prompt", "..", "Prompt ⤵️", "🖼️ Image Prompt ⤵️"
    boiler = re.compile(r'^\s*([\d\.\s、]*|\.+|[\W_]*)\s*((image|girl|boy|character sheet image)?\s*prompt\s*\d*|提示词|プロンプト)?\s*[:：]?\s*[\W_]*$', re.I)
    while lines and boiler.match(lines[0]):
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    s = '\n'.join(lines).strip()
    s = re.sub(r'^&?gt;\s*', '', s)
    s = re.sub(r'^>\s*', '', s)
    s = re.sub(r'\n{3,}', '\n\n', s)
    paras = s.split('\n\n')
    while len(paras) > 1 and ((CTA.search(paras[-1]) and len(paras[-1]) < 200) or re.fullmatch(r'\s*((#|@)\S+\s*)+', paras[-1])):
        paras.pop()
    s = '\n\n'.join(paras)
    # drop trailing hashtag-only line
    s = re.sub(r'(\n\s*(#\S+\s*)+)$', '', s).strip()
    return s

def build_posts(raw_glob='raw/*.txt'):
    resp = load_responses(sorted(glob.glob(raw_glob)))
    posts, media, users = {}, {}, {}
    for d in resp:
        for p in d.get('data', []) or []:
            # prefer the copy that has note_tweet / more fields
            old = posts.get(p['id'])
            if not old or len(json.dumps(p)) > len(json.dumps(old)):
                posts[p['id']] = p
        inc = d.get('includes', {}) or {}
        for m in inc.get('media', []): 
            if m.get('media_key') not in media or m.get('alt_text'): media[m['media_key']] = m
        for u in inc.get('users', []): users[u['id']] = {**users.get(u['id'], {}), **u}
    # index self-replies by conversation
    replies = {}
    for p in posts.values():
        conv = p.get('conversation_id')
        if not conv or conv == p['id']: continue
        if p.get('in_reply_to_user_id') == p['author_id']:
            replies.setdefault((conv, p['author_id']), []).append(p)
    items = []
    for pid, p in posts.items():
        if p.get('conversation_id') not in (None, pid) and p.get('in_reply_to_user_id') == p['author_id']:
            # it's a self-reply; only keep as standalone if it has its own photos + inline prompt (e.g. DeepBlue reply)
            pass
        t = fulltext(p)
        mks = (p.get('attachments') or {}).get('media_keys', [])
        photos = [media[k] for k in mks if k in media and media[k].get('type') == 'photo' and media[k].get('url')]
        if not photos or pid in EXCLUDE_IDS or EXCLUDE_TEXT.search(t): continue
        alts = [m.get('alt_text', '') for m in photos if m.get('alt_text')]
        if not (GPT25.search(t) or any(GPT25.search(a) for a in alts)): continue
        prompt, source = '', ''
        for m in MARK.finditer(t):
            ws = t.rfind(' ', 0, m.start()); nl = t.rfind('\n', 0, m.start())
            word = t[max(ws, nl) + 1:m.start()]
            if '#' in word: continue          # part of a hashtag like #のぞむプロンプト
            cand = clean_prompt(t[m.end():])
            if STEP_STUB.match(cand) or (POINTER.search(cand) and len(cand) < 160): continue
            if len(cand) >= 8: prompt, source = cand, 'post'; break
        long_alts0 = [a for a in alts if len(a) >= 40 and not a.startswith('AI生成画像')]
        if prompt and long_alts0 and max(len(a) for a in long_alts0) > 3 * len(prompt):
            prompt = ''
        if not prompt:
            long_alts = [a for a in alts if len(a) >= 25 and not a.startswith('AI生成画像')]
            if long_alts:
                uniq = []
                for a in long_alts:
                    a = clean_prompt(re.sub(r'^\s*prompt\s*[:：]?\s*', '', a, flags=re.I))
                    if a and a not in uniq: uniq.append(a)
                prompt, source = '\n\n———\n\n'.join(uniq), 'alt'
        is_root = p.get('conversation_id', pid) == pid
        if not prompt and is_root:
            rs = sorted(replies.get((p.get('conversation_id', pid), p['author_id']), []), key=lambda r: r['created_at'])
            parts = []
            for r in rs:
                rt = fulltext(r)
                if VIDEO_ONLY.match(rt) or re.search(r'video prompt', rt[:40], re.I): continue
                c = clean_prompt(rt)
                c2 = TCO.sub('', c).strip()
                if len(c2) < 40: continue  # links / thanks / short chatter
                if re.match(r'^(try it|inspired by|link)', c2, re.I) or EXCLUDE_TEXT.search(rt): continue
                parts.append(c)
            if parts:
                prompt = '\n\n———\n\n'.join(parts); source = 'reply'
        if not prompt: continue
        u = users.get(p['author_id'], {})
        dt = datetime.strptime(p['created_at'], '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc).astimezone(SH)
        items.append({
            'id': pid,
            'url': f"https://x.com/{u.get('username','i')}/status/{pid}",
            'author': u.get('username', ''), 'author_name': u.get('name', ''),
            'avatar': u.get('profile_image_url', ''),
            'created_at_utc': p['created_at'], 'created_at_sh': dt.strftime('%Y-%m-%d %H:%M'),
            'likes': p['public_metrics']['like_count'],
            'reposts': p['public_metrics'].get('retweet_count', 0),
            'bookmarks': p['public_metrics'].get('bookmark_count', 0),
            'lang': p.get('lang', ''),
            'text': TCO.sub('', t).strip(),
            'prompt': prompt, 'prompt_source': source,
            'images': [{'url': m['url'], 'w': m.get('width'), 'h': m.get('height'), 'media_key': m['media_key']} for m in photos],
            'nsfw_flag': bool(NSFW.search(t + ' ' + prompt)),
        })
    # dedupe: same author + same prompt head, or identical first image
    items.sort(key=lambda x: -x['likes'])
    seen_p, seen_img, out = set(), set(), []
    for it in items:
        kp = (it['author'], re.sub(r'\W', '', it['prompt'])[:150])
        ki = it['images'][0]['url']
        if kp in seen_p or ki in seen_img: continue
        seen_p.add(kp); seen_img.add(ki); out.append(it)
    return out, posts

if __name__ == '__main__':
    out, posts = build_posts()
    print(len(out), 'items from', len(posts), 'posts')
    for it in out:
        print(it['prompt_source'].ljust(5), it['likes'], it['author'], 'NSFW' if it['nsfw_flag'] else '', '|', repr(it['prompt'][:110]))
