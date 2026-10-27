"""Write data/sox-brief/YYYY-MM-DD.md: the pre-market data brief for SOX预测.

The cloud routine that makes the call can't reach market-data sites, but
GitHub Actions can (.github/workflows/sox-brief.yml, shortly before the
routine). The brief gives it hard numbers to reason from:

  1. Live pre-market / overnight quotes: chip stocks, index futures, Asia and
     Europe, rates, dollar, oil, VIX.
  2. Where SOX stands: recent returns, volatility, moving averages, RSI.
  3. Base rates from 5 years of SOX history: how the session after a gap of
     today's size, or after a move like yesterday's, usually went.
  4. The forecast track record so far, against a naive baseline.

Usage: python sox_brief.py
"""

import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import sox_model
from sox import chart, day_of, load_predictions, MARKET

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "data" / "sox-brief"

# (symbol, label) per group, in brief order.
GROUPS = [
    ("Semiconductor ETFs (pre-market)", [
        ("SOXX", "iShares Semiconductor ETF"), ("SMH", "VanEck Semiconductor ETF"),
    ]),
    ("Largest SOX members (pre-market)", [
        ("NVDA", "Nvidia"), ("AVGO", "Broadcom"), ("AMD", "AMD"), ("TSM", "TSMC ADR"),
        ("MU", "Micron"), ("ASML", "ASML ADR"), ("QCOM", "Qualcomm"), ("AMAT", "Applied Materials"),
        ("LRCX", "Lam Research"), ("KLAC", "KLA"), ("INTC", "Intel"), ("TXN", "Texas Instruments"),
        ("ADI", "Analog Devices"), ("MRVL", "Marvell"), ("ARM", "Arm"), ("MCHP", "Microchip"),
        ("NXPI", "NXP"), ("ON", "onsemi"), ("MPWR", "Monolithic Power"),
    ]),
    ("AI demand bellwethers (pre-market)", [
        ("MSFT", "Microsoft"), ("GOOGL", "Alphabet"), ("AMZN", "Amazon"), ("META", "Meta"),
        ("ORCL", "Oracle"), ("SMCI", "Super Micro"),
    ]),
    ("US index futures and ETFs", [
        ("NQ=F", "Nasdaq-100 futures"), ("ES=F", "S&P 500 futures"), ("RTY=F", "Russell 2000 futures"),
        ("QQQ", "Nasdaq-100 ETF (pre-market)"),
    ]),
    ("Asia (today's session)", [
        ("2330.TW", "TSMC (Taiwan)"), ("000660.KS", "SK Hynix"), ("005930.KS", "Samsung Electronics"),
        ("8035.T", "Tokyo Electron"), ("6857.T", "Advantest"), ("^TWII", "Taiwan Weighted"),
        ("^KS11", "KOSPI"), ("^N225", "Nikkei 225"), ("^HSI", "Hang Seng"),
    ]),
    ("Europe (live)", [
        ("ASML.AS", "ASML (Amsterdam)"), ("BESI.AS", "BE Semiconductor"), ("IFX.DE", "Infineon"),
        ("STMPA.PA", "STMicro"), ("^STOXX50E", "Euro Stoxx 50"),
    ]),
    ("Rates, dollar, commodities, risk", [
        ("^TNX", "US 10-year yield (x10)"), ("DX-Y.NYB", "US dollar index"), ("USDJPY=X", "USD/JPY"),
        ("CL=F", "WTI crude"), ("GC=F", "Gold"), ("^VIX", "VIX"), ("BTC-USD", "Bitcoin"),
    ]),
]


def quote(symbol):
    """Latest price (pre-market included) and % change vs the previous regular close."""
    d = chart(symbol, range="10d", interval="1d")
    off = d["meta"].get("gmtoffset", 0)
    closes = [(day_of(ts, off), c) for ts, c in zip(d.get("timestamp") or [], d["indicators"]["quote"][0]["close"])
              if c is not None]
    last = None
    try:
        i = chart(symbol, range="1d", interval="1m", includePrePost="true")
        for ts, c in zip(i.get("timestamp") or [], i["indicators"]["quote"][0]["close"]):
            if c is not None:
                last = (ts, c)
    except Exception:
        i = d
    if last is None:   # nothing traded yet today: fall back to the last daily close
        if len(closes) < 2:
            return None
        return {"price": closes[-1][1], "pct": (closes[-1][1] / closes[-2][1] - 1) * 100,
                "at": closes[-1][0] + " close"}
    day = day_of(last[0], i["meta"].get("gmtoffset", off))
    prev = [c for dd, c in closes if dd < day]
    if not prev:
        return None
    return {"price": last[1], "pct": (last[1] / prev[-1] - 1) * 100,
            "at": datetime.fromtimestamp(last[0], timezone.utc).strftime("%H:%M UTC")}


def quotes_section():
    """Markdown tables of live quotes, plus {symbol: quote} for later sections."""
    out, got = [], {}
    for title, items in GROUPS:
        out += [f"### {title}", "", "| Symbol | Name | Last | % vs prev close | As of |", "|---|---|---|---|---|"]
        for sym, name in items:
            try:
                q = quote(sym)
            except Exception as e:
                q, err = None, e
            if q:
                got[sym] = q
                out.append(f"| {sym} | {name} | {q['price']:,.2f} | {q['pct']:+.2f}% | {q['at']} |")
            else:
                out.append(f"| {sym} | {name} | n/a | n/a | |")
            time.sleep(0.2)
        out.append("")
    return out, got


def sox_history(date, symbol="^SOX", years="5y"):
    """(date, open, close) for years of sessions before date."""
    r = chart(symbol, range=years, interval="1d")
    q = r["indicators"]["quote"][0]
    off = r["meta"].get("gmtoffset", -14400)
    rows = [(day_of(ts, off), o, c) for ts, o, c in zip(r["timestamp"], q["open"], q["close"]) if o and c]
    return [x for x in rows if x[0] < date]   # a live bar for today isn't history yet


def pct(a, b):
    return (a / b - 1) * 100


def rsi(closes, n=14):
    ch = [b - a for a, b in zip(closes[-n - 1:-1], closes[-n:])]
    up = sum(x for x in ch if x > 0) / n
    dn = -sum(x for x in ch if x < 0) / n
    return 100 if dn == 0 else 100 - 100 / (1 + up / dn)


def state_section(rows):
    closes = [c for _, _, c in rows]
    rets = [pct(b, a) for a, b in zip(closes, closes[1:])]
    last_day, _, last = rows[-1]
    ma = lambda n: sum(closes[-n:]) / n
    hi52 = max(closes[-252:])
    vol20 = statistics.pstdev(rets[-20:])
    return [
        f"Last close {last_day}: **{last:,.2f}** ({rets[-1]:+.2f}% on the day)", "",
        "| Measure | Value |", "|---|---|",
        f"| 1-day / 5-day / 20-day return | {rets[-1]:+.2f}% / {pct(closes[-1], closes[-6]):+.2f}% / {pct(closes[-1], closes[-21]):+.2f}% |",
        f"| Last 5 daily moves | {', '.join(f'{x:+.2f}%' for x in rets[-5:])} |",
        f"| 20-day realized vol (std of daily %) | {vol20:.2f}% (5-year avg {statistics.pstdev(rets):.2f}%) |",
        f"| vs 20 / 50 / 200-day average | {pct(last, ma(20)):+.1f}% / {pct(last, ma(50)):+.1f}% / {pct(last, ma(200)):+.1f}% |",
        f"| RSI(14) | {rsi(closes):.0f} |",
        f"| From 52-week closing high | {pct(last, hi52):+.1f}% |",
        "",
    ]


def bucket_table(pairs, edges, label):
    """pairs: (x, outcomes dict). Groups by x into buckets between edges."""
    out = [f"| {label} | Days | Avg open→close | Open→close same sign as gap | Avg close→close | Close→close up |",
           "|---|---|---|---|---|---|"]
    bounds = [-1e9] + edges + [1e9]
    for lo, hi in zip(bounds, bounds[1:]):
        sel = [o for x, o in pairs if lo <= x < hi]
        if not sel:
            continue
        name = (f"< {hi:+g}%" if lo < -1e8 else f"≥ {lo:+g}%" if hi > 1e8 else f"{lo:+g}% to {hi:+g}%")
        n = len(sel)
        same = sum(1 for o in sel if o["gap"] * o["intra"] > 0) / n * 100
        out.append(f"| {name} | {n} | {statistics.mean(o['intra'] for o in sel):+.2f}% | {same:.0f}% | "
                   f"{statistics.mean(o['ret'] for o in sel):+.2f}% | {sum(1 for o in sel if o['ret'] > 0) / n * 100:.0f}% |")
    return out


def base_rates_section(rows):
    days = []
    for (d0, o0, c0), (d1, o1, c1) in zip(rows, rows[1:]):
        days.append({"date": d1, "gap": pct(o1, c0), "intra": pct(c1, o1), "ret": pct(c1, c0)})
    prev_pairs = [(a["ret"], b) for a, b in zip(days, days[1:])]
    gap_pairs = [(o["gap"], o) for o in days]
    out = [f"From {len(days)} SOX sessions ({days[0]['date']} to {days[-1]['date']}). "
           "Gap = open vs previous close (a proxy for the pre-market move); "
           "open→close = what the session did after the open.", "",
           "**By today's opening gap** (use the SOXX pre-market move above as the expected gap):", ""]
    out += bucket_table(gap_pairs, [-3, -1.5, -0.5, 0.5, 1.5, 3], "Gap")
    out += ["", "**By the previous day's close→close move:**", ""]
    out += bucket_table(prev_pairs, [-4, -2, -0.5, 0.5, 2, 4], "Previous day")
    beta = statistics.correlation([o["gap"] for o in days], [o["ret"] for o in days])
    out += ["", f"Correlation of gap with the day's close→close move: {beta:.2f}. "
            f"All days: avg open→close {statistics.mean(o['intra'] for o in days):+.2f}%, "
            f"close→close up {sum(1 for o in days if o['ret'] > 0) / len(days) * 100:.0f}% of the time.", ""]
    return out


def model_section(date, quotes):
    """Refit the regression (sox_model.py), save it, and apply it to today's pre-market."""
    model = sox_model.build(sox_history(date, "^SOX", "10y"), sox_history(date, "QQQ", "10y"))
    sox_model.save(model)
    sm = model["summary"]
    out = ["A ridge regression for the SOX's move **after the open** (open→close), fitted on "
           f"{model['days']} sessions ({model['trained_on'][0]} to {model['trained_on'][1]}). "
           "Walk-forward test (each year predicted only from earlier years):", "",
           "| Year | Days | Avg error, model | Avg error, \"no move after the open\" | Direction right (days with signal) | Correlation |",
           "|---|---|---|---|---|---|"]
    for t in model["walk_forward"]:
        hit = f"{t['sign_hit'] * 100:.0f}% ({t['sign_days']})" if t["sign_hit"] is not None else "—"
        out.append(f"| {t['year']} | {t['days']} | {t['mae_drift_model']:.3f} | {t['mae_drift_zero']:.3f} | {hit} | {t['corr']:+.2f} |")
    out += ["", f"Beat \"no move after the open\" in {sm['years_beating_zero']} of {sm['years']} years; "
            f"direction right {sm['sign_hit'] * 100:.0f}% of {sm['sign_days']} signal days. "
            "**Treat it as a weak, objective anchor, not a signal.**", ""]
    closes = [c for _, _, c in sox_history(date)]
    sx, qq = quotes.get("SOXX"), quotes.get("QQQ")
    if sx and qq:
        x = sox_model.features(closes, sx["pct"], qq["pct"])
        drift = sox_model.predict(model, x)
        out += [f"**Today** (SOXX pre-market {sx['pct']:+.2f}% and QQQ {qq['pct']:+.2f}% at {sx['at']}): "
                f"model after-open move **{drift:+.2f}%**, so model forecast ≈ **{sx['pct'] + drift:+.2f}%**. "
                "The page records the model's value again at the moment of your call, from the pre-market then.", "",
                "| Feature | Today | Coefficient | Contribution |", "|---|---|---|---|"]
        for f in sox_model.FEATURES:
            c = model["coef"][f]
            out.append(f"| {f} | {x[f]:+.2f} | {c:+.4f} | {c * sox_model.clip(x[f]):+.3f} |")
        out.append("")
    else:
        out += ["Today's SOXX or QQQ pre-market quote is missing, so no model value.", ""]
    return out


def track_record_section():
    preds = load_predictions()
    try:
        market = json.loads(MARKET.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        market = {}
    done = [(d, p["predict"], market[d]) for d, p in sorted(preds.items())
            if "sox" in market.get(d, {}) and "pre" in market[d]]
    if not done:
        return ["No scored forecasts yet.", ""]
    out = ["| Date | Forecast | Model | SOXX pre-mkt at call | Actual SOX | Error | Direction |",
           "|---|---|---|---|---|---|---|"]
    for d, f, m in done[-15:]:
        a, pre = m["sox"], m["pre"]
        mod = f"{m['model']:+.2f}%" if "model" in m else "—"
        out.append(f"| {d} | {f:+.1f}% | {mod} | {pre:+.2f}% | {a:+.2f}% | {f - a:+.2f} | "
                   f"{'right' if (f > 0) == (a > 0) else 'wrong'} |")
    n = len(done)
    mae = statistics.mean(abs(f - m["sox"]) for _, f, m in done)
    base = statistics.mean(abs(m["pre"] - m["sox"]) for _, f, m in done)
    bias = statistics.mean(f - m["sox"] for _, f, m in done)
    hit = sum(1 for _, f, m in done if (f > 0) == (m["sox"] > 0))
    bhit = sum(1 for _, f, m in done if (m["pre"] > 0) == (m["sox"] > 0))
    with_model = [(f, m) for _, f, m in done if "model" in m]
    model_note = (f" The model's avg error {statistics.mean(abs(m['model'] - m['sox']) for _, m in with_model):.2f} "
                  f"over {len(with_model)} days (yours on the same days "
                  f"{statistics.mean(abs(f - m['sox']) for f, m in with_model):.2f})." if with_model else "")
    out += ["", f"Over {n} days: avg error **{mae:.2f}** pts vs **{base:.2f}** for the naive baseline "
            f"(forecast = SOXX pre-market move). Direction right {hit}/{n} (baseline {bhit}/{n}). "
            f"Average signed error (forecast − actual) {bias:+.2f} pts "
            f"({'too bullish' if bias > 0.1 else 'too bearish' if bias < -0.1 else 'no clear bias'})." + model_note, ""]
    return out


def main():
    now = datetime.now(timezone.utc)
    # The brief is for today's session: today's date in New York.
    date = day_of(now.timestamp(), chart("SOXX", range="1d", interval="1d")["meta"].get("gmtoffset", -14400))
    rows = sox_history(date)
    lines = [f"# SOX pre-market brief, {date}", "",
             f"Generated {now.strftime('%Y-%m-%d %H:%M UTC')} by GitHub Actions from Yahoo Finance. "
             "Quotes are live snapshots; check the time in each row.", "",
             "## 1. Live quotes", ""]
    qlines, quotes = quotes_section()
    lines += qlines
    lines += ["## 2. Where SOX stands", ""] + state_section(rows)
    lines += ["## 3. Base rates (5 years of SOX)", ""] + base_rates_section(rows)
    lines += ["## 4. Statistical model (reference)", ""] + model_section(date, quotes)
    lines += ["## 5. Forecast track record", ""] + track_record_section()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{date}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
