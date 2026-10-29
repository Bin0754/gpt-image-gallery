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
TPL_V = (SCRIPTS / 'template_video.html').read_text(encoding='utf-8')

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
    "2115457308679676340",  # johnAGI168: 2026-10-29 review, witch costume corset and stockings pose, suggestive
    "2115413787318906998",  # wushi123321: 2026-10-29 review, maid outfit with stockings, borderline suggestive
    "2115366865338003602",  # liyue_ai: 2026-10-29 review, tight short one-shoulder dress pose, borderline suggestive
    "2114563418644468156",  # johnAGI168: 2026-10-27 review, woman relaxing on bed, intimate bedroom, suggestive
    "2114665717136310552",  # Adam38363368936: 2026-10-27 review, slip dress with cardigan sliding off shoulder, borderline suggestive
    "2114753483912175859",  # mylesBaiM: 2026-10-27 review, fishnet stockings pose, suggestive
    "2114835364602880326",  # RougeHalo_AI: 2026-10-27 review, revealing outfit, suggestive
    "2114820382008152116",  # devgetsit: 2026-10-27 review, sultry fire dancer, revealing outfit
    "2114539259004924123",  # alanblogsooooo: 2026-10-27 review, body-focused suggestive mirror selfie
    "2114723911841862008",  # abxxai: 2026-10-27 review, swimwear body reference sheet, borderline
    "2114723945136181702",  # abxxai: 2026-10-27 review, shirtless body reference sheet, borderline
    "2114768364367430071",  # DeepBlueX0: 2026-10-27 review, low-cut lookbook, borderline suggestive
    "2114723928786768066",  # unknown author: 2026-10-27 review, swimsuit pose, borderline suggestive
    "2114275521320386982",  # alanblogsooooo: 2026-10-26 review, body-focused suggestive coser pose
    "2113873415882866834",  # alanblogsooooo: 2026-10-25 review, body-focused suggestive mirror selfie
    "2114013548611317864",  # HumblyAlex: 2026-10-25 review, chat-screenshot commentary, not a prompt
    "2113941069549404359",  # Shoji_ai: 2026-10-25 review, puzzle answer key, not a prompt
    "2113829425448149340",  # _AWAZO: 2026-10-25 review, alt-text description of news graphic, not a prompt
    "2113790319116402803",  # wowwowai: 2026-10-25 review, API deprecation infographic, not a prompt
    "2114046512082886675",  # quadchatapp: 2026-10-25 review, app screenshot alt text, not a prompt
    "2113998570127048843",  # superfang119: 2026-10-25 review, model comparison caption, not a prompt
    "2113590742505730238",  # Mrpinecone888: 2026-10-24 review, suggestive crouching pose in low-cut top
    "2113488085925130261",  # johnAGI168: 2026-10-24 review, suggestive over-the-shoulder pose in short slip dress
    "2113282871594991805",  # johnAGI168 - underwear / lingerie pose (2026-10-23 review)
    "2113164130484158727",  # ritsuto_NFT_Vt - API price/speed comparison, prompt is only an image description (2026-10-23 review)
    "2113369807311835405",  # finnardley - Claude Code automation prompt, not an image prompt (2026-10-23 review)
    "2112893162729681393",  # alanblogsooooo - bikini cleavage selfie (2026-10-22 review)
    "2112851056090829044",  # alanblogsooooo - kneeling from-behind pose, shorts (2026-10-22 review)
    "2110190856636424521",  # hardik_lut83675 - low-cut car selfie, parted lips (2026-10-15 review)
    "2110317210811941251",  # AiVykute - tank top / short shorts pose, uncertain (2026-10-15 review)
    "2109204991533793520",  # suggestive selfie grid (2026-10-12 review)
    "2109121110336008571",  # low-cut crouching pose (2026-10-12 review)
    "2109135933539070327",  # suggestive pool-table pose (2026-10-12 review)
    "2109266767591997675",  # swimsuit comparison (2026-10-12 review)
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
    # 2026-10-13 refresh review (contact sheet)
    '2109486267586986099',                         # @johnAGI168 kneeling lingerie-style fantasy portrait
    '2109545439452361017',                         # @imGopalTiwari loungewear cleavage full-body
    '2109702653970383291',                         # @imGopalTiwari low-cut top / mini skirt pose
    '2109776245227475088',                         # @livybabie anime fishnets, prompt asks legs spread
    '2109751210118902178',                         # @hardik_lut83675 bikini model comparison
    '2109578399228555367',                         # @veronicaahelena cleavage focus
    '2109574354787049514',                         # @veronicaahelena cleavage focus
    '2109573735808405851',                         # @veronicaahelena cleavage focus
    '2109639494886731866',                         # @sequencebyalex text is a caption, not a prompt
    # 2026-10-14 refresh review (contact sheet)
    '2110065031652000004',                         # @RougeHalo_AI lingerie / underwear on bed
    '2109867780673528268',                         # @johnAGI168 high-slit Hancock mirror selfie
    '2110038855315333503',                         # @johnAGI168 crop-top short-skirt portrait (unsure)
    '2109923938767946139',                         # @ann_nnng reply is placeholder, not a real prompt
    # 2026-10-16 refresh review (contact sheet)
    '2110688711398883343',                         # @Mrpinecone888 hotel intimate boudoir / private photoshoot
    '2110805412262105575',                         # @imGopalTiwari bodysuit pin-up squat pose
    '2110756836307591321',                         # @johnAGI168 POV harness/stockings chin-touch
    '2110658042476023908',                         # @DeepBlueX0 school-uniform duck-sit boyfriend POV
    '2110578042686849068',                         # @DeepBlueX0 boyfriend POV intimate chin-touch series
    '2110702477779866100',                         # @spark_chenlin bikini mirror selfie
    '2110718938145292295',                         # @livybabie school-uniform cosplay (unsure)
    '2110851139356758051',                         # @RougeHalo_AI crop-top short-shorts sitting (unsure)
    # 2026-10-18 refresh review (contact sheet)
    '2111223815900381534',                         # @livybabie lingerie / strappy cosplay
    '2111177608058851782',                         # @lishishen7i sheer lace on bed
    '2111343846487437606',                         # @lishishen7i wet sheer gown in pool
    '2110895499318313251',                         # @alanblogsooooo bikini checkered-flag beach
    '2110943314312614262',                         # @alanblogsooooo swimsuit beach POV
    '2111164093847552466',                         # @chatgptpaglu short black dress (unsure)
    '2111128031926632682',                         # @johnAGI168 tight tank / leggings pose (unsure)
    '2111078947144565023',                         # @mehvishs25 crop-top mirror selfie (unsure)
    '2111469082557993258',                         # @johnAGI168 cleavage-focus selfie (unsure)
    '2111452170210136408',                         # @mehvishs25 mini-skirt crop fashion (unsure)
    # 2026-10-19 refresh review (contact sheet)
    '2111725603984486734',                         # @johnAGI168 gym sports-bra mirror selfie
    '2111677535557681278',                         # @inkroom_ai slip nightdress at window (unsure)
    '2111687732703764718',                         # @inkroom_ai towel after swim (unsure)
    '2111933617102372906',                         # @livybabie revealing Halloween cosplay pin-up
    '2111847424826511499',                         # @UBQDHdYKB065819 comparison caption, not a real prompt
    # 2026-10-21 refresh review (contact sheet)
    '2112002720873759067',                         # @livybabie crop-top mini-skirt Halloween cosplay, low-angle lean
    '2112192892127039583',                         # @johnAGI168 doll-like witch, crossed legs in stockings (unsure)
    '2112025758113648812',                         # @johnAGI168 "alluring" Slytherin witch short skirt
    '2112569911645974748',                         # @johnAGI168 silk slip dress tea-room portrait (unsure)
    '2112187761423945827',                         # @alanblogsooooo 辣妹 long-legs short-dress night pose (unsure)
    '2111938096682177000',                         # @momoka_AIIllust cropped-top mini-skirt anime witch (unsure)
    '2112612313786151388',                         # @madeonmade_ 4-model comparison, not a prompt
    '2111999943649227103',                         # @HigenekoTech comparison notes, not a prompt
    '2112539648887239167',                         # @heypickd Midjourney-vs-ChatGPT card alt text, not a prompt


    # 2026-10-28 daily refresh NSFW/suggestive review
    '2114978210526134579',  # @ice_love2_sugoi beach-volleyball bikini beauty (suggestive)
    '2114984190890463375',  # @alanblogsooooo bridal lingerie corset + stockings (suggestive)
    '2114918075753775545',  # @DeepBlueX0 清涼感官 lotus/hanfu low neckline (suggestive)
    '2114913695252058504',  # @aiai_agt 地雷系彼女 short maid dress + stockings (suggestive)
    '2114875883991470257',  # @aiai_agt neon-gal gamer stockings (uncertain → hide)
    '2114946821583761814',  # @johnAGI168 angel/devil clubwear leather (suggestive)
    '2114996079813148722',  # @static_stare translucent liquid-glass gown (sheer/suggestive)
}
# Video posts (video_data.json) hidden after manual review of the poster contact sheet.
VHIDE_IDS = {   # video posts kept in video_data.json but not published (reviewed on the poster contact sheet)
    '2115350279076077786',  # apispace_ai - underwear couple in bathroom, sexual (2026-10-29 review)
    '2115504077434228845',  # oliver031972 - POV gym mat cleavage shot, body-focused, suggestive (2026-10-29 review)
    '2114564425134829621',  # AIwithZeeshi - wet swimsuit beauty ad, borderline suggestive (2026-10-27 review)
    '2114824116943614049',  # YourAlphaMom - gym video, body-focused, borderline suggestive (2026-10-27 review)
    '2114828449902899689',  # Alexneyef - gym video, body-focused, borderline suggestive (2026-10-27 review)
    '2114708250935402521',  # aigenboss - model comparison commentary, not a prompt (2026-10-27 review)
    '2114666738239627660',  # YardenCohe30362 - Kling vs Seedance comparison question, not a prompt (2026-10-27 review)
    '2114383271672856653',  # Miraai_creates - revealing armor outfit, borderline suggestive (2026-10-26 review)
    '2114466414551572626',  # johnmccoyx - model comparison commentary, not a prompt (2026-10-26 review)
    '2114272433503138075',  # NaoyaCreates - setup/cost note for a comparison, not a prompt (2026-10-26 review)
    '2114293043037970508',  # aisamsonreal - comparison question, not a prompt (2026-10-26 review)
    '2114328135420293145',  # Adam38363368936 - only a first-frame instruction, not a prompt (2026-10-26 review)
    '2114356249919881419',  # AsWill11 - commentary about another creator clip, not a prompt (2026-10-26 review)
    '2114338958301880457',  # doctorwasif - prompt cut off mid-sentence (2026-10-26 review)
    '2114413297797837201',  # arsalannazir07 - prompt cut off mid-sentence (2026-10-26 review)
    '2114220288443560087',  # itxsarmadd - prompt cut off mid-sentence (2026-10-26 review)
    '2114271406435299746',  # AIVanta0 - prompt cut off mid-sentence (2026-10-26 review)
    '2114176619019702641',  # MrJeff_Ai - prompt cut off mid-sentence (2026-10-26 review)
    '2114403851365449987',  # Kim_harin05 - prompt cut off mid-sentence (2026-10-26 review)
    '2114297177724129597',  # itxabdullaa - prompt cut off mid-sentence (2026-10-26 review)
    '2113867658101735469',  # ZentrixHQ - low-angle short-skirt game shot, borderline suggestive (2026-10-25 review)
    '2113986953435599342',  # swordBluesy - workflow description, not a prompt (2026-10-25 review)
    '2113808936952627547',  # octopusaia - news caption, not a prompt (2026-10-25 review)
    '2114073499400876355',  # PicsartPlaygrnd - workflow/settings walkthrough, not a prompt (2026-10-25 review)
    '2113470007094972739',  # VibeCaesar - commentary on output/cost, not a prompt (2026-10-24 review)
    '2113488325705420847',  # ZaidVex - lace corset / thigh-high stockings outfit, suggestive (2026-10-24 review)
    '2113510518006935878',  # lifeofgtam - commentary, not a prompt (2026-10-24 review)
    '2113585683348804017',  # imFarhanAi - reply praising a concept, not a prompt (2026-10-24 review)
    '2113609034821492967',  # neuralshockwave - tool template pointer, not a prompt (2026-10-24 review)
    '2113615190239461660',  # Dheepanratnam - caption/joke, not a prompt (2026-10-24 review)
    '2113667092004389012',  # Enzoxbt01 - generic prompt-format advice / model list, not a prompt (2026-10-24 review)
    '2113740907430453542',  # OscarBafta - caption only, not a prompt (2026-10-24 review)
    '2113217153016979594',  # swordBluesy - workflow steps (Claude + Higgsfield), not a prompt (2026-10-23 review)
    '2113185895658738003',  # Justin_lords - Claude ad-research workflow, not a prompt (2026-10-23 review)
    '2113244959990329635',  # AIwithkhan - 'baddie energy' woman in bed poster, uncertain (2026-10-23 review)
    '2112988992350421220',  # YourAlphaMom - 'Instagram model' MILA, bikini/sports-bra cleavage, uncertain (2026-10-22 review)
    '2112993163098902693',  # Alexneyef - same MILA prompt, bikini cleavage, uncertain (2026-10-22 review)
    '2112990596843679772',  # ichelpark - workflow steps (blender blocking), not a prompt (2026-10-22 review)
    '2110408486228021321',  # voyzai - explicit body description, tight low-cut gym outfit (2026-10-15 review)
    '2110277595019276674',  # johnAGI168 - low-angle white stockings / heels doll pose (2026-10-15 review)
    '2110294441080824067',  # liyue_ai - tight top body-motion swap in car, uncertain (2026-10-15 review)
    '2110218035755958328',  # MeenakshiYACS - low leg shot, mini skirt, uncertain (2026-10-15 review)
    '2110283927931744488',  # 0kncn - glowing figure reads as nude silhouette, uncertain (2026-10-15 review)
    # suggestive poster / outfit focus
    '2109182343625732099',  # johnAGI168 - tight mini-dress outfit-change dance
    '2109202785036353857',  # metabo2727 - same outfit-change prompt
    '2103217467984101710',  # Alexneyef - bikini / shirtless close-up
    '2099736809718829064',  # ronxxstudio - cleavage close-up poster
    # text is not an actual video prompt
    '2107593616893845562',  # DavidRunsAds - workflow explanation
    '2106536299356381507',  # hxhxhx0916 - negative prompt only
    '2106574630664257929',  # jarvis11x - workflow notes
    '2090287713945862654',  # beginnersblog1 - process notes
    '2108618981540000162',  # ooffooxx - A/B comparison question
    # 2026-10-13 refresh review
    '2109561889156202577',  # arsalannazir07 - undressed sniper poster
    '2109600808329249250',  # Tech_Apex0 - same prompt / poster
    '2109641513588449531',  # davidsaimastery - squat poster, body/feet focus
    '2109317520700457216',  # ScaleWthAI - giantess low-angle scale-play
    '2109350381331353945',  # geezmedia01 - workflow explanation
    '2109475881051628005',  # alixbuilds - text is not a prompt
    '2109657818899067389',  # yaohui12138 - ad copy, not a prompt
    '2109658531217703330',  # web4miko - random code string, not a prompt
    '2109715744699437492',  # Nothingignore1 - teaser caption, not a prompt
    '2109715239818477741',  # Nothingignore1 - teaser caption, not a prompt
    '2109571731576750427',  # TaliaAariz - prompt cut off mid-sentence in the post
    '2109460837043708104',  # juliaevee - one-line style tag only
    '2109694691432337628',  # smewAI - condensed rewrite of another author's prompt
    # 2026-10-14 refresh review (poster contact sheet)
    '2110141995020632115',  # YourAlphaMom - bikini beach selfie poster
    '2110084200363913570',  # sixugc - workflow tips, not a prompt
    '2109889856793092570',  # garylau_ai - model comparison question, not a prompt
    '2109951019706651045',  # Xanderwow_A - credits/tooling notes, not a prompt
    # 2026-10-16 refresh review (poster contact sheet)
    '2110774943294070795',  # rewind02 - workflow how-to, not a prompt
    '2110884467015307593',  # VibeCaesar - model comparison pricing, not a prompt
    # 2026-10-18 refresh review (poster contact sheet)
    '2111512551578026319',  # voyzai - explicit body / deep-cleavage gym prompt
    '2111072967652212813',  # KeyoAPI - commentary about a prompt, not a usable prompt
    '2111321354964521468',  # AIwithSynthia - fitted crop-top revenge comedy (unsure)
    # 2026-10-19 refresh review (poster contact sheet)
    '2111825583596331312',  # spwfeijen - workflow steps, not a prompt
    '2111725657780810108',  # akiyoshisan - Kling vs Seedance comparison notes
    '2111837361269256575',  # WBK_SZ - Gemini vs Grok comparison notes
    '2111873356937232743',  # thealphatron - Claude previs notes, not a Seedance prompt
    '2111928121179975824',  # gingerpreneur1 - Wan vs Seedance comparison question
    '2111789180946923540',  # DDJCXX - workflow template with placeholders
    '2111620640726040806',  # iX00AI - schoolgirl pool/swimwear (unsure)
    # 2026-10-21 refresh review (poster contact sheet)
    '2112652614944837939',  # YourAlphaMom - explicit body / sports-bra cleavage prompt
    '2112430938005311656',  # ZentrixHQ - WAN vs Seedance comparison, sports-bra fitness (unsure)
    '2112154192534241709',  # Just_sharon7 - low-neck cosplay cleavage poster (unsure)
    '2112499805880713531',  # ElsaSofia__AI - crop top / thigh-strap boots fighter (unsure)
    '2111975176854536287',  # aimikoda - Claude video-edit prompt, not a Seedance prompt
    '2111975795203690555',  # aimikoda - Claude video-edit prompt, not a Seedance prompt
    '2112217172051190206',  # vivistac - pricing promo, not a prompt
    '2112171910134145298',  # theodorsan - ecom marketing tips, not a prompt
    '2112477342576873842',  # scenepond - model comparison, one-line prompt + commentary
    '2112672019557044336',  # Enzoxbt01 - step-by-step guide, not a prompt
    '2112198542026502219',  # georgesttock - UGC workflow notes, not a prompt
    '2112249301468577936',  # 0xPixelMind - shot-chain template / workflow, not a prompt
    '2112140511687414204',  # KeyoAPI - commentary about a prompt, not a usable prompt
    '2112629397635092561',  # zeuuss_01 - character-sheet tutorial, not a Seedance prompt


    # 2026-10-28 daily refresh NSFW / not-a-prompt review
    '2115191029641175400',  # @YourAlphaMom Seedance-vs-Kling gym cleavage comparison (suggestive)
    '2114966761489813857',  # @meAsifAi swimsuit boat shot; body is image prompt not Seedance video prompt
}
VSTATS = {}
VCOUNT = 0          # number of public video posts; shown in the 图片/视频 tab of every page
SITE_DIR = ROOT / 'site'
REPO_STATIC = ROOT / 'repo'
SITE_SCRIPTS = ['fetch_x.py', 'scrape.py', 'extract.py', 'build_site.py', 'template.html', 'queries.json',
                'publish.sh', 'refresh.sh', 'requirements.txt', 'template_video.html']
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
           '__COUNT__': str(st['count']), '__VCOUNT__': str(VCOUNT), '__UPDATED__': st['updated']}
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
                 '{{VCOUNT}}': VSTATS.get('count', 0), '{{VCOUNT25}}': VSTATS.get('n25', 0),
                 '{{VFIRST}}': VSTATS.get('first', ''), '{{VLAST}}': VSTATS.get('last', ''),
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


# ------------------------------------------------------------------ videos
def load_videos():
    f = ROOT / 'video_data.json'
    if not f.exists(): return None, []
    d = json.loads(f.read_text(encoding='utf-8'))
    posts = [p for p in d['posts'] if (INCLUDE_NSFW or not p.get('nsfw_flag')) and p['id'] not in VHIDE_IDS]
    for p in posts: p['language'] = lang_of(p)
    return d, posts


def vstats(d, posts):
    dates = sorted(p['created_at_sh'] for p in posts) or ['']
    gen = datetime.fromisoformat(d['generated_at']).astimezone(SH)
    return {'count': len(posts), 'n25': sum(p['model'].startswith('Seedance 2.5') for p in posts),
            'first': dates[0][:10], 'last': dates[-1][:10], 'authors': len({p['author'] for p in posts}),
            'models': Counter(p['model'] for p in posts), 'updated': gen.strftime('%Y-%m-%d %H:%M')}


def site_videos(posts):
    out = []
    for p in posts:
        p = json.loads(json.dumps(p))
        for v in p['videos']: v['poster_src'] = 'posters/' + v['poster']
        out.append(p)
    return out


def render_videos(d, posts, vst, st):
    payload = {'posts': site_videos(posts), 'count': len(posts), 'n25': vst['n25'], 'first': vst['first'],
               'last': vst['last'], 'updated': vst['updated']}
    js = json.dumps(payload, ensure_ascii=False).replace('</', '<\\/')
    top = max(posts, key=lambda p: p['likes']) if posts else None
    og = SITE_URL + 'posters/' + top['videos'][0]['poster'] if top else ''
    desc = (f"收录 {vst['count']} 条 X 上公开分享的 Seedance AI 视频（其中 Seedance 2.5 {vst['n25']} 条）与完整提示词："
            f"在线播放、搜索、一键复制，并可下载 JSON/CSV。内容版权归原作者。")
    rep = {'__VDESC__': desc, '__SITE_URL__': SITE_URL, '__VOG_IMAGE__': og, '__REPO_URL__': REPO_URL,
           '__ZIP_URL__': ZIP_URL, '__REMOVAL_URL__': REMOVAL_URL, '__SUBMIT_URL__': SUBMIT_URL,
           '__COUNT__': str(st['count']), '__VCOUNT__': str(vst['count']), '__UPDATED__': vst['updated']}
    html = TPL_V
    for k, v in rep.items(): html = html.replace(k, v)
    return html.replace('__DATA__', js)


def write_video_downloads(dest: Path, d, posts):
    recs = []
    for p in sorted(posts, key=lambda p: -p['likes']):
        dt = datetime.strptime(p['created_at_utc'], '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc).astimezone(SH)
        recs.append({'id': p['id'], 'model': p['model'], 'prompt': p['prompt'], 'author': p['author'],
                     'author_url': f"https://x.com/{p['author']}", 'post_url': p['url'],
                     'date': dt.isoformat(timespec='seconds'), 'likes': p['likes'], 'language': p['language'],
                     'prompt_source': p['prompt_source'],
                     'videos': [{'mp4': v['mp4'], 'duration_s': round((v.get('duration_ms') or 0) / 1000, 1),
                                 'poster': 'posters/' + v['poster'], 'width': v.get('w'), 'height': v.get('h')} for v in p['videos']]})
    meta = {'name': 'Seedance 视频提示词 / Seedance video prompts (GPT Image 2.5 提示词图库)',
            'homepage': SITE_URL + 'videos.html', 'repository': REPO_URL,
            'generated_at': datetime.fromisoformat(d['generated_at']).astimezone(SH).isoformat(timespec='seconds'),
            'count': len(recs),
            'license': 'Code: MIT. Videos and prompts belong to their original authors on X; mp4 links point to X (video.twimg.com) and may expire.',
            'fields': {'model': 'Seedance version named in the post (Seedance 2.5 / Seedance 2.0 / ...)',
                       'videos': 'mp4 = X-hosted file (not mirrored), duration_s, poster = local poster frame',
                       'prompt_source': 'post = post text, reply = author\'s own reply, alt = media ALT text'},
            'prompts': recs}
    (dest / 'video_prompts.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    cols = ['id', 'date', 'model', 'author', 'author_url', 'post_url', 'likes', 'language', 'prompt_source', 'prompt', 'mp4', 'duration_s']
    with open(dest / 'video_prompts.csv', 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for r in recs:
            w.writerow({**{c: r[c] for c in cols if c in r}, 'mp4': ' | '.join(v['mp4'] for v in r['videos']),
                        'duration_s': ' | '.join(str(v['duration_s']) for v in r['videos'])})


def export_videos(vd, vposts, vst, st):
    (SITE_DIR / 'videos.html').write_text(render_videos(vd, vposts, vst, st), encoding='utf-8')
    write_video_downloads(SITE_DIR, vd, vposts)
    want = {v['poster'] for p in vposts for v in p['videos']}
    (SITE_DIR / 'posters').mkdir(exist_ok=True)
    for f in (SITE_DIR / 'posters').glob('*'):
        if f.name not in want: f.unlink()
    for name in want:
        src, dst = ROOT / 'posters' / name, SITE_DIR / 'posters' / name
        if not dst.exists() or dst.stat().st_size != src.stat().st_size: shutil.copy2(src, dst)
    print(f"site/ exported: {vst['count']} video posts, {len(want)} posters")


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
    global VCOUNT
    d, posts = load()
    st = stats(d, posts)
    vd, vposts = load_videos()
    vst = vstats(vd, vposts) if vd else None
    VCOUNT = vst['count'] if vst else 0
    VSTATS.update(vst or {})
    if vd:
        (ROOT / 'videos.html').write_text(render_videos(vd, vposts, vst, st), encoding='utf-8')
        write_video_downloads(ROOT, vd, vposts)
        print(f"videos.html + video_prompts.json/csv: {vst['count']} video posts ({vst['n25']} Seedance 2.5)")
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
        if vd: export_videos(vd, vposts, vst, st)
        if a.release_zip: release_zip(ROOT.parent / ZIP_NAME)


if __name__ == '__main__':
    main()
