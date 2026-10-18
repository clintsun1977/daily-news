# 每日新闻收集器 Daily News Digest

## 结构
- `data/YYYY-MM-DD.json` — 当天新闻数据（中英双语：标题、摘要、标签、来源链接）
- `build.py` — 把所有 JSON 生成网页
- `docs/YYYY-MM-DD.html` — 每日网页；`docs/index.html` 永远是最新一天（GitHub Pages 发布 docs/）
- `DAILY_TASK.md` — 云端每日任务的完整说明

## 每日流程
1. 搜集新闻，按 `data/2026-10-18.json` 的格式新建当天文件
2. 运行 `python build.py`
3. 打开 `docs/index.html`

## 收录规则
- 中国 3–5 条；加拿大 5–10 条（大多伦多约占一半）；国际 5–10 条
- 体育单独成栏，重点：欧冠、英超、西甲、网球（ATP/WTA）、NBA、NFL、NHL、MLB
- 标签：`politics` 政治 · `finance` 财经 · `sports` 体育 · `tech` 科技 · `breaking` 突发

## 页面用法
- 新闻默认是标题列表，点标题展开摘要和来源；可一键全部展开/收起
- 标题右侧 🔊 按钮朗读该条（标题+摘要），再点停止；按顶部语言模式读中文、英文，或双语模式下先英后中
- league 字段可用：EPL / LaLiga / UCL / ATP / WTA / NBA / NFL / NHL / MLB

## 手机查看
- 链接：https://claude.ai/artifact/2c2BqBMk6rgXGhDsm6dPXA （登录自己的 Claude 账号后打开）
- 每天 `python build.py` 会同时生成 `build/artifact.html`，把它重新发布到同一链接即可更新
