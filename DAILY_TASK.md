# Daily task: build today's bilingual news digest

You are producing one issue of a Chinese–English bilingual daily news web page.
The reader lives in the Greater Toronto Area (GTA) and uses the page partly for
English listening practice. Work fully autonomously; nobody will answer questions.

## 1. Work out today's date

Use Toronto time: `TZ=America/Toronto date +%F` gives `YYYY-MM-DD`.
If `data/YYYY-MM-DD.json` already exists for today, stop: today's issue is done.

## 2. Collect the news (web search)

Cover the last ~24–36 hours. Topics: politics, business/finance, sports, tech,
and breaking events (disasters, crime, accidents).

| Section `id` | Count | Notes |
|---|---|---|
| `china` | 3–5 | Mainland China, Hong Kong, China's foreign relations |
| `canada` | 5–10 | Two groups: **Greater Toronto Area** (about half: Toronto, Peel/Mississauga/Brampton, York, Durham, Halton, Ontario provincial politics affecting the GTA) and **National** |
| `world` | 5–10 | Global politics, markets, conflicts, tech, major disasters |
| `sports` | 6–10 | Latest results and big storylines. Priority: Champions League (`UCL`), Premier League (`EPL`), LaLiga (`LaLiga`), tennis (`ATP` / `WTA`), `NBA`, `NFL`, `NHL`, `MLB`. Mention Toronto teams (Maple Leafs, Raptors, Blue Jays) and Canadian players when relevant. Skip leagues that are out of season. |

Rules:
- Every item needs at least one source URL that is an actual article (not a
  homepage) dated within the window. Prefer CBC, CTV, CP24, Global News,
  Toronto Star, Globe and Mail, Reuters, AP, BBC, Bloomberg, ESPN, NHL.com,
  MLB.com, NBA.com, NFL.com, ATP/WTA, UEFA, South China Morning Post, Xinhua.
- Never invent facts, scores or quotes. If search snippets conflict or a story
  can't be confirmed from a real article, drop it. Sports scores must come from
  a box score or match report.
- Search for scores of games that already finished; don't report games in progress as results.
- Avoid duplicates across sections.

## 3. Write `data/YYYY-MM-DD.json`

Copy the structure of the newest existing file in `data/` exactly. Per item:

```json
{
  "tags": ["politics"],            // any of: politics, finance, sports, tech, breaking
  "league": "EPL",                 // sports items only (codes above)
  "title":   { "zh": "…", "en": "…" },
  "summary": { "zh": "…", "en": "…" },
  "sources": [ { "name": "CBC News", "url": "https://…" } ]
}
```

- `title`: one line, max ~30 Chinese characters / ~90 English characters.
- `summary`: 2–4 sentences with the key facts (who, what, where, numbers).
  English: plain, natural news English, good for listening practice.
  Chinese: natural Simplified Chinese (not a word-for-word translation); use
  standard Chinese names for people/teams/places (e.g. 卡尼, 邹至蕙, 枫叶, 猛龙).
- Sports items always include the `sports` tag plus a `league` code.
- `updated`: `{"zh": "更新于多伦多时间 M月D日 早上", "en": "Updated <Mon D>, morning (Toronto time)"}`.
- Canada uses `"groups"` (GTA first, then National); other sections use `"items"`.

Validate: `python -c "import json,sys; json.load(open(sys.argv[1], encoding='utf-8'))" data/YYYY-MM-DD.json`

## 4. Build and publish

```bash
python build.py
git add data docs
git commit -m "news: YYYY-MM-DD"
git push origin HEAD:main
```

`build.py` writes `docs/YYYY-MM-DD.html` and `docs/index.html`; GitHub Pages
serves `docs/` from the `main` branch, so pushing to `main` publishes the issue.
Don't change `build.py` or old data files.

## 5. Finish

End with a short report: date, item counts per section (GTA vs National), and
any stories you dropped because they couldn't be verified.
