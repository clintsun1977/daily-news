# Daily task: SOX预测 (SOX Forecast)

Before the US market opens, make **one clear call** for today's move in the
**PHLX Semiconductor Index (SOX)**: up or down by a specific percentage,
close-to-close (today's 4 PM close vs. yesterday's close). Work fully
autonomously; nobody will answer questions.

The call is published on https://clintsun1977.github.io/daily-news/sox.html.
A GitHub Action records the SOXX pre-market move at the moment you publish
and fills in the actual result after the close, so publish **before the open**.

## 1. Date and deadline

```bash
TZ=America/New_York date '+%F %H:%M %a'
```

- Use that New York date as `YYYY-MM-DD`.
- Stop without publishing if: it's Saturday/Sunday; it's an NYSE holiday
  (2026: Nov 26, Dec 25 · 2027: Jan 1, Jan 18, Feb 15, Mar 26, May 31, Jun 18,
  Jul 5, Sep 6, Nov 25, Dec 24; for later years, search "NYSE holidays");
  `data/sox/YYYY-MM-DD.json` already exists.
- **Deadline: pushed by 9:25 AM New York time.** Check the clock again before
  writing the file. If it is 9:25 or later, stop: a call made after the open
  doesn't count. Budget your research to finish in time.

## 2. Research (WebSearch, `mode: "extended"`)

`WebFetch`/`curl` to news and finance sites are usually blocked in this
environment; that's expected. Work from WebSearch results. Run the searches in
parallel batches. Cover every factor that can move chip stocks today:

1. **Pre-market now**: SOXX / SMH pre-market, Nasdaq-100 and S&P 500 futures,
   pre-market moves of NVDA, AVGO, AMD, TSM, MU, ASML, INTC, QCOM, AMAT, LRCX,
   KLAC, ARM, MRVL.
2. **Yesterday's session**: SOX close and % change, what drove it, any
   after-hours moves (earnings, guidance).
3. **Overnight markets**: Taiwan (TSMC), Korea (Samsung, SK Hynix), Japan
   (Tokyo Electron, Advantest), Europe (ASML, Infineon, STMicro).
4. **Company news**: earnings before the open today / after the close
   yesterday, guidance, analyst up/downgrades, AI capex news from big cloud
   buyers (Microsoft, Alphabet, Amazon, Meta, OpenAI), large deals.
5. **Policy**: US export controls, China, tariffs, CHIPS Act, Taiwan
   tensions.
6. **Macro**: today's economic calendar (CPI, PPI, jobs, PCE, retail sales,
   Fed speakers or a Fed decision), 10-year Treasury yield, US dollar, VIX,
   oil.

Weigh them. The pre-market move is the strongest single signal, but adjust for
scheduled events later in the day, how big yesterday's move was (stretch /
mean reversion), and the SOX's typical daily range (it usually moves about
1.5–2.5x as much as the S&P 500).

## 3. Write `data/sox/YYYY-MM-DD.json`

Get the time stamp right before writing: `date -u +%FT%TZ`.

```json
{
  "date": "YYYY-MM-DD",
  "made_at": "YYYY-MM-DDTHH:MM:SSZ",
  "predict": -1.3,
  "summary": {
    "zh": "两三句话说明理由（中文，80–140 字）。",
    "en": "Two or three sentences on why (40–70 words)."
  },
  "factors": [
    {"dir": "down", "zh": "一句话因素", "en": "One-line factor"},
    {"dir": "up", "zh": "…", "en": "…"},
    {"dir": "mixed", "zh": "…", "en": "…"}
  ]
}
```

- `predict`: today's SOX % change, **one decimal, never 0** (e.g. `1.8` or
  `-0.7`). Make a clear call; no ranges, no hedging.
- `factors`: the 3–6 factors that mattered most, most important first, each
  with `dir` = `up`, `down` or `mixed` (its pull on today's move). Include
  the key numbers you found (e.g. "NVDA +2.1% pre-market after earnings").
- Never invent figures. Use only numbers that appear in your search results.
- Chinese: natural Simplified Chinese with standard names (英伟达, 台积电,
  美光, 阿斯麦, 博通, 美联储).

Check it: `python sox.py check data/sox/YYYY-MM-DD.json`; fix every ERROR.

## 4. Publish

```bash
git add data/sox/YYYY-MM-DD.json
git commit -m "sox predict: YYYY-MM-DD"
git push origin HEAD:main
```

Only add that one file. Don't run `python sox.py` without arguments, and don't
touch `docs/` or `data/sox-market.json`: the GitHub Action builds the page.
If the push is rejected because `main` moved, `git pull --rebase origin main`
and push again.

## 5. Finish

End with a short report: date, the call, the New York time you pushed, and
the three biggest factors.
