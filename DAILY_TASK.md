# Daily task: build today's CLINT DAILY NEWS issue

You are producing one issue of **CLINT DAILY NEWS**, a Chinese–English bilingual
daily news web page. Work fully autonomously; nobody will answer questions.

## Point of view

Pick and write the news **as a born-and-raised, English-speaking Canadian
living in the Greater Toronto Area (GTA)** would read it each morning: the
stories that touch their own life. Think: cost of living (groceries, gas,
rent, housing, mortgages, interest rates, taxes), jobs and the economy,
Canada–US trade and tariffs, health care, schools, commuting (TTC, GO,
highways, Pearson airport), weather and storms, crime and public safety, city
hall and Queen's Park, Ottawa politics, the US news that spills over into
Canada, the markets and their savings, and the Toronto teams.

Leave out stories that only matter elsewhere. A big world event belongs only
if it clearly affects Canadians (trade, prices, travel, security, Canadians
involved) and then goes in the Canada or United States section, told from the
Canadian angle.

## 1. Work out today's date

Use Toronto time: `TZ=America/Toronto date +%F` gives `YYYY-MM-DD`.
If `data/YYYY-MM-DD.json` already exists for today, stop: today's issue is done.

## 2. Collect the news (web search)

Cover the last ~24–36 hours. **50 items in total**, in four sections:

| Section `id` | Title (zh / en) | Items | Notes |
|---|---|---|---|
| `gta` | 大多伦多地区 / GTA | 16 | Toronto, Peel (Mississauga, Brampton), York, Durham, Halton; Ontario government news that affects the GTA. Housing, transit, traffic, weather, crime, city budgets, schools, hospitals, local business, events. |
| `canada` | 加拿大 / Canada | 14 | Federal politics, Bank of Canada, economy and prices, jobs, trade and tariffs, national stories from other provinces. **Exclude** GTA local news (it has its own section). |
| `usa` | 美国 / United States | 12 | US politics and economy as they matter to Canadians. Must include one item on the previous US trading day's close (S&P 500, Dow, Nasdaq, biggest movers; mention the TSX if the source gives it). |
| `sports` | 体育 / Sports | 8 | Toronto teams first: Maple Leafs, Raptors, Blue Jays, Argonauts, Toronto FC. Then `NHL`, `NBA`, `NFL`, `MLB`, `CFL`, and Canadian athletes (e.g. tennis `ATP` / `WTA`). Big `EPL` / `UCL` results only when they're major news. Skip leagues out of season. |

If one section really runs dry after the top-up rounds, move the spare count to
another section so the issue still reaches 50.

### Sources

Use these outlets first, and mix them: within each section use at least 4
different outlets.

- **CBC News**, **CTV News**, **BBC News**, **Fox News**, **CNN**, **The New York Times**
- **Toronto local media**: Toronto Star, CP24, CityNews Toronto, Toronto Sun,
  Global News (Toronto), blogTO, Toronto Life, Globe and Mail (Toronto)
- Sports scores and recaps may also come from TSN, Sportsnet, ESPN or the
  league sites (NHL.com, NBA.com, MLB.com, CFL.ca).

Other outlets only when these have nothing on a story. For US political
stories, give both CNN and Fox News where possible.

### Network note (cloud environment)

`WebFetch` and `curl` to news sites are usually blocked (ENOTFOUND / proxy 403).
That is expected. Do **not** stop because of it. Build the issue from
`WebSearch` alone:
- Use `mode: "extended"`. Its answer summarizes the articles it found and lists
  their URLs; that summary, tied to a specific dated article URL in the result
  list, counts as confirmation.
- Don't use `allowed_domains` with reuters.com, apnews.com or thestar.com (the
  search API rejects them); search without a domain filter instead.
- Run searches in parallel batches (6+ per turn), using outlet names in the
  query (e.g. "CP24 Toronto news <date>", "CBC News Canada <date>",
  "CTV News Ontario <date>", "Fox News CNN <date>", "stock market close Dow
  S&P Nasdaq TSX <date>", "Maple Leafs game recap <date>").
- After the first pass, count items per section. For every section below its
  target, run another targeted batch (new angles: other outlets, other GTA
  cities, housing, transit, weather, courts, crime, health, business) and
  repeat up to 4 top-up rounds. Don't stop early. A story from the last 48
  hours is acceptable when the 24–36 hour window runs dry.
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
- No duplicates across sections.
- Plain, factual tone; no editorializing.

## 3. Write `data/YYYY-MM-DD.json`

Exact shape (sections in this order):

```json
{
  "date": "YYYY-MM-DD",
  "updated": {"zh": "更新于多伦多时间 M月D日 早上", "en": "Updated <Mon D>, morning (Toronto time)"},
  "sections": [
    {"id": "gta", "title": {"zh": "大多伦多地区", "en": "GTA"}, "items": [ ... ]},
    {"id": "canada", "title": {"zh": "加拿大", "en": "Canada"}, "items": [ ... ]},
    {"id": "usa", "title": {"zh": "美国", "en": "United States"}, "items": [ ... ]},
    {"id": "sports", "title": {"zh": "体育", "en": "Sports"}, "items": [ ... ]}
  ]
}
```

Each item:

```json
{
  "tags": ["politics"],
  "league": "NHL",
  "title":   {"zh": "…", "en": "…"},
  "summary": {"zh": "…", "en": "…"},
  "sources": [{"name": "CBC News", "url": "https://…"}, {"name": "CP24", "url": "https://…"}]
}
```

- `tags`: one or more of `politics`, `military`, `finance`, `sports`, `tech`,
  `breaking`, `nature`, `art`. US stock market items use `finance`.
- `league`: sports items only, one of `NHL`, `NBA`, `NFL`, `MLB`, `CFL`,
  `ATP`, `WTA`, `EPL`, `UCL`, `LaLiga`; sports items also carry the `sports` tag.
- `title`: one line, max ~30 Chinese characters / ~90 English characters.
- `summary`: a **brief** recap of the source story, **2–3 sentences**: about
  **40–70 English words** and **80–140 Chinese characters**. Lead with the key
  point (what happened, the key number), then one line on why it matters to
  the reader or what happens next. No background padding. For sports results
  give the score, the key performer and what it means (standings, series, next
  game).
  English: plain, natural news English, good for listening practice.
  Chinese: natural Simplified Chinese (not a word-for-word translation); use
  standard Chinese names for people/teams/places (e.g. 卡尼, 邹至蕙, 福特, 枫叶, 猛龙, 蓝鸟).

Then check it: `python check.py data/YYYY-MM-DD.json`. Fix every ERROR. For a
WARN about a short section, run more search batches (see the top-up rule
above). For a WARN about summary length, trim or expand it. Publish once errors
are fixed and you have done what you can on the warnings.

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

A GitHub Actions job (`.github/workflows/cbc.yml`) also pushes to `main` every
3 hours to refresh `docs/cbc.html` (极简CBC). Leave that file alone. If your
push is rejected because `main` moved, run `git pull --rebase origin main` and
push again.

## 5. Finish

End with a short report: date, item counts per section, number of distinct
outlets used, and any stories you dropped because they couldn't be verified.
