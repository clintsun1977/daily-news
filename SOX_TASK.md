# Daily task: SOX预测 (SOX Forecast)

Before the US market opens, make **one clear call** for today's move in the
**PHLX Semiconductor Index (SOX)**: up or down by a specific percentage,
close-to-close (today's 4 PM close vs. yesterday's close). Work fully
autonomously; nobody will answer questions.

The goal is accuracy, measured honestly: your average error must beat the
naive baseline "forecast = SOXX pre-market move", and your trade side (see
step 5) must be right more often than not. Be disciplined, not dramatic.

The call is published on https://clintsun1977.github.io/daily-news/sox.html.
A GitHub Action records the SOXX pre-market move at the moment you publish,
places the paper trade, and fills in the actual result after the close.

## 1. Date, deadline, latest data

```bash
git pull --rebase origin main
TZ=America/New_York date '+%F %H:%M %a'
```

- Use that New York date as `YYYY-MM-DD`.
- Stop without publishing if: it's Saturday/Sunday; it's an NYSE holiday
  (2026: Nov 26, Dec 25 · 2027: Jan 1, Jan 18, Feb 15, Mar 26, May 31, Jun 18,
  Jul 5, Sep 6, Nov 25, Dec 24; for later years, search "NYSE holidays");
  `data/sox/YYYY-MM-DD.json` already exists.
- **Deadline: pushed by 9:25 AM New York time.** Check the clock again before
  writing the file. If it is 9:25 or later, stop: a call made after the open
  doesn't count. Budget your time: about 25 minutes in total.

## 2. Learn from the record (5 minutes)

Read `data/sox-lessons.md` (standing rules + daily log) and section 5 of
today's brief (`data/sox-brief/YYYY-MM-DD.md`, the forecast track record).

For each scored forecast that has no log entry yet (normally just the last
trading day), search for what actually drove that session ("semiconductor
stocks <date> close", "SOX index <date>") and append a log entry:

```
### YYYY-MM-DD · forecast +0.6 / pre-market +0.13 / actual -1.2 / trade side wrong
- What drove the day: …
- What I missed or misjudged: …
- Lesson: … (one concrete, testable sentence)
```

Then revise the **Standing rules** at the top of that file when the log shows
a pattern across several days (a recurring bias, a factor that keeps
mattering, a rule that keeps failing). Keep at most 15 rules, each one line,
and the log to the latest 40 entries. Apply the rules today.

## 3. Read today's brief

`data/sox-brief/YYYY-MM-DD.md` is written by GitHub Actions at about 7:50 and
8:20 AM New York time (EDT; an hour earlier in EST) from Yahoo Finance. It has:

1. Live quotes with timestamps: SOXX/SMH and SOXL/SOXS pre-market, the 19
   largest SOX members, AI buyers (MSFT, GOOGL, AMZN, META, ORCL), index
   futures, Asia (TSMC, SK Hynix, Samsung, Tokyo Electron, Advantest), Europe
   (ASML, BESI, Infineon, STMicro), 10-year yield, dollar, yen, oil, gold,
   VIX, bitcoin.
2. Where SOX stands: recent returns, realized volatility, distance from the
   20/50/200-day averages, RSI(14), drawdown from the high.
3. Base rates from 5 years of SOX: what the session after the open did,
   given the size of the opening gap and the previous day's move.
4. A statistical model (`sox_model.py`, ridge regression on 10 years) of the
   move after the open, its year-by-year out-of-sample record, and today's
   value. Its record is weak (about as good as assuming no move after the
   open), so it is an objective anchor, not a signal.
5. The track record: your forecasts, the model's and the baseline's errors.

If today's brief is missing (the Action was late), use the latest one for
the base rates and get live quotes from search instead. These numbers are
facts; prefer them over numbers quoted in news articles.

## 4. Search for catalysts (WebSearch, `mode: "extended"`)

`WebFetch`/`curl` to news and finance sites are usually blocked here; that's
expected. Run the searches in parallel batches. Look for what the numbers
don't show yet:

- **Overnight and pre-market news**: why chips are moving this morning;
  earnings before the open today or after yesterday's close (SOX members,
  their big customers, equipment makers); guidance; analyst calls.
- **Scheduled events today and when**: US data (8:30 / 10:00 AM), Fed
  speakers or an FOMC decision (2 PM), Treasury auctions, big earnings after
  today's close (positioning ahead of them), monthly options expiry (third
  Friday; quarterly ones are bigger), index rebalances, month/quarter end.
- **Industry data**: TSMC monthly sales (around the 10th), Korean chip
  exports (1st and 21st), SIA sales, memory pricing (DRAM/NAND), AI capex
  updates.
- **Policy and geopolitics**: export controls, China, tariffs, Taiwan,
  Middle East / oil, US politics.
- **Positioning and sentiment**: after a big move, is it capitulation,
  short covering, or a trend change? Weekend risk on Fridays.
- **What others are saying** (shown on the page as "各方观点"): views on
  chip stocks / the SOX for today or the next few days from well-known
  outlets and named commentators: CNBC, Bloomberg, Reuters, WSJ, Barron's,
  MarketWatch, Yahoo Finance, Financial Times, Investor's Business Daily;
  sell-side semiconductor analysts and strategists (e.g. Bernstein, Morgan
  Stanley, BofA, Goldman, JPMorgan, Wedbush, Strategas, Fundstrat). Search
  e.g. "semiconductor stocks analyst outlook <date>", "chip stocks
  strategist <date>", "<analyst name> semiconductors". Collect 3–6 views
  with a mix of stances where they exist. Weigh them in your forecast, but
  don't follow the crowd blindly.

Never invent figures. Use only numbers that appear in the brief or in your
search results.

## 5. Build the forecast in two parts

**Forecast = expected opening gap + expected move after the open.**

1. **Gap (`gap_est`)**: start from the latest SOXX pre-market move in the
   brief. Adjust only for news after the brief's timestamp (e.g. futures or
   Europe moving since, a pre-market headline). SOX and SOXX move almost
   one-for-one.
2. **After the open (`drift_est`)**: the base rates say this averages about
   zero; only move it with evidence, and weigh each factor:
   - base rates for today's gap size and yesterday's move (continuation or
     fade?);
   - stretched technicals (RSI under 25 or over 75, far from the averages)
     favour a partial reversal; trends favour continuation;
   - pre-market breadth: are leaders (NVDA, AVGO, TSM, MU, equipment) moving
     together, or is one stock driving SOXX?
   - Europe's semis have traded for hours with today's news: a big gap
     between them and US pre-market is a signal;
   - scheduled catalysts during the session and their likely direction;
   - futures, yields, dollar and VIX direction this morning;
   - your standing rules;
   - the statistical model's after-open value (brief section 4): start your
     thinking from it, and if you end up far from it (more than about 0.5
     points), know why. The page scores your forecast against the model's,
     so you have to add something it can't see (news, Europe, catalysts).
   Keep `drift_est` within ±1.5 unless there is a strong scheduled catalyst.
3. **Sanity checks**: the SOX's daily standard deviation is in the brief
   (about 2–2.5%); a forecast beyond ±2x that needs an exceptional reason.
   Write one line on what would prove you wrong.

`predict` = `gap_est` + `drift_est`, rounded to one decimal, **never 0**.

**The trade side**: the paper trade buys SOXL at the open if `predict` is
above the SOXX pre-market move at the moment you publish, SOXS otherwise. So
the sign of `drift_est` is your bet on the session after the open. Make it
deliberately, never by rounding. If the pre-market move is between your gap
estimate and your forecast, re-check.

**The size and confidence matter too**: eight paper-trading rules are
scored side by side (see the page). Among them: rule B sells once the SOX's
move on the day reaches twice `predict` either way, so an inflated forecast
puts its exits out of reach and a timid one gets it stopped out by noise;
rule 2 sizes the position by `confidence` (high 100%, medium 50%, low 25%);
rule 3 trades only when `predict` differs from the pre-market move by at
least 0.5 points. So give your honest best estimate of the size, and use
`high` only when the evidence really lines up: the record will show whether
your high-confidence calls do better.

## 6. Write `data/sox/YYYY-MM-DD.json`

Get the time stamp right before writing: `date -u +%FT%TZ`.

```json
{
  "date": "YYYY-MM-DD",
  "made_at": "YYYY-MM-DDTHH:MM:SSZ",
  "predict": -1.3,
  "gap_est": -0.8,
  "drift_est": -0.5,
  "confidence": "medium",
  "summary": {
    "zh": "两三句话说明理由（中文，80–140 字）：先说缺口，再说开盘后的判断和依据。",
    "en": "Two or three sentences (40–70 words): the gap first, then the call on the session and why."
  },
  "factors": [
    {"dir": "down", "zh": "一句话因素", "en": "One-line factor"},
    {"dir": "up", "zh": "…", "en": "…"},
    {"dir": "mixed", "zh": "…", "en": "…"}
  ],
  "risk": {"zh": "什么情况会证明预测错了", "en": "What would prove this call wrong"},
  "views": [
    {"who": "Chris Verrone", "source": "Strategas (on CNBC)", "stance": "up",
     "url": "https://…the article…",
     "en": "One or two sentences in your own words.",
     "zh": "一两句话，用自己的话概括。"}
  ]
}
```

- `predict`, `gap_est`, `drift_est`: percent, one decimal; `predict` never 0.
- `confidence`: `low`, `medium` or `high`.
- `factors`: the 3–6 factors that mattered most, most important first, each
  with `dir` = `up`, `down` or `mixed` and the key number (e.g. "NVDA +2.1%
  pre-market after earnings").
- `views`: 2–6 items (aim for 3–6). `who` is the person (omit if none is
  named), `source` the firm/outlet, `stance` = `up`, `down` or `mixed` on
  chips today, `url` the specific article it came from (not a home page),
  dated within the last two days. Paraphrase in your own words; no long
  quotes. Only include a view if a search result ties it to that person or
  outlet and that URL. Never invent or guess an attribution; if a claim
  can't be pinned to a source, leave it out.
- Chinese: natural Simplified Chinese with standard names (英伟达, 台积电,
  美光, 阿斯麦, 博通, 美联储).

Check it: `python sox.py check data/sox/YYYY-MM-DD.json`; fix every ERROR.

## 7. Publish

```bash
git add data/sox/YYYY-MM-DD.json data/sox-lessons.md
git commit -m "sox predict: YYYY-MM-DD"
git push origin HEAD:main
```

Only add those files. Don't run `python sox.py` without arguments, and don't
touch `docs/`, `data/sox-market.json` or `data/sox-brief/`: GitHub Actions
build those. If the push is rejected because `main` moved,
`git pull --rebase origin main` and push again.

## 8. Finish

End with a short report: date, the call (gap + drift), the trade side, the
New York time you pushed, the three biggest factors, the views you listed,
and any rule you changed.
