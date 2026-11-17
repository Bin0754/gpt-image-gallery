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
TPL_APP = (SCRIPTS / 'template_app.html').read_text(encoding='utf-8')   # one template for index.html + videos.html
import hashlib, re, sys
sys.path.insert(0, str(SCRIPTS))
from extract import IMAGE_MODEL_ORDER, VIDEO_MODEL_ORDER, model_family

REPO = 'Bin0754/gpt-image-gallery'
REPO_URL = f'https://github.com/{REPO}'
SITE_URL = 'https://bin0754.github.io/gpt-image-gallery/'
ZIP_NAME = 'gpt-image-gallery.zip'
ZIP_URL = f'{REPO_URL}/releases/latest/download/{ZIP_NAME}'
REMOVAL_URL = f'{REPO_URL}/issues/new?template=removal-request.yml'
SUBMIT_URL = f'{REPO_URL}/issues/new?template=submit-prompt.yml'

EMBED_SIDE, EMBED_Q = 560, 68          # gallery.html embedded image size / JPEG quality
THUMB_W, THUMB_MAXH, THUMB_Q = 440, 1100, 70   # grid thumbnails: WebP, 440px wide (2x for ~220px mobile columns)
POSTER_W, POSTER_Q = 440, 68                     # video poster frames: WebP
CHUNK0, CHUNK = 60, 500                         # first data chunk (top posts by likes) renders the first screen
MODEL_COLORS = {'GPT Image 2.5': '#7c9cff', 'GPT Image 2.6': '#2dd4bf', 'Nano Banana 2.1': '#facc15', 'Grok Image 2': '#e5e7eb',
                '即梦 5.5': '#fb7185', '即梦 5.0 Pro': '#c084fc', 'Seedance 2.5': '#7c9cff', 'Seedance 2.5 Flash': '#38bdf8',
                'MiniMax H3': '#fb923c', 'Wan 3.0': '#a3e635', '其他 Seedance': '#8b91a1'}
INCLUDE_NSFW = False
# Not caught by the NSFW keyword filter but too suggestive for a public page (manual review).
HIDE_IDS = {
    "2117106809907695738",  # frametheory058: nude keyword in prompt (2026-11-07 review)
    "2118013272712724535",  # DeepBlueX0: 性感私密自拍 series, suggestive (2026-11-07 review)
    "2117503576348192848",  # johnAGI168: bed-level intimate night still, unsure so hidden (2026-11-07 review)
    "2117826273388941719",  # johnAGI168: bed-level intimate morning still, unsure so hidden (2026-11-07 review)
    "2116445874884677706",  # DeepBlueX0: suggestive cosplay selfies (2026-11-01 review)
    "2116355257886224796",  # DeepBlueX0: suggestive silhouette poses (2026-11-01 review)
    "2116416368966807778",  # johnAGI168: suggestive leggy glamour pose (2026-11-01 review)
    "2116518040573538521",  # johnAGI168: suggestive leggy glamour pose (2026-11-01 review)
    "2116467745424638072",  # MissDelulu9: tight mini-dress glamour, unsure so hidden (2026-11-01 review)
    "2115797066438045789",  # RTJLDR: price comparison text, not a prompt; suggestive images (2026-10-30 review)
    "2115856638716379214",  # DrSadek_: model comparison commentary, not a prompt (2026-10-30 review)
    "2115842097890660748",  # FlyAIgh: process notes, not a prompt (2026-10-30 review)
    "2115840090656129334",  # FlyAIgh: process notes, not a prompt (2026-10-30 review)
    "2115838061565161482",  # FlyAIgh: process notes, not a prompt (2026-10-30 review)
    "2115836081107320968",  # FlyAIgh: process notes, not a prompt (2026-10-30 review)
    "2115834066146648279",  # FlyAIgh: process notes, not a prompt (2026-10-30 review)
    "2115831783203774541",  # FlyAIgh: process notes, not a prompt (2026-10-30 review)
    "2115813710862094800",  # wushi123321: maid bedroom pose, suggestive (2026-10-30 review)
    "2115813460541862120",  # AiVideos_eu: pricing news, not a prompt (2026-10-30 review)
    "2115652305710383611",  # alanblogsooooo: body-focused pose, suggestive (2026-10-30 review)
    "2115733642370830754",  # alanblogsooooo: body-focused pose, suggestive (2026-10-30 review)
    "2115656128654622755",  # tsnmediahub: alt-text news card, not a prompt (2026-10-30 review)
    "2115753085184446859",  # xiaoxiaodong: intro text, not a prompt (2026-10-30 review)
    "2115704748888203597",  # kinocode3: alt-text news diagram, not a prompt (2026-10-30 review)
    "2115599773453709374",  # kabumira862571: theme keywords only, not a real prompt (2026-10-30 review)
    "2115940073602699334",  # kabumira862571: theme keywords only, not a real prompt (2026-10-30 review)
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

    # 2026-10-31 daily refresh NSFW review
    '2116013902563586137',  # @johnAGI168 black crop top + stockings armchair pose (suggestive)
    '2116161404923220295',  # @liyue_ai low-cut top lounging (uncertain → hide)
    '2116191790504046669',  # @johnAGI168 crop-top couple on sofa (uncertain → hide)

    # 2026-11-10 one-off 200-scan catch-up review
    '2119019430751715469',  # @DeepBlueX0 swimsuit / water-reveal fashion, suggestive
    '2117108677178228747',  # @alanblogsooooo intimate sunset/bed-adjacent pose, suggestive
    '2117479339046707302',  # @alanblogsooooo rooftop JK crouching pose, suggestive
    '2116796180273508422',  # @alanblogsooooo sushi-bar toast with cleavage focus, suggestive
    '2119837427720491199',  # @lnxinshng252654 bedroom phone look-up, suggestive (unsure → hide)
    '2116765563552936380',  # @alanblogsooooo night flash body-focused selfie, suggestive
    '2116833186785411419',  # @alanblogsooooo GPT-vs-豆包 generation comparison, not a prompt
    '2117544923608306005',  # @liyue_ai nsfw_flag from scrape
    '2117181395873456151',  # @liyue_ai nsfw_flag from scrape
    '2117187479556227389',  # @liyue_ai nsfw_flag from scrape
    '2117534750432727370',  # @CandyTravelight nsfw_flag from scrape
    '2118440862996709872',  # @AIModelRace race-card graphic, not a prompt
    '2117791137809174843',  # @AIModelRace race-card graphic, not a prompt
    '2117269269926834552',  # @AIModelRace race-card graphic, not a prompt
    '2116989526937677838',  # @AIModelRace race-card graphic, not a prompt
    '2118801475753148461',  # @AIModelRace race-card graphic, not a prompt
    '2116968741254635607',  # @Jack_tech_edu LMArena leaderboard preview, not a prompt
    '2119927195980194011',  # @DumbEinstein Seedream radial comparison chart, not a prompt
    '2117460352849834253',  # @VisuraCode loose-vs-template comparison, not a prompt
    '2117180694728475085',  # @kanakanaAIArt short caption, not a real prompt
    '2116911610212270096',  # @alanblogsooo too-short prompt fragment
    # --- 2026-11-17 multi-model review ---
    '2121728716309180634',  # @onoken1025sub suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121803816316076110',  # @johnAGI168 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2118901753923965090',  # @sdjn_wgc suggestive/revealing (2026-11-17 review, when unsure hide)
    '2118357727009276159',  # @sdjn_wgc suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121201759297339607',  # @LoveAiko2003 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2119611294345236615',  # @LoveAiko2003 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2110036716954472471',  # @tealdog2 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2110009680642896306',  # @aisima2046 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121417649288802315',  # @youci290897 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2110903619285647693',  # @aisima2046 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2119437281690014011',  # @AJCreatesAI suggestive/revealing (2026-11-17 review, when unsure hide)
    '2117998185604161762',  # @LoveAiko2003 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2110710510463098955',  # @favprompt suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120060311445164318',  # @youci290897 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2119088855341310206',  # @youci290897 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121110720301384072',  # @libn498262 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121907812473373169',  # @DeepBlueX0 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120863920932196657',  # @youci290897 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121563275498508774',  # @AJCreatesAI suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121975813759521132',  # @nicknickai suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121960695646568923',  # @nicknickai suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120557431109620027',  # @DeepBlueX0 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2122186757726957960',  # @LvZongru9204 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2122198025959510171',  # @libn498262 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121081775963386054',  # @libn498262 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120885067438497997',  # @alanblogsooo suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121934412518695318',  # @libn498262 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120392940787003766',  # @LvZongru9204 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120156034904018948',  # @allinGoabroad suggestive/revealing (2026-11-17 review, when unsure hide)
    '2119803891818873147',  # @LvZongru9204 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2119776316027445535',  # @youci290897 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2122380409665376327',  # @libn498262 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121253331758985680',  # @libn498262 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121122513879290167',  # @LvZongru9204 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2122163308958818733',  # @LvZongru9204 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120136395813732615',  # @ChanJunor23588 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2119451606140006740',  # @youci290897 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2109535859435532795',  # @ai_lady_ready suggestive/revealing (2026-11-17 review, when unsure hide)
    '2122172628198920380',  # @LvZongru9204 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2122229509047112010',  # @libn498262 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2122230018428580073',  # @LvZongru9204 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2122250459549209069',  # @AJCreatesAI suggestive/revealing (2026-11-17 review, when unsure hide)
    '2122215119962931621',  # @sumistudio_ai suggestive/revealing (2026-11-17 review, when unsure hide)
    '2122383662302081142',  # @libn498262 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2122377667102355641',  # @libn498262 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2122373684086423942',  # @libn498262 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121255457658478890',  # @libn498262 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120768740308738501',  # @cyazierpen suggestive/revealing (2026-11-17 review, when unsure hide)
    '2122263956358398318',  # @LvZongru9204 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2122164761660141910',  # @libn498262 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2122139950905004226',  # @LvZongru9204 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121978368518422956',  # @libn498262 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121918227047698873',  # @nicknickai suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121765049245004137',  # @ZabojcaKomarow suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121537889637147049',  # @wu_jinchan12113 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120542070435975403',  # @taoartc suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120058743014699342',  # @taoartc suggestive/revealing (2026-11-17 review, when unsure hide)
    '2119958092490457165',  # @youci290897 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2118921498237034634',  # @DeepBlueX0 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2118906367369155018',  # @youci290897 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2118517866417082659',  # @akiba_tokyo_jp suggestive/revealing (2026-11-17 review, when unsure hide)
    '2118359110123229470',  # @youci290897 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2118333443272835388',  # @youci290897 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2116909496798998716',  # @ModelPurposeAI suggestive/revealing (2026-11-17 review, when unsure hide)
    '2116544790997484013',  # @ModelPurposeAI suggestive/revealing (2026-11-17 review, when unsure hide)
    '2110711519696576982',  # @favprompt suggestive/revealing (2026-11-17 review, when unsure hide)
    '2122494038880493730',  # @AcornerVJ suggestive/revealing (2026-11-17 review, when unsure hide)
    '2122380651433209874',  # @FuguiChen1314 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121450709715660928',  # @libn498262 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121444288198561799',  # @libn498262 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121441900238663696',  # @libn498262 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121439238554280299',  # @libn498262 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121292004806045852',  # @nicknickai suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121280614867632248',  # @nicknickai suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121224662357270872',  # @wanzhousu1 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121179194994659364',  # @nicknickai suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121105365244809259',  # @Mxfo888 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121083158338977889',  # @libn498262 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120949066536570985',  # @Mxfo888 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120935903292186836',  # @Mxfo888 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120884014638862525',  # @youci290897 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120882901759963401',  # @Mxfo888 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120872789523787907',  # @Mxfo888 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120862450132406560',  # @taoartc suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120823578417365319',  # @ChanJunor23588 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120816034378821753',  # @Mxfo888 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120806584297418899',  # @Mxfo888 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120799057350123839',  # @Mxfo888 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121910580848242814',  # @nicknickai suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121902728767267098',  # @nicknickai suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121803366229815590',  # @libn498262 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121802236645019836',  # @libn498262 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121799366931611880',  # @libn498262 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121764299828015297',  # @nicknickai suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120547991404826986',  # @ChanJunor23588 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120531483215462794',  # @ChanJunor23588 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120458825476219104',  # @ChanJunor23588 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120449076621947197',  # @taoartc suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120394446563119183',  # @ChanJunor23588 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120391085415637366',  # @taoartc suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120308619199799423',  # @ChanJunor23588 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120176297641160943',  # @taoartc suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120152655238447222',  # @AJCreatesAI suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120101020923748757',  # @taoartc suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120028801090687014',  # @taoartc suggestive/revealing (2026-11-17 review, when unsure hide)
    '2119996745275027706',  # @taoartc suggestive/revealing (2026-11-17 review, when unsure hide)
    '2119823549510951014',  # @taoartc suggestive/revealing (2026-11-17 review, when unsure hide)
    '2119805960839664094',  # @taoartc suggestive/revealing (2026-11-17 review, when unsure hide)
    '2119795323120058436',  # @taoartc suggestive/revealing (2026-11-17 review, when unsure hide)
    '2119729888865419525',  # @taoartc suggestive/revealing (2026-11-17 review, when unsure hide)
    '2118899973450608660',  # @akiba_tokyo_jp suggestive/revealing (2026-11-17 review, when unsure hide)
    '2122005978845683940',  # @Vici_001 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2122004890411217010',  # @Vici_001 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2114911076873843133',  # @tealdog2 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2120533471244505183',  # @Mxfo888 suggestive/revealing (2026-11-17 review, when unsure hide)
    '2118305330048512449',  # @knoxtwts UI screenshot, not artwork (2026-11-17 review)
    '2121156670868844655',  # @jhl880617 benchmark chart, not artwork (2026-11-17 review)
    '2120359868096024877',  # @yyyole UI screenshot, not artwork (2026-11-17 review)
    '2121896705679638593',  # @MengTo UI screenshot, not artwork (2026-11-17 review)
    '2121850353436315870',  # @asakouhinomu caption only (参照画像/生成画像), no prompt (2026-11-17 review)
    '2121548897764139507',  # @RTJLDR model name only, no prompt (2026-11-17 review)
    '2119779478654312642',  # @SethCritchley credit line only, no prompt (2026-11-17 review)
    '2120524136342753725',  # @FromSummerF comparison note, not a prompt (2026-11-17 review)
    '2121010883770101863',  # @asakouhinomu caption only, no prompt (2026-11-17 review)
    '2120341703718781355',  # @LvZongru9204 truncated prompt fragment (2026-11-17 review)
    '2121343792133366180',  # @greghunkins "Seedream 5.5 on" fragment, no prompt (2026-11-17 review)
    '2116199841873436785',  # @asakouhinomu caption only, no prompt (2026-11-17 review)
    '2119607888591438246',  # @youci290897 truncated prompt header only (2026-11-17 review)
    '2118850710200783272',  # @akiba_tokyo_jp prompt is only in the image, text is a caption (2026-11-17 review)
    '2111744107248771443',  # @heathergreen prompt fragment (2026-11-17 review)
    '2117702991667249456',  # @Brothershade caption, no prompt (2026-11-17 review)
    '2119237205357150550',  # @akiba_tokyo_jp caption only (2026-11-17 review)
    '2118958115534344703',  # @akiba_tokyo_jp caption only (2026-11-17 review)
    '2121011713680302207',  # @asakouhinomu caption only, no prompt (2026-11-17 review)
    '2119256206019899672',  # @einsburnz model ranking list, not a prompt (2026-11-17 review)
    '2120782624348090824',  # @ft4ht0 reference-id instruction only (2026-11-17 review)
    '2120706042413842697',  # @ft4ht0 reference-id instruction only (2026-11-17 review)
    '2119645628829708456',  # @akiba_tokyo_jp caption only (2026-11-17 review)
    '2118613074546720998',  # @akiba_tokyo_jp caption only (2026-11-17 review)
    '2121011145528213983',  # @asakouhinomu caption only, no prompt (2026-11-17 review)
    '2119324038992482477',  # @CandyTravelight truncated prompt header only (2026-11-17 review)
    '2108112665818406964',  # @dreamydigiarts suggestive/revealing (2026-11-17 review, when unsure hide)
    '2108475052437983290',  # @dreamydigiarts suggestive/revealing (2026-11-17 review, when unsure hide)
}
# Video posts (video_data.json) hidden after manual review of the poster contact sheet.
VHIDE_IDS = {
    # --- 2026-11-16 catch-up review ---
    "2120202866908344535",  # YourAlphaMom: sports-bra model comparison, suggestive close-ups (2026-11-16 review)
    "2121715884666360217",  # YourAlphaMom: gym selfie in sports bra, suggestive (2026-11-16 review)
    "2120935540346196065",  # YourAlphaMom: low-angle gym aisle shot in tight shorts (2026-11-16 review)
    "2121312739469713463",  # YourAlphaMom: body-focused street shot in tight shorts (2026-11-16 review)
    "2120577042232283381",  # YourAlphaMom: body-focused waterfront shot in tight athletic wear, unsure so hidden (2026-11-16 review)
    "2121902564585152869",  # Galupus: sports-bra model comparison, suggestive close-ups (2026-11-16 review)
    "2120439367537745972",  # RDV1113: sports-bra model comparison, suggestive (2026-11-16 review)
    "2121113184706920701",  # doctorwasif: gym camcorder "crush" vlog in sports bra, suggestive (2026-11-16 review)
    "2121460616007237981",  # dreamydigiarts: prompt asks for a sensual crop-top pose (2026-11-16 review)
    "2121823004673892524",  # dreamydigiarts: prompt asks for sexy unbuttoned-shirt pose (2026-11-16 review)
    "2121392675115180176",  # john87445528: bedroom vanity shot in a crop/bra, suggestive (2026-11-16 review)
    "2120622093314437276",  # Mavern_0x: wet thin top on a city sidewalk, unsure so hidden (2026-11-16 review)
    "2120155516483838107",  # leayaana: Picsart CTA / which-scene question, not a real prompt (2026-11-16 review)
    "2120520544106041729",  # leayaana: Picsart CTA / which-won question, not a real prompt (2026-11-16 review)
    "2121699850417004920",  # leayaana: Picsart CTA / which-part question, not a real prompt (2026-11-16 review)
    "2121861899050737820",  # dreamina_brys: "comment 4 for the prompt" bait, no real prompt (2026-11-16 review)
    "2121910205361574044",  # dreamina_gharl: settings/hashtag bait, no real prompt (2026-11-16 review)
    "2121139401829093754",  # dreamina_muha: settings/hashtag bait, no real prompt (2026-11-16 review)
    "2120100091113689580",  # Nothingignore1: title-only matchup ("Dom Toretto Vs. Hobbs"), not a prompt (2026-11-16 review)
    "2121997651935678717",  # Nothingignore1: title-only matchup, not a prompt (2026-11-16 review)
    "2121168687344582949",  # Nothingignore1: title-only matchup, not a prompt (2026-11-16 review)
    "2121163329549082893",  # Nothingignore1: title-only matchup, not a prompt (2026-11-16 review)
    "2121625892153860358",  # Nothingignore1: title-only matchup, not a prompt (2026-11-16 review)
    "2122255578189734252",  # Nothingignore1: episode title only, not a prompt (2026-11-16 review)
    "2121109662741438925",  # IqbalIrm34136: title-only matchup, not a prompt (2026-11-16 review)
    "2121576785624379681",  # IqbalIrm34136: title-only matchup, not a prompt (2026-11-16 review)
    "2120897290521186402",  # IqbalIrm34136: thanks/shout-out text, not a prompt (2026-11-16 review)
    "2120969630470611248",  # Qweex_eth: "Would you watch..." question, not a prompt (2026-11-16 review)
    "2121663973380780240",  # esrhengwu: Kling vs Seedance comment, not a prompt (2026-11-16 review)
    "2121046211943956561",  # postandfly: hashtags only, not a prompt (2026-11-16 review)
    "2122149940793147470",  # JuanScaleAds: ad CTA, not a prompt (2026-11-16 review)
    "2122130065819644132",  # TheGeoJournal: commentary, not a prompt (2026-11-16 review)
    "2118923904890613803",  # MeenakshiYACS: Sexy keyword in prompt (2026-11-07 review)
    "2118773221520793984",  # Mavern_0x: erotic office prompt (2026-11-07 review)   # video posts kept in video_data.json but not published (reviewed on the poster contact sheet)
    '2116450848347652254',  # Tomdotdev: suggestive close-up in shorts (2026-11-01 review)
    '2116635769729323171',  # YourAlphaMom: model comparison question poster (2026-11-01 review)
    '2116533722723864694',  # voyzai: ad with truncated prompt fragment, not a real prompt (2026-11-01 review)
    '2115788980969185474',  # oliver031972: cleavage sports-bra vlog, suggestive (2026-10-30 review)
    '2115874033803862236',  # Sjaano81: speed/cost comparison, not a prompt (2026-10-30 review)
    '2115734110715236487',  # wootjie18: product ad, not a prompt (2026-10-30 review)
    '2115862815898808553',  # PixelDojoAI: excerpt of an image prompt, not the video prompt (2026-10-30 review)
    '2115830154538713121',  # whoisnilo: result description, not a real prompt (unsure) (2026-10-30 review)
    '2115636407616123255',  # ZentrixHQ: one-line fragment, not a real prompt (2026-10-30 review)
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

    # 2026-10-31 daily refresh NSFW review
    '2116284031067476106',  # @YourAlphaMom cleavage selfie (suggestive)
    '2116111120566247680',  # @dreamydigiarts skin-tight bodysuit selfie (suggestive)
    '2116197269636595940',  # @Niaoshubaba process commentary, no actual prompt
    '2116029909667827737',  # @ayzalnooor24521 character/outfit reference-sheet image prompt, not a Seedance video prompt

    # 2026-11-10 one-off 200-scan catch-up review
    '2118246827778875740',  # @MeenakshiYACS Sexy keyword in prompt
    '2118476249056067682',  # @YourAlphaMom nsfw_flag + process-style camcorder prompt
    '2119132023130636322',  # @Mavern_0x nsfw_flag
    '2117633599872614540',  # @ZentrixHQ recreate-@Video1 process instruction, not a Seedance prompt
    '2116934648857346272',  # @Nabilidosoo process/pose description referencing @ video
    '2117112373878395194',  # @AIwithWania too-short prompt fragment
    '2118605889074807152',  # @ankit_jhaa_ turnaround-sheet duplicate/process
    '2118223256314585274',  # @dreamina_muha settings/hashtags only, not a prompt
    '2118223242746040410',  # @dreamina_prei settings/hashtags only, not a prompt
    '2118223238820196536',  # @dreamina_brys settings/hashtags only, not a prompt
    # --- 2026-11-17 multi-model review ---
    '2122385276462883315',  # @devgetsit suggestive/revealing (2026-11-17 review, when unsure hide)
    '2121863238501753062',  # @boniusex deployment tutorial text, not a prompt (2026-11-17 review)
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


# ------------------------------------------------------------------ fast app pages (index.html / videos.html)
def webp_thumb(src: Path, dst: Path, w: int, q: int, maxh=None):
    """Small WebP derivative for the grid (cached: only built once per file)."""
    if dst.exists():
        with Image.open(dst) as im: return im.width, im.height
    im = Image.open(src).convert('RGB')
    sc = min(1.0, w / im.width)
    if maxh: sc = min(sc, maxh / im.height)
    if sc < 1: im = im.resize((max(1, round(im.width * sc)), max(1, round(im.height * sc))), Image.Resampling.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, 'WEBP', quality=q, method=5)
    return im.width, im.height


def prepare_media(posts, videos):
    """Point every card at a WebP thumbnail / poster (built from the 1200px image / 480px poster)."""
    import concurrent.futures as cf
    jobs = [(im, ROOT / 'images' / im['file'], ROOT / 'thumbs' / (Path(im['file']).stem + '.webp'), THUMB_W, THUMB_Q, THUMB_MAXH)
            for p in posts for im in p['images']]
    jobs += [(v, ROOT / 'posters' / v['poster'], ROOT / 'posters' / (Path(v['poster']).stem + '.webp'), POSTER_W, POSTER_Q, None)
             for p in videos for v in p['videos']]
    def work(j):
        obj, src, dst, w, q, mh = j
        return obj, dst.name, webp_thumb(src, dst, w, q, mh)
    with cf.ThreadPoolExecutor(8) as ex:
        for obj, name, (w, h) in ex.map(work, jobs):
            if 'file' in obj: obj['thumb'], obj['tw'], obj['th'] = name, w, h
            else: obj['poster'], obj['pw'], obj['ph'] = name, w, h


def img_record(p):
    r = {'i': p['id'], 'a': p['author'], 'n': p.get('author_name', ''), 'av': short_av(p.get('avatar', '')), 'd': p['created_at_sh'],
         'l': p['likes'], 'r': p.get('reposts', 0), 'g': p['language'], 'm': p.get('model') or 'GPT Image 2.5',
         's': p['prompt_source'], 'p': p['prompt'],
         'im': [[im.get('thumb_src') or 'thumbs/' + im['thumb'], im['tw'], im['th'], im.get('full_src') or 'images/' + im['file'], im['w'], im['h']] for im in p['images']]}
    add_text(r, p)
    return r


def short_av(u):   # lean JSON: the template re-adds these well-known prefixes
    return u[len('https://pbs.twimg.com/profile_images/'):] if u.startswith('https://pbs.twimg.com/profile_images/') else u


def short_vt(u):
    u = u or ''
    return u[len('https://video.twimg.com/'):] if u.startswith('https://video.twimg.com/') else u


def add_text(r, p):
    """Original post text is only kept when it adds context (prompt from a reply / ALT); capped for lean chunks."""
    x = (p.get('text') or '').strip()
    if x and p['prompt_source'] != 'post' and x != p['prompt'].strip(): r['x'] = x[:600]


def vid_record(p):
    r = {'i': p['id'], 'a': p['author'], 'n': p.get('author_name', ''), 'av': short_av(p.get('avatar', '')), 'd': p['created_at_sh'],
         'l': p['likes'], 'g': p['language'], 'm': p['model'], 'f': model_family(p['model']), 's': p['prompt_source'], 'p': p['prompt'],
         'v': [['posters/' + v['poster'], v['pw'], v['ph'], v.get('duration_ms') or 0, short_vt(v.get('mp4')),
                1 if v.get('mp4_low') == v.get('mp4') else short_vt(v.get('mp4_low')), v.get('views') or 0] for v in p['videos']]}
    add_text(r, p)
    return r


PAGE = {
    'image': dict(file='index.html', title='AI 提示词图库 · GPT Image / Nano Banana / Grok / 即梦 作品与完整提示词',
                  tagline='X 上头部 AI 生图模型的真实作品，每张图都附完整提示词，一键复制',
                  placeholder='搜索提示词或作者，例如：海报、像素、travel、cinematic',
                  foot='图片与提示词版权归各原作者所有，每条内容均附 X 原帖链接；本站仅做整理与索引，与 OpenAI / Google / xAI / 字节跳动无任何关联。'),
    'video': dict(file='videos.html', title='AI 提示词图库 · AI 视频提示词（Seedance / MiniMax H3 / Wan 3.0）',
                  tagline='X 上头部 AI 视频模型的作品，每条都附完整提示词，点开即可播放',
                  placeholder='搜索视频提示词或作者，例如：cinematic、打戏、アニメ、vlog',
                  foot='视频与提示词版权归各原作者所有，视频直接从 X（video.twimg.com）播放，本站不存储视频文件；本站仅做整理与索引，与各模型厂商无任何关联。'),
}


def write_app(kind, dest: Path, recs, st, vcount, icount, inline=False):
    """Write dest/index.html or dest/videos.html (small shell + inline manifest) and dest/data/<kind>-N-<hash>.json chunks."""
    cfg = PAGE[kind]
    recs = sorted(recs, key=lambda r: -r['l'])
    fam = (lambda r: r['f']) if kind == 'video' else (lambda r: r['m'])
    counts = Counter(fam(r) for r in recs)
    order = (VIDEO_MODEL_ORDER + ['其他 Seedance']) if kind == 'video' else IMAGE_MODEL_ORDER
    models = [m for m in order if counts.get(m)] + [m for m in counts if m not in order]
    names = []
    if not inline:
        ddir = dest / 'data'; ddir.mkdir(parents=True, exist_ok=True)
        for f in ddir.glob(f'{kind}-*.json'): f.unlink()
        chunks = [recs[:CHUNK0]] + [recs[i:i + CHUNK] for i in range(CHUNK0, len(recs), CHUNK)]
        for k, c in enumerate(chunks):
            b = json.dumps(c, ensure_ascii=False, separators=(',', ':')).encode()
            name = f'data/{kind}-{k}-{hashlib.sha1(b).hexdigest()[:10]}.json'
            (dest / name).write_bytes(b); names.append(name)
    dates = sorted(r['d'] for r in recs) or ['']
    man = {'kind': kind, 'count': len(recs), 'media': sum(len(r.get('im') or r.get('v')) for r in recs),
           'first': dates[0][:10], 'last': dates[-1][:10], 'models': models, 'counts': dict(counts),
           'colors': {m: MODEL_COLORS.get(m, '#8b91a1') for m in models}, 'chunks': names}
    if inline: man['inline'] = recs
    mlist = '、'.join(f'{m} {counts[m]}' for m in models)
    if kind == 'image':
        intro = (f'<b>这是什么？</b>收录 <b>{len(recs)}</b> 组 X（Twitter）用户公开分享的 AI 生图作品（共 {man["media"]} 张图），'
                 f'覆盖头部模型：{mlist}。每组都附作者给出的<b>完整提示词</b>和原帖链接；点上方模型标签即可分类浏览。')
    else:
        intro = (f'<b>视频专区：</b>收录 <b>{len(recs)}</b> 条 X 用户公开分享的 AI 视频：{mlist}。每条都附<b>完整提示词</b>；'
                 '视频在点开（或桌面端悬停）后才从 X 加载，列表只加载压缩封面。')
    top = recs[0] if recs else None
    cdn = f'https://cdn.jsdelivr.net/gh/{REPO}@main/'
    og = (cdn + (top['im'][0][3] if kind == 'image' else top['v'][0][0])) if top and not inline else ''
    desc = (f"收录 {len(recs)} {'组' if kind == 'image' else '条'} X 上公开分享的 AI {'图片' if kind == 'image' else '视频'}与完整提示词（{mlist}）："
            "按模型分类、中/英/日搜索、按点赞或时间排序、一键复制，并可下载 JSON/CSV。内容版权归原作者。")
    rep = {'__TITLE__': cfg['title'], '__DESC__': desc, '__PAGE_URL__': SITE_URL + ('' if kind == 'image' else 'videos.html'),
           '__OG_IMAGE__': og, '__REFERRER__': '<meta name="referrer" content="no-referrer">',
           '__TAGLINE__': cfg['tagline'], '__PLACEHOLDER__': cfg['placeholder'], '__FOOT1__': cfg['foot'], '__INTRO__': intro,
           '__TAB_IMG__': 'class="on" aria-current="page"' if kind == 'image' else '',
           '__TAB_VID__': 'class="on" aria-current="page"' if kind == 'video' else '',
           '__COUNT__': str(icount), '__VCOUNT__': str(vcount), '__UPDATED__': st['updated'],
           '__REPO_URL__': REPO_URL, '__ZIP_URL__': ZIP_URL, '__REMOVAL_URL__': REMOVAL_URL, '__SUBMIT_URL__': SUBMIT_URL}
    html = TPL_APP
    if inline or not names: html = re.sub(r'<link rel="preload" href="__CHUNK0__"[^>]*>\n', '', html)
    else: html = html.replace('__CHUNK0__', names[0])
    for k, v in rep.items(): html = html.replace(k, v)
    html = html.replace('__MANIFEST__', json.dumps(man, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/'))
    (dest / cfg['file']).write_text(html, encoding='utf-8')
    return html


def prompt_records(posts):
    out = []
    for p in sorted(posts, key=lambda p: -p['likes']):
        dt = datetime.strptime(p['created_at_utc'], '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc).astimezone(SH)
        out.append({
            'id': p['id'], 'model': p.get('model') or 'GPT Image 2.5', 'prompt': p['prompt'], 'author': p['author'],
            'author_url': f"https://x.com/{p['author']}", 'post_url': p['url'],
            'date': dt.isoformat(timespec='seconds'), 'likes': p['likes'], 'language': p['language'],
            'images': ['images/' + im['file'] for im in p['images']], 'prompt_source': p['prompt_source'],
        })
    return out


def write_downloads(dest: Path, d, posts, st):
    recs = prompt_records(posts)
    meta = {
        'name': 'AI 提示词图库 / AI Prompt Gallery',
        'models': dict(Counter(p.get('model') or 'GPT Image 2.5' for p in posts)),
        'homepage': SITE_URL, 'repository': REPO_URL, 'generated_at': datetime.fromisoformat(d['generated_at']).astimezone(SH).isoformat(timespec='seconds'),
        'count': len(recs),
        'license': 'Code: MIT. Images and prompts belong to their original authors on X; each record links to the original post.',
        'fields': {'id': 'X post id', 'model': 'AI image model named in the post (GPT Image 2.5 / GPT Image 2.6 / Nano Banana 2.1 / Grok Image 2 / 即梦 5.5 / 即梦 5.0 Pro)', 'prompt': 'full prompt text as shared by the author', 'author': 'X username',
                   'author_url': 'X profile', 'post_url': 'original post', 'date': 'post time, ISO 8601, UTC+8',
                   'likes': 'like count at collection time', 'language': 'zh | ja | en | other',
                   'images': 'image paths relative to the site root (max 1200px JPEG)',
                   'prompt_source': 'post = post text, reply = author\'s own reply, alt = image ALT text'},
        'prompts': recs,
    }
    (dest / 'prompts.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    cols = ['id', 'date', 'model', 'author', 'author_url', 'post_url', 'likes', 'language', 'prompt_source', 'prompt', 'images']
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
    write_app('image', SITE_DIR, [img_record(p) for p in posts], st, VCOUNT, st['count'])
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


def write_video_downloads(dest: Path, d, posts):
    recs = []
    for p in sorted(posts, key=lambda p: -p['likes']):
        dt = datetime.strptime(p['created_at_utc'], '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc).astimezone(SH)
        recs.append({'id': p['id'], 'model': p['model'], 'model_family': model_family(p['model']), 'prompt': p['prompt'], 'author': p['author'],
                     'author_url': f"https://x.com/{p['author']}", 'post_url': p['url'],
                     'date': dt.isoformat(timespec='seconds'), 'likes': p['likes'], 'language': p['language'],
                     'prompt_source': p['prompt_source'],
                     'videos': [{'mp4': v['mp4'], 'duration_s': round((v.get('duration_ms') or 0) / 1000, 1),
                                 'poster': 'posters/' + v['poster'], 'width': v.get('w'), 'height': v.get('h')} for v in p['videos']]})
    meta = {'name': 'AI 视频提示词 / AI video prompts (AI 提示词图库)',
            'homepage': SITE_URL + 'videos.html', 'repository': REPO_URL,
            'generated_at': datetime.fromisoformat(d['generated_at']).astimezone(SH).isoformat(timespec='seconds'),
            'count': len(recs),
            'license': 'Code: MIT. Videos and prompts belong to their original authors on X; mp4 links point to X (video.twimg.com) and may expire.',
            'models': dict(Counter(p['model'] for p in posts)),
            'fields': {'model': 'video model named in the post (Seedance 2.5 / Seedance 2.5 Pro / Seedance 2.5 Flash / MiniMax H3 / Wan 3.0; older Seedance versions as named)',
                       'model_family': 'filter group used on the site (Seedance 2.5 Pro counts as Seedance 2.5)',
                       'videos': 'mp4 = X-hosted file (not mirrored), duration_s, poster = local poster frame',
                       'prompt_source': 'post = post text, reply = author\'s own reply, alt = media ALT text'},
            'prompts': recs}
    (dest / 'video_prompts.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    cols = ['id', 'date', 'model', 'model_family', 'author', 'author_url', 'post_url', 'likes', 'language', 'prompt_source', 'prompt', 'mp4', 'duration_s']
    with open(dest / 'video_prompts.csv', 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for r in recs:
            w.writerow({**{c: r[c] for c in cols if c in r}, 'mp4': ' | '.join(v['mp4'] for v in r['videos']),
                        'duration_s': ' | '.join(str(v['duration_s']) for v in r['videos'])})


def export_videos(vd, vposts, vst, st):
    write_app('video', SITE_DIR, [vid_record(p) for p in vposts], vst, vst['count'], st['count'])
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
    prepare_media(posts, vposts)
    if vd:
        write_app('video', ROOT, [vid_record(p) for p in vposts], vst, VCOUNT, st['count'])
        write_video_downloads(ROOT, vd, vposts)
        print(f"videos.html + video_prompts.json/csv: {vst['count']} video posts {dict(vst['models'])}")
    write_app('image', ROOT, [img_record(p) for p in posts], st, VCOUNT, st['count'])
    write_downloads(ROOT, d, posts, st)
    print(f"index.html + prompts.json/csv: {st['count']} posts, {st['images']} images {dict(Counter(p.get('model') for p in posts))}")
    if not a.no_gallery:
        single = []
        for p in posts:
            p = json.loads(json.dumps(p))
            for im in p['images']:
                src, w, h = b64img(ROOT / 'images' / im['file'], EMBED_SIDE, EMBED_Q)
                im['thumb_src'] = im['full_src'] = src; im['tw'], im['th'] = w, h
            single.append(img_record(p))
        tmp = ROOT / '.gallery_build'; tmp.mkdir(exist_ok=True)
        html = write_app('image', tmp, single, st, VCOUNT, st['count'], inline=True)
        shutil.move(str(tmp / 'index.html'), str(ROOT / 'gallery.html')); shutil.rmtree(tmp, ignore_errors=True)
        print('gallery.html', round(len(html.encode()) / 1e6, 1), 'MB')
    if a.export or SITE_DIR.exists():
        export_site(d, posts, st)
        if vd: export_videos(vd, vposts, vst, st)
        if a.release_zip: release_zip(ROOT.parent / ZIP_NAME)


if __name__ == '__main__':
    main()
