# CLINT DAILY NEWS 每日新闻

## 结构
- `data/YYYY-MM-DD.json` — 当天新闻数据（中英双语：标题、摘要、标签、来源链接）
- `build.py` — 把所有 JSON 生成网页
- `docs/YYYY-MM-DD.html` — 每日网页（GitHub Pages 发布 docs/）
- `docs/index.html` — 网站首页，即极简CBC（由 `cbc.py` 生成，与 `docs/cbc.html` 相同）
- `DAILY_TASK.md` — 云端每日任务的完整说明
- `cbc.py` — 生成网站首页「极简CBC」（`docs/index.html`，`docs/cbc.html` 为同一页面），页首沿用 CLINT DAILY NEWS 的排版和照片，底部是大鹅硬刚老鹰的照片。共 200 条新闻标题，专栏分两排：第一排 头条、加拿大、多伦多、伯灵顿·奥克维尔、国际；第二排 政治、财经、科技、健康、文艺、体育。伯灵顿·奥克维尔栏目（15 条）取自 Google 新闻搜索到的当地媒体（Inside Halton、BurlingtonToday、Oakville News、CHCH 等）、inSauga 和 CBC 里提到该地区的标题，两城轮流入选，过滤讣告和美国同名城镇；其余来自 CBC（汉密尔顿并入多伦多，冰球和足球并入体育，其他城市并入加拿大以补足条数）。点右侧按钮打开原文；可切换双语/中文/EN（中文标题为 Google 机器翻译，缓存在 `data/cbc-zh.json`）。由 GitHub Actions（`.github/workflows/cbc.yml`）每 3 小时自动运行并推送，不消耗 Claude 用量；页面最下方（大鹅照片下）有 .SOX 按钮通往 SOX预测

## 每日流程
1. 搜集新闻，按 `DAILY_TASK.md` 第 3 节的格式新建当天文件
2. 运行 `python build.py`
3. 打开 `docs/YYYY-MM-DD.html`

## 收录规则（详见 DAILY_TASK.md）
- 视角：一名土生土长、讲英语的大多伦多本地加拿大人，每天看与自己生活息息相关的新闻（物价、房子、利率、交通、天气、治安、政府、美加关系、股市、本地球队）
- 每天 50 条：大多伦多 16、加拿大（不含大多）14、美国 12、体育 8
- 来源：CBC、CTV、BBC、Fox、CNN、纽约时报，以及多伦多本地媒体（Toronto Star、CP24、CityNews、Toronto Sun、Global News、blogTO 等）
- 摘要简短：2–3 句，约 40–70 个英文词 / 80–140 个汉字，先说重点
- 标签：politics 政治 · military 军事 · finance 财经 · sports 体育 · tech 科技 · breaking 突发 · nature 自然 · art 艺术
- 发布前运行 `python check.py data/YYYY-MM-DD.json` 检查格式和条数

## 页面用法
- 新闻默认是标题列表，点标题展开摘要和来源；可一键全部展开/收起
- 标题右侧 🔊 按钮朗读该条（标题+摘要），再点停止；按顶部语言模式读中文、英文，或双语模式下先英后中
- league 字段可用：NHL / NBA / NFL / MLB / CFL / ATP / WTA / EPL / UCL / LaLiga

## 固定网址与自动更新
- 固定网址（不用登录，手机电脑都能打开）：https://clintsun1977.github.io/daily-news/
- 每天早上 7 点（多伦多夏令时；冬令时为 6 点，即 UTC 11:00）由云端定时任务按 `DAILY_TASK.md` 自动收集、生成并推送到 GitHub
- 定时任务管理：https://claude.ai/code/routines/trig_018YgwWVtvR824xkyFqr7pJJ
- 旧的 claude.ai 私人链接（需手动更新）：https://claude.ai/artifact/2c2BqBMk6rgXGhDsm6dPXA
