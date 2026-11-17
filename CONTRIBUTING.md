# 参与贡献

感谢你帮忙让这个图库更好！以下几种方式都很欢迎：

## 推荐提示词
在 [Issues](https://github.com/Bin0754/gpt-image-gallery/issues/new?template=submit-prompt.yml) 选择 **「推荐提示词」** 模板，填写：
- X 原帖链接（必须是公开帖子，并明确使用 GPT Image 2.5 生成）；
- 提示词的位置（正文 / 作者回复 / 图片 ALT）——**作者本人公开给出的提示词**才会收录，我们不会根据图片“猜”提示词。

维护者会在下次数据更新时加入。

## 报告问题
提示词截取不完整、混入了广告语、语言分类错误、图片打不开、页面在某些设备上显示异常……都可以直接开 Issue，最好附上帖子链接或截图。

## 移除内容
如果你是作者并希望移除自己的作品，请使用 **「移除请求」** 模板（[直接打开](https://github.com/Bin0754/gpt-image-gallery/issues/new?template=removal-request.yml)）。我们会优先处理。

## 提交代码（PR）
1. Fork 并创建分支；
2. 页面改动在 `scripts/template.html`，数据处理在 `scripts/extract.py` / `scripts/scrape.py` / `scripts/build_site.py`；
3. 本地运行 `python3 scripts/build_site.py --no-gallery && python3 -m http.server 8080` 检查效果（请同时看一下 390px 宽的手机布局）；
4. 提交 PR 并简单说明改动。

请勿在 PR 中提交任何 API Token 或个人凭据（`raw/` 与 `.env` 已在 `.gitignore` 中）。代码贡献将按 MIT 协议发布。
