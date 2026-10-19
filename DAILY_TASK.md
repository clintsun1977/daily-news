# Daily task: build today's bilingual news digest

You are producing one issue of a Chinese–English bilingual daily news web page.
The reader lives in the Greater Toronto Area (GTA) and uses the page partly for
English listening practice. Work fully autonomously; nobody will answer questions.

## 1. Work out today's date

Use Toronto time: `TZ=America/Toronto date +%F` gives `YYYY-MM-DD`.
If `data/YYYY-MM-DD.json` already exists for today, stop: today's issue is done.

## 2. Collect the news (web search)

Cover the last ~24–36 hours. Topics: politics, business/finance, sports, tech,
breaking events (disasters, crime, accidents), entertainment and celebrity gossip.

| Section `id` | Count | Notes |
|---|---|---|
| `china` | 3–5 | Mainland China, Hong Kong, China's foreign relations |
| `canada` | 5–10 | Two groups: **Greater Toronto Area** (about half: Toronto, Peel/Mississauga/Brampton, York, Durham, Halton, Ontario provincial politics affecting the GTA) and **National** |
| `world` | 5–10 | Global politics, markets, conflicts, tech, major disasters |
| `sports` | 6–10 | Latest results and big storylines. Priority: Champions League (`UCL`), Premier League (`EPL`), LaLiga (`LaLiga`), tennis (`ATP` / `WTA`), `NBA`, `NFL`, `NHL`, `MLB`. Mention Toronto teams (Maple Leafs, Raptors, Blue Jays) and Canadian players when relevant. Skip leagues that are out of season. |
| `entertainment` | 2–6 | Two groups, each 1–3 items: **Entertainment 娱乐圈** (films/box office, music, TV, awards, concerts, industry news; tag `entertainment`) and **Gossip 八卦** (celebrity relationships, sightings, feuds, viral moments; tag `gossip`). Mix Chinese-language (mainland/HK/Taiwan) and Western stars. |

**Network note:** in the cloud environment `WebFetch` and `curl` to news sites
are usually blocked (ENOTFOUND / proxy 403). That is expected. Do **not** stop
because of it. Build the whole issue from `WebSearch` alone:
- Use `mode: "extended"`. Its answer summarizes the articles it found and lists
  their URLs; that summary, tied to a specific dated article URL in the result
  list, counts as confirmation.
- Don't use `allowed_domains` with reuters.com, apnews.com or thestar.com (the
  search API rejects them); search without a domain filter instead.
- Run searches in parallel batches (several per turn) to keep the run short.
- Publishing a smaller issue is far better than publishing nothing. Only skip
  publishing if you have fewer than 10 confirmed items in total.

Rules:
- Every item needs at least one source URL that is an actual article (not a
  homepage or section page) dated within the window. Prefer CBC, CTV, CP24,
  Global News, CityNews, Globe and Mail, BBC, Bloomberg, ESPN, NHL.com,
  MLB.com, NBA.com, NFL.com, ATP/WTA, UEFA, South China Morning Post, Xinhua.
- Never invent facts, scores or quotes. If two results disagree on a fact or
  score, drop that detail (or the item) rather than guess. Sports scores must
  come from a result that names the final score (match report, recap or
  scoreboard marked final).
- Search for scores of games that already finished; don't report games in progress as results.
- Avoid duplicates across sections.
- Gossip: only public figures, only from established entertainment outlets
  (Variety, Deadline, People, E! News, BBC, CTV, Sina 新浪娱乐, Tencent 腾讯娱乐,
  HK01, etc.). Report rumours only together with the response or denial, and say
  plainly when something is unconfirmed (e.g. a fan sighting). No stories about
  minors, private individuals, health or sexuality speculation, or anything
  defamatory.

## 3. Write `data/YYYY-MM-DD.json`

Copy the structure of the newest existing file in `data/` exactly. Per item:

```json
{
  "tags": ["politics"],            // any of: politics, finance, sports, tech, breaking, entertainment, gossip
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
- Canada uses `"groups"` (GTA first, then National) and so does `entertainment`
  (Entertainment 娱乐圈 first, then Gossip 八卦); other sections use `"items"`.
  Section order: china, canada, world, sports, entertainment.

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

End with a short report: date, item counts per section (GTA vs National,
Entertainment vs Gossip), and
any stories you dropped because they couldn't be verified.
