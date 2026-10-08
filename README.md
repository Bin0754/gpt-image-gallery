# GPT Image 2.5 提示词图库

从 X（Twitter）公开帖子中收集的 **GPT Image 2.5**（OpenAI，2026-09-08 发布，API 型号 `gpt-image-2.5-flare` / `gpt-image-2.5-sunburst`）生成图片 + 完整提示词。

在线浏览：**https://bin0754.github.io/gpt-image-gallery/**（GitHub Pages，手机/电脑均可）

## 文件
- `index.html` — 完整站点（引用 `images/` 和 `thumbs/`），可用 `python3 -m http.server 8080` 打开，也可直接双击
- `gallery.html` — 单文件版（图片以 base64 内嵌），双击即可打开
- `data.json` — 结构化数据（帖子、作者、北京时间、点赞、提示词、提示词来源、图片）
- `images/` 最长边 1200px JPEG；`thumbs/` 最长边 480px
- `raw/` — X API 原始返回（MCP 调用结果，仅本地保留，不发布）
- `site/` — 由 `build_site.py` 生成的发布目录（本身是 git 仓库 `Bin0754/gpt-image-gallery`，GitHub Pages 从 main 分支根目录发布）；只包含 `index.html`、`data.json`、显示中的图片/缩略图、图标、README 和 `scripts/`（脚本副本，需在项目根目录运行）
- `publish.sh` — 把 `site/` 提交并推送到 GitHub（`gh` 需已登录）

## 刷新数据
X 数据是通过 `x` MCP 工具（X API v2 `search_posts_all` / `get_posts_by_ids`）拉取的，脚本本身不直接调用 X：
1. 让助手用 `x` MCP 重新搜索（查询见 `data.json` 的 `queries`），参数：
   `expansions=attachments.media_keys,author_id,referenced_tweets.id`，
   `media.fields=url,width,height,alt_text,type`，`post.fields=created_at,public_metrics,note_tweet,conversation_id,referenced_tweets,attachments,in_reply_to_user_id`，
   把每次返回的 JSON 存成 `raw/*.txt`（第一行为 JSON）。
2. 对“Prompt below / 提示词在评论”的帖子，用 `(from:作者 (conversation_id:ID ...)) is:reply -has:mentions` 拉作者自回复，再用 `get_posts_by_ids` 补全长文（note_tweet）。
3. `python3 scrape.py`（解析 + 去重 + 下载/压缩图片 → data.json）
4. `python3 build_site.py`（生成 index.html、gallery.html、site/、../gpt-image-gallery.zip）
5. `./publish.sh`（提交并推送 site/ 到 GitHub，约 1 分钟后线上页面更新；无变化时不会提交）

每日刷新例程：`python3 scrape.py && python3 build_site.py && ./publish.sh`

提示词提取规则见 `extract.py`：优先帖子正文中 `Prompt:` / `提示词：` / `プロンプト：` 之后的文字；否则用图片 ALT 文本；否则用作者在同一会话里的自回复。默认过滤掉含明显 NSFW 关键词的帖子（`build_site.py` 中 `INCLUDE_NSFW`），另有人工隐藏列表 `HIDE_IDS`（关键词没拦住但画面过于性感的帖子）。
gallery.html、zip、raw/ 不会发布到 GitHub。所有图片与提示词版权归原作者，页面仅作索引并链接原帖。
