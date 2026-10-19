# CLINT DAILY NEWS 每日新闻

## 结构
- `data/YYYY-MM-DD.json` — 当天新闻数据（中英双语：标题、摘要、标签、来源链接）
- `build.py` — 把所有 JSON 生成网页
- `docs/YYYY-MM-DD.html` — 每日网页；`docs/index.html` 永远是最新一天（GitHub Pages 发布 docs/）
- `DAILY_TASK.md` — 云端每日任务的完整说明

## 每日流程
1. 搜集新闻，按 `data/2026-10-18.json` 的格式新建当天文件
2. 运行 `python build.py`
3. 打开 `docs/index.html`

## 收录规则（详见 DAILY_TASK.md）
- 加拿大（不含大多）10、大多伦多 10、美国 10、欧洲 10、亚洲（不含中国）10、中国 10；体育 6–10；娱乐圈和八卦各 1–3
- 来源：CBC、Fox、CNN、新华社、BBC、纽约时报、联合早报等权威媒体，尽量不同国家、不同角度
- 侧重：政治、军事、财经、美股、体育、科技、自然、艺术、娱乐、突发
- 标签：politics 政治 · military 军事 · finance 财经 · sports 体育 · tech 科技 · breaking 突发 · nature 自然 · art 艺术 · entertainment 娱乐圈 · gossip 八卦
- 发布前运行 `python check.py data/YYYY-MM-DD.json` 检查格式和条数

## 页面用法
- 新闻默认是标题列表，点标题展开摘要和来源；可一键全部展开/收起
- 标题右侧 🔊 按钮朗读该条（标题+摘要），再点停止；按顶部语言模式读中文、英文，或双语模式下先英后中
- league 字段可用：EPL / LaLiga / UCL / ATP / WTA / NBA / NFL / NHL / MLB

## 固定网址与自动更新
- 固定网址（不用登录，手机电脑都能打开）：https://clintsun1977.github.io/daily-news/
- 每天早上 7 点（多伦多夏令时；冬令时为 6 点，即 UTC 11:00）由云端定时任务按 `DAILY_TASK.md` 自动收集、生成并推送到 GitHub
- 定时任务管理：https://claude.ai/code/routines/trig_018YgwWVtvR824xkyFqr7pJJ
- 旧的 claude.ai 私人链接（需手动更新）：https://claude.ai/artifact/2c2BqBMk6rgXGhDsm6dPXA
