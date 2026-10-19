# Daily task: build today's CLINT DAILY NEWS issue

You are producing one issue of **CLINT DAILY NEWS**, a Chinese–English bilingual
daily news web page. The reader lives in the Greater Toronto Area (GTA) and uses
the page partly for English listening practice. Work fully autonomously; nobody
will answer questions.

## 1. Work out today's date

Use Toronto time: `TZ=America/Toronto date +%F` gives `YYYY-MM-DD`.
If `data/YYYY-MM-DD.json` already exists for today, stop: today's issue is done.

## 2. Collect the news (web search)

Cover the last ~24–36 hours. Pick the **major** stories, weighted toward:
politics, military/defence, business and finance, **US stock market**, sports,
science and tech, nature (climate, weather, environment, wildlife, space), arts
and culture, entertainment, and breaking news (disasters, crime, accidents).

| Section `id` | Title (zh / en) | Items | Notes |
|---|---|---|---|
| `canada` | 加拿大 / Canada | 10 | National and other provinces. **Exclude** GTA local news (it has its own section). |
| `gta` | 大多伦多 / Greater Toronto | 10 | Toronto, Peel (Mississauga, Brampton), York, Durham, Halton, and Ontario government news that affects the GTA. |
| `usa` | 美国 / United States | 10 | Must include one item on the previous US trading day's close (S&P 500, Dow, Nasdaq, biggest movers). |
| `europe` | 欧洲 / Europe | 10 | UK, EU and European countries, Russia–Ukraine war. |
| `asia` | 亚洲 / Asia | 10 | Asia-Pacific and Middle East **excluding China** (Japan, Koreas, India, Southeast Asia, Taiwan, Australia, Middle East...). |
| `china` | 中国 / China | 10 | Mainland China and Hong Kong, China's foreign relations and economy. |
| `sports` | 体育 / Sports | 6–10 | Results and big storylines: Champions League (`UCL`), Premier League (`EPL`), LaLiga (`LaLiga`), tennis (`ATP` / `WTA`), `NBA`, `NFL`, `NHL`, `MLB`. Mention Toronto teams (Maple Leafs, Raptors, Blue Jays) and Canadian players when relevant. Skip leagues out of season. |
| `entertainment` | 娱乐 / Entertainment | 2–6 | Two groups, each 1–3 items: **Entertainment 娱乐圈** (films, box office, music, TV, awards; tag `entertainment`) and **Gossip 八卦** (celebrity relationships, sightings, feuds, viral moments; tag `gossip`). Mix Chinese-language (mainland/HK/Taiwan) and Western stars. |

### Sources: authoritative and varied

Use major, authoritative outlets, and **mix countries and viewpoints**. Within
each section use at least 4 different outlets, and give big stories two
sources from different countries where possible (e.g. a Chinese and a Western
outlet on a China–US story; CNN and Fox News on a US political story).

- Canada: CBC, CTV, Global News, CP24, CityNews, Globe and Mail, National Post
- USA: CNN, Fox News, New York Times, Washington Post, NPR, NBC, CBS, ABC, CNBC, Bloomberg, WSJ, Politico
- Europe: BBC, Guardian, Sky News, DW, France 24, Le Monde, Euronews
- Asia: Lianhe Zaobao 联合早报, Straits Times, CNA, NHK, Kyodo, Japan Times, Yonhap, Korea Herald, Times of India, Hindustan Times, Al Jazeera, ABC Australia
- China: Xinhua 新华社, CGTN, People's Daily, China Daily, Global Times, Caixin, SCMP, RTHK, Lianhe Zaobao
- Sports: ESPN, BBC Sport, Sky Sports, TSN, Sportsnet, NHL.com, NBA.com, NFL.com, MLB.com, ATP/WTA, UEFA
- Entertainment: Variety, Deadline, Hollywood Reporter, People, E! News, 新浪娱乐, 腾讯娱乐, HK01

### Network note (cloud environment)

`WebFetch` and `curl` to news sites are usually blocked (ENOTFOUND / proxy 403).
That is expected. Do **not** stop because of it. Build the issue from
`WebSearch` alone:
- Use `mode: "extended"`. Its answer summarizes the articles it found and lists
  their URLs; that summary, tied to a specific dated article URL in the result
  list, counts as confirmation.
- Don't use `allowed_domains` with reuters.com, apnews.com or thestar.com (the
  search API rejects them); search without a domain filter instead.
- Run searches in parallel batches (6+ per turn). A good plan: one batch per
  section, using outlet names in the query (e.g. "BBC Europe news <date>",
  "联合早报 亚洲 <date>", "Xinhua China <date>", "Fox News CNN <date>",
  "stock market close Dow S&P Nasdaq <date>").
- After the first pass, count items per section. For any section below its
  target, run another targeted batch before writing the file.
- Publishing a smaller issue is far better than publishing nothing. Only skip
  publishing if you have fewer than 20 confirmed items in total.

### Rules

- Every item needs at least one source URL that is an actual article (not a
  homepage or section page) dated within the window.
- Never invent facts, scores, figures or quotes. If two results disagree on a
  fact or score, drop that detail (or the item) rather than guess. Sports
  scores must come from a result that names the final score (match report,
  recap, or box score marked final), and the source URL should be that game's
  own page, not a scoreboard index.
- Don't report games in progress as results.
- Avoid duplicates across sections (a China–US story goes in one section only).
- Gossip: only public figures, only from established entertainment outlets.
  Report rumours only together with the response or denial, and say plainly
  when something is unconfirmed (e.g. a fan sighting). No stories about
  minors, private individuals, health or sexuality speculation, or anything
  defamatory.

## 3. Write `data/YYYY-MM-DD.json`

Exact shape (sections in this order):

```json
{
  "date": "YYYY-MM-DD",
  "updated": {"zh": "更新于多伦多时间 M月D日 早上", "en": "Updated <Mon D>, morning (Toronto time)"},
  "sections": [
    {"id": "canada", "title": {"zh": "加拿大", "en": "Canada"}, "items": [ ... ]},
    {"id": "gta", "title": {"zh": "大多伦多", "en": "Greater Toronto"}, "items": [ ... ]},
    {"id": "usa", "title": {"zh": "美国", "en": "United States"}, "items": [ ... ]},
    {"id": "europe", "title": {"zh": "欧洲", "en": "Europe"}, "items": [ ... ]},
    {"id": "asia", "title": {"zh": "亚洲", "en": "Asia"}, "items": [ ... ]},
    {"id": "china", "title": {"zh": "中国", "en": "China"}, "items": [ ... ]},
    {"id": "sports", "title": {"zh": "体育", "en": "Sports"}, "items": [ ... ]},
    {"id": "entertainment", "title": {"zh": "娱乐", "en": "Entertainment"}, "groups": [
      {"title": {"zh": "娱乐圈", "en": "Entertainment"}, "items": [ ... ]},
      {"title": {"zh": "八卦", "en": "Gossip"}, "items": [ ... ]}
    ]}
  ]
}
```

Each item:

```json
{
  "tags": ["politics"],
  "league": "EPL",
  "title":   {"zh": "…", "en": "…"},
  "summary": {"zh": "…", "en": "…"},
  "sources": [{"name": "CBC News", "url": "https://…"}, {"name": "Xinhua", "url": "https://…"}]
}
```

- `tags`: one or more of `politics`, `military`, `finance`, `sports`, `tech`,
  `breaking`, `nature`, `art`, `entertainment`, `gossip`. US stock market items
  use `finance`.
- `league`: sports items only (codes above); sports items also carry the `sports` tag.
- `title`: one line, max ~30 Chinese characters / ~90 English characters.
- `summary`: 2–4 sentences with the key facts (who, what, where, numbers).
  English: plain, natural news English, good for listening practice.
  Chinese: natural Simplified Chinese (not a word-for-word translation); use
  standard Chinese names for people/teams/places (e.g. 卡尼, 邹至蕙, 枫叶, 猛龙).

Then check it: `python check.py data/YYYY-MM-DD.json`. Fix every ERROR. For a
WARN about a short section, run one more search batch for that section if you
can; otherwise publish anyway.

## 4. Build and publish

```bash
python build.py
git add data docs
git commit -m "news: YYYY-MM-DD"
git push origin HEAD:main
```

`build.py` writes `docs/YYYY-MM-DD.html` and `docs/index.html`; GitHub Pages
serves `docs/` from the `main` branch, so pushing to `main` publishes the issue.
Don't change `build.py`, `check.py` or old data files.

## 5. Finish

End with a short report: date, item counts per section, number of distinct
outlets used, and any stories you dropped because they couldn't be verified.
