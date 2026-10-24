"""Build docs/sox.html: SOX预测 / SOX Forecast.

Each US trading morning the cloud routine (SOX_TASK.md) writes
data/sox/YYYY-MM-DD.json with Claude's call for the day's move in the PHLX
Semiconductor Index (SOX). This script, run by GitHub Actions
(.github/workflows/sox.yml), adds the market side from Yahoo Finance -- the
SOXX pre-market move at the moment the call was made, and the actual SOX/SOXX
close-to-close moves -- into data/sox-market.json, then renders the page.

Usage:
  python sox.py              fetch market data and rebuild docs/sox.html
  python sox.py check FILE   validate a prediction file (no network)
"""

import json
import re
import statistics
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent
PRED = ROOT / "data" / "sox"
MARKET = ROOT / "data" / "sox-market.json"
OUT = ROOT / "docs" / "sox.html"
UA = "Mozilla/5.0"
HOSTS = ("query1", "query2")
CHART = "https://{}.finance.yahoo.com/v8/finance/chart/{}?{}"


def chart(symbol, **params):
    """Yahoo Finance chart API result for one symbol, trying both hosts."""
    q = urllib.parse.urlencode(params)
    err = None
    for host in HOSTS:
        url = CHART.format(host, urllib.parse.quote(symbol), q)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())["chart"]["result"][0]
        except Exception as e:
            err = e
            time.sleep(2)
    raise RuntimeError(f"{symbol}: {err}")


def day_of(ts, offset):
    """Exchange-local date (YYYY-MM-DD) of a unix time, given the UTC offset in seconds."""
    return (datetime.fromtimestamp(ts + offset, timezone.utc)).strftime("%Y-%m-%d")


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def daily(symbol, opens=None):
    """{date: close} for recent sessions, plus the set of dates whose close is final.

    Pass a dict as opens to also collect {date: opening price}.
    """
    r = chart(symbol, range="3mo", interval="1d")
    meta = r["meta"]
    off = meta.get("gmtoffset", -14400)
    closes = {}
    q = r["indicators"]["quote"][0]
    for ts, o, c in zip(r.get("timestamp") or [], q["open"], q["close"]):
        if c is not None:
            closes[day_of(ts, off)] = c
        if o is not None and opens is not None:
            opens[day_of(ts, off)] = o
    # Today's bar is live until the regular session has ended (plus a margin).
    final = set(closes)
    reg = meta.get("currentTradingPeriod", {}).get("regular")
    if reg and time.time() < reg["end"] + 600:
        final.discard(day_of(reg["start"], reg["gmtoffset"]))
    return closes, final


def changes(closes, final):
    """{date: % change vs previous close} for final sessions."""
    days = sorted(closes)
    return {d: round((closes[d] / closes[p] - 1) * 100, 2)
            for p, d in zip(days, days[1:]) if d in final}


_intraday = {}


def session_bars(symbol, date, kind):
    """[(time, close)] 1-minute bars of one session ("pre" or "regular") on date.

    Yahoo keeps 1-minute bars for about a week.
    """
    if symbol not in _intraday:
        _intraday[symbol] = chart(symbol, range="5d", interval="1m", includePrePost="true")
    r = _intraday[symbol]
    periods = r["meta"].get("tradingPeriods", {})
    if isinstance(periods, list):   # indexes have no pre/post: a plain list of regular sessions
        periods = {"regular": periods}
    sess = None
    for p in periods.get(kind, []):
        p = p[0] if isinstance(p, list) else p
        if day_of(p["start"], p["gmtoffset"]) == date:
            sess = p
    if sess is None:
        return []
    return [(ts, c) for ts, c in zip(r.get("timestamp") or [], r["indicators"]["quote"][0]["close"])
            if c is not None and sess["start"] <= ts < sess["end"]]


def price_at(symbol, made_at, date):
    """(time, price) of a symbol in the pre-market session of date, at made_at.

    Uses the last 1-minute pre-market bar at or before made_at (or the last
    pre-market bar if the call came later); a thinly traded symbol with no bar
    yet falls back to its first pre-market bar after made_at.
    """
    bars = session_bars(symbol, date, "pre")
    if not bars:
        return None
    upto = min(bars[-1][0], made_at)
    last = [b for b in bars if b[0] <= upto]
    return last[-1] if last else bars[0]


# Paper-trading rules, all compared on the page. Every rule trades SOXL (3x
# bull) or SOXS (3x bear); thresholds are measured on the SOX index itself.
RULES = ("A", "B", "1", "2", "3", "4", "5", "6")
SIZE = {"high": 1.0, "medium": 0.5, "low": 0.25}   # rule 2: share of the balance by confidence
FILTER = 0.5     # rule 3: trade only if |forecast - pre-market| >= this many points
TRAIL_ON = 1.0   # rule 5: start trailing once the SOX has moved this far our way...
CONFIRM = 30 * 60   # rule 6: check the direction this long after the open


def at_or_before(bars, ts):
    got = [b for b in bars if b[0] <= ts]
    return got[-1] if got else bars[0]


def simulate_day(date, p, pre, sox_prev, sox_open, vol20, etf_open, etf_close):
    """Entry and exit of every rule for one finished session.

    Returns {rule: {"sym", "buy", "sell", "frac", "why", "at"}} or
    {rule: {"skip": reason}}; why = "close", "tp" (take profit), "sl" (stop
    loss) or "trail". Returns None if the 1-minute bars are gone (they're kept
    about a week).
    """
    predict = p["predict"]
    side = "SOXL" if predict > pre else "SOXS"
    d = 1 if side == "SOXL" else -1
    sox = session_bars("^SOX", date, "regular")
    bars = {s_: session_bars(s_, date, "regular") for s_ in ("SOXL", "SOXS")}
    if not sox or not all(bars.values()):
        return None
    start = sox[0][0]

    def trade(sym=side, buy=None, sell=None, frac=1.0, why="close", at=None):
        return {"sym": sym, "buy": round(buy if buy is not None else etf_open[sym], 4),
                "sell": round(sell if sell is not None else etf_close[sym], 4),
                "frac": frac, "why": why, "at": iso(at) if at else None}

    def exit_when(test):
        """Sell at the first minute where test(sox_close) says so, else at the close."""
        for ts, c in sox:
            why = test(c)
            if why:
                return trade(sell=at_or_before(bars[side], ts)[1], why=why, at=ts)
        return trade()

    out = {"A": trade()}

    # B: the SOX's move on the day (vs yesterday's close) reaches twice the forecast.
    band = 2 * abs(predict)

    def rule_b(c):
        chg = (c / sox_prev - 1) * 100
        return ("tp" if chg * d > 0 else "sl") if abs(chg) >= band else None
    out["B"] = exit_when(rule_b)

    # 1: baseline that ignores the forecast: follow the pre-market move.
    base = "SOXL" if pre >= 0 else "SOXS"
    out["1"] = trade(sym=base)

    # 2: position size by the forecast's confidence (none given: medium).
    out["2"] = trade(frac=SIZE.get(p.get("confidence"), SIZE["medium"]))

    # 3: only when the forecast expects a real move after the open.
    out["3"] = trade() if abs(predict - pre) >= FILTER else {"skip": "filter"}

    # 4: take profit / stop loss at one recent daily standard deviation from the open.
    def rule_4(c):
        mv = (c / sox_open - 1) * 100
        return ("tp" if mv * d > 0 else "sl") if abs(mv) >= vol20 else None
    out["4"] = exit_when(rule_4)

    # 5: once the SOX has moved TRAIL_ON% our way from the open, sell if half
    # of the best gain is given back.
    peak = [0.0]

    def rule_5(c):
        g = d * (c / sox_open - 1) * 100
        peak[0] = max(peak[0], g)
        return "trail" if peak[0] >= TRAIL_ON and g <= peak[0] / 2 else None
    out["5"] = exit_when(rule_5)

    # 6: buy 30 minutes after the open, only if the SOX has moved our way by then.
    ts6, c6 = at_or_before(sox, start + CONFIRM)
    if d * (c6 - sox_open) > 0:
        out["6"] = trade(buy=at_or_before(bars[side], ts6)[1])
        out["6"]["in_at"] = iso(ts6)
    else:
        out["6"] = {"skip": "no confirm"}
    return out


def model_at(made_at, date, pre, sox_closes):
    """The model's forecast for date, from the pre-market at made_at."""
    import sox_model   # sox_model doesn't import this module, so no cycle
    model = sox_model.load()
    if model is None:
        return None
    qqq, _ = daily("QQQ")
    prev = [d for d in sorted(qqq) if d < date]
    q = price_at("QQQ", made_at, date)
    hist = [sox_closes[d] for d in sorted(sox_closes) if d < date]
    if not prev or q is None:
        return None
    x = sox_model.features(hist, pre, pct(q[1], qqq[prev[-1]]))
    if x is None:
        return None
    drift = sox_model.predict(model, x)
    return {"model": round(pre + drift, 2), "model_drift": round(drift, 2)}


def pct(a, b):
    return (a / b - 1) * 100


def vol(closes, date, n=20):
    """Standard deviation of the n daily % moves before date."""
    days = [d for d in sorted(closes) if d < date][-(n + 1):]
    rets = [(closes[b] / closes[a] - 1) * 100 for a, b in zip(days, days[1:])]
    return statistics.pstdev(rets) if len(rets) >= 5 else None


def premarket(made_at, date, soxx_closes):
    """SOXX pre-market % change at the time the prediction was made, vs the previous close."""
    prev = [d for d in sorted(soxx_closes) if d < date]
    if not prev:
        return None
    base = soxx_closes[prev[-1]]
    last = price_at("SOXX", made_at, date)
    if last is None:
        return None
    return {"pre": round((last[1] / base - 1) * 100, 2), "pre_price": round(last[1], 2),
            "pre_at": iso(last[0]), "prev_close": round(base, 2)}


def load_predictions():
    preds = {}
    for p in sorted(PRED.glob("????-??-??.json")):
        try:
            preds[p.stem] = json.loads(p.read_text(encoding="utf-8"))
        except ValueError as e:
            print("skip", p.name, e)
    return preds


def update_market(preds):
    try:
        market = json.loads(MARKET.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        market = {}
    sox_opens = {}
    sox, sox_final = daily("^SOX", sox_opens)
    soxx, soxx_final = daily("SOXX")
    sox_chg, soxx_chg = changes(sox, sox_final), changes(soxx, soxx_final)
    etf = {}   # SOXL/SOXS (closes, final, opens), fetched once when a trade needs them
    for date, p in preds.items():
        m = market.setdefault(date, {})
        made = datetime.fromisoformat(p["made_at"].replace("Z", "+00:00")).timestamp()
        if "pre" not in m:
            try:
                got = premarket(made, date, soxx)
                if got:
                    m.update(got)
                else:
                    print(date, "no pre-market SOXX data yet")
            except Exception as e:
                print(date, "pre-market lookup failed:", e)
        # The statistical model's call (sox_model.py), from the pre-market at
        # the moment of the forecast: SOXX and QQQ, plus the SOX's history.
        if "pre" in m and "model" not in m:
            try:
                got = model_at(made, date, m["pre"], sox)
                if got:
                    m.update(got)
            except Exception as e:
                print(date, "model lookup failed:", e)
        # Paper trades: today's side and opening price as soon as the session
        # opens; every rule's result once the close is final (see simulate_day).
        m.pop("trade", None)   # older single-rule format
        if "pre" in m:
            side = "SOXL" if p["predict"] > m["pre"] else "SOXS"
            if "SOXL" not in etf:
                for sym in ("SOXL", "SOXS"):
                    opens = {}
                    etf[sym] = daily(sym, opens) + (opens,)
            if date in etf[side][2]:
                m["entry"] = {"sym": side, "buy": round(etf[side][2][date], 4)}
            if date in sox_final and date in etf["SOXL"][1] and not m.get("sim"):
                prev = [d for d in sorted(sox) if d < date]
                try:
                    got = simulate_day(
                        date, p, m["pre"], sox[prev[-1]], sox_opens[date], vol(sox, date),
                        {s_: etf[s_][2][date] for s_ in etf}, {s_: etf[s_][0][date] for s_ in etf})
                except Exception as e:
                    got = None
                    print(date, "paper-trade simulation failed:", e)
                if got:
                    m["sim"] = got
                else:
                    print(date, "no 1-minute bars for the paper trades")
        if date in sox_chg:
            m.update({"sox": sox_chg[date], "sox_close": round(sox[date], 2)})
        if date in soxx_chg:
            m["soxx"] = soxx_chg[date]
    MARKET.write_text(json.dumps(dict(sorted(market.items())), ensure_ascii=False, indent=1) + "\n",
                      encoding="utf-8")
    return market


def check(path):
    """Validate one prediction file; returns a list of problems."""
    path = Path(path)
    errs = []
    try:
        p = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [f"cannot read JSON: {e}"]
    if p.get("date") != path.stem:
        errs.append(f'"date" must be {path.stem}')
    v = p.get("predict")
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        errs.append('"predict" must be a number (percent, e.g. 1.3 or -0.8)')
    else:
        if v == 0:
            errs.append('"predict" must be a clear call: up or down, not 0')
        if abs(v) > 15:
            errs.append('"predict" is out of range (|x| <= 15)')
        if round(v, 1) != v:
            errs.append('"predict" takes one decimal place')
    if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", str(p.get("made_at", ""))):
        errs.append('"made_at" must be UTC like 2026-10-26T12:52:10Z')
    for k in ("summary",):
        s = p.get(k) or {}
        if not (isinstance(s, dict) and s.get("zh") and s.get("en")):
            errs.append(f'"{k}" needs non-empty "zh" and "en"')
    f = p.get("factors")
    if not (isinstance(f, list) and 3 <= len(f) <= 6
            and all(isinstance(x, dict) and x.get("zh") and x.get("en") and x.get("dir") in ("up", "down", "mixed")
                    for x in f)):
        errs.append('"factors" must be 3-6 items, each {"dir": up|down|mixed, "zh", "en"}')
    vs = p.get("views")
    if not (isinstance(vs, list) and 2 <= len(vs) <= 6
            and all(isinstance(x, dict) and x.get("source") and x.get("zh") and x.get("en")
                    and x.get("stance") in ("up", "down", "mixed")
                    and re.match(r"https?://[^/\s]+/\S+", str(x.get("url", ""))) for x in vs)):
        errs.append('"views" must be 2-6 items, each {"who"?, "source", "url" (the article), '
                    '"stance": up|down|mixed, "zh", "en"}')
    for k in ("gap_est", "drift_est"):
        if k in p and (not isinstance(p[k], (int, float)) or isinstance(p[k], bool)):
            errs.append(f'"{k}" must be a number (percent)')
    if isinstance(v, (int, float)) and all(isinstance(p.get(k), (int, float)) for k in ("gap_est", "drift_est")):
        if abs(p["gap_est"] + p["drift_est"] - v) > 0.11:
            errs.append('"predict" must equal gap_est + drift_est (rounded to one decimal)')
    if "confidence" in p and p["confidence"] not in ("low", "medium", "high"):
        errs.append('"confidence" must be low, medium or high')
    if "risk" in p and not (isinstance(p["risk"], dict) and p["risk"].get("zh") and p["risk"].get("en")):
        errs.append('"risk" needs non-empty "zh" and "en"')
    return errs


def render(preds, market, now):
    rows = []
    for date in sorted(preds):
        p, m = preds[date], market.get(date, {})
        rows.append({
            "d": date, "p": p["predict"], "at": p.get("made_at"),
            "pre": m.get("pre"), "preAt": m.get("pre_at"),
            "a": m.get("sox"), "ax": m.get("soxx"), "close": m.get("sox_close"),
            "s": p.get("summary"), "f": p.get("factors", []), "ent": m.get("entry"), "sim": m.get("sim"),
            "g": p.get("gap_est"), "dr": p.get("drift_est"), "cf": p.get("confidence"), "rk": p.get("risk"),
            "v": p.get("views", []), "mo": m.get("model"),
        })
    data = json.dumps({"rows": rows, "updated": iso(now.timestamp())}, ensure_ascii=False)
    return TEMPLATE.replace("__DATA__", data.replace("</", "<\\/"))


TEMPLATE = r"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SOX预测 · SOX Forecast</title>
<style>
:root {
  --bg: #f2f7f6; --paper: #ffffff; --ink: #1f2b30; --muted: #66767c; --line: #dfe9e6; --grid: #e8efed;
  --accent: #0e8a7c; --accent-soft: #dff3ef; --accent-ink: #ffffff;
  --pred: #2a78d6; --act: #eb6834; --model: #1baf7a; --up: #12805c; --down: #c8372d;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0f1719; --paper: #162123; --ink: #e4eeee; --muted: #93a5a8; --line: #24363a; --grid: #1e2d30;
    --accent: #3cc8b4; --accent-soft: #123430; --accent-ink: #062320;
    --pred: #3987e5; --act: #d95926; --model: #199e70; --up: #3fbf8f; --down: #ff7a6e; color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #0f1719; --paper: #162123; --ink: #e4eeee; --muted: #93a5a8; --line: #24363a; --grid: #1e2d30;
  --accent: #3cc8b4; --accent-soft: #123430; --accent-ink: #062320;
  --pred: #3987e5; --act: #d95926; --model: #199e70; --up: #3fbf8f; --down: #ff7a6e; color-scheme: dark;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 18px/1.6 -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif;
  -webkit-font-smoothing: antialiased; }
.wrap { max-width: 860px; margin: 0 auto;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
.zh { margin-left: 6px; opacity: .75; }
body.m-en .zh { display: none !important; }
body.m-zh .en { display: none !important; }
body.m-en .zh, body.m-zh .zh { margin-left: 0; }
body.m-zh .zh { opacity: 1; }
.blk > .zh { display: block; margin-left: 0; }
.seg { display: inline-flex; border: 1px solid var(--line); border-radius: 999px; overflow: hidden; background: var(--bg); padding: 2px; }
.seg button { border: 0; background: none; color: var(--muted); padding: 4px 12px; font: inherit; font-size: 15px; cursor: pointer; border-radius: 999px; }
.seg button.on { background: var(--accent); color: var(--accent-ink); }
.top { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
header { padding-block: 22px 18px; border-bottom: 1px solid var(--line); background: var(--paper); }
.back { display: inline-flex; align-items: center; gap: 4px; color: var(--accent); text-decoration: none; font-weight: 600; font-size: 16px; }
.back:hover { text-decoration: underline; }
.back svg { width: 18px; height: 18px; }
h1 { margin: 10px 0 0; font-size: clamp(28px, 6vw, 38px); line-height: 1.15; }
h1 .zh { font-size: .6em; font-weight: 600; color: var(--muted); opacity: 1; }
body.m-zh h1 .zh { font-size: 1em; color: inherit; }
.card { background: var(--paper); border: 1px solid var(--line); border-radius: 16px; padding: 20px; margin-top: 22px; }
.label { color: var(--muted); font-size: 15px; font-weight: 600; }
.hero { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 10px 28px; }
.duo { display: grid; grid-template-columns: 1fr 1fr; margin-top: 8px; }
.duo > div { min-width: 0; }
.duo > div + div { border-left: 1px solid var(--line); padding-left: clamp(12px, 4vw, 28px); }
.big.wait { color: var(--muted); }
.verdict { margin: 12px 0 2px; font-size: 16px; }
.duo2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.duo2 .bal { font-size: clamp(24px, 7vw, 40px); }
.duo2 .stats { margin: 4px 0 0; gap: 4px 14px; }
.duo2 .stats b { font-size: 16px; }
.tag { display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; }
.tablewrap { overflow-x: auto; }
.tablewrap table { min-width: 560px; }
.rulebox { margin: 0 0 10px; }
.rules { margin: 8px 0 4px; padding: 0; list-style: none; display: grid; gap: 4px; font-size: 14px; color: var(--muted); }
.rules b { display: inline-block; min-width: 1.4em; color: var(--ink); }
.rules .zh { margin-left: 4px; }
body.m-bi .rules .zh { display: block; margin-left: 1.6em; }
table.cmp { min-width: 720px; }
table.cmp tbody tr { cursor: pointer; }
table.cmp tbody tr:hover { background: var(--hover, var(--grid)); }
table.cmp tbody tr.sel { background: var(--accent-soft); }
table.cmp td:first-child { min-width: 12em; }
body.m-bi table.cmp td:first-child .zh { display: block; margin: 0 0 0 1.2em; }
table.cmp td:first-child b { display: inline-block; min-width: 1.2em; }
.crown { display: inline-block; margin-left: 4px; padding: 0 7px; border-radius: 999px; background: var(--accent); color: var(--accent-ink);
  font-size: 12px; font-weight: 700; }
.crown .zh { margin-left: 0; }
#trades h4 { margin: 14px 0 0; font-size: 15px; }
.big { font-size: clamp(54px, 15vw, 84px); font-weight: 800; line-height: 1; letter-spacing: -.02em;
  font-variant-numeric: tabular-nums; margin-top: 6px; }
.big .arr { font-size: .55em; vertical-align: .18em; margin-right: 4px; }
.big.up .arr { color: var(--up); } .big.down .arr { color: var(--down); }
.duo .big { font-size: clamp(28px, 8.5vw, 76px); }
.facts { display: grid; gap: 4px; font-size: 16px; padding-bottom: 6px; }
.facts b { font-variant-numeric: tabular-nums; }
.why { margin: 16px 0 0; font-size: 17px; }
.why .zh { display: block; margin: 4px 0 0; }
details { margin-top: 12px; }
summary { cursor: pointer; color: var(--accent); font-weight: 600; font-size: 15px; }
.factors { margin: 8px 0 0; padding: 0; list-style: none; display: grid; gap: 6px; font-size: 16px; }
.factors li { display: grid; grid-template-columns: 1.4em 1fr; gap: 6px; }
.factors .zh { display: block; margin: 0; }
.views { margin: 10px 0 0; padding: 0; list-style: none; display: grid; gap: 14px; }
.views li { display: grid; grid-template-columns: 1.4em 1fr; gap: 6px; font-size: 16px; }
.views .who { font-weight: 700; }
.views .who .zh { display: inline; }
.views .txt .zh { display: block; margin: 2px 0 0; }
.views a.src { display: inline-flex; align-items: center; gap: 2px; margin-top: 4px; color: var(--accent); font-size: 14px;
  font-weight: 600; text-decoration: none; }
.views a.src:hover { text-decoration: underline; }
.views a.src svg { width: 14px; height: 14px; }
.note { margin: 12px 0 0; }
.dir { font-weight: 800; text-align: center; }
.dir.up { color: var(--up); } .dir.down { color: var(--down); } .dir.mixed { color: var(--muted); }
.stats { display: flex; flex-wrap: wrap; gap: 8px 26px; margin-bottom: 12px; font-size: 15px; color: var(--muted); }
.stats b { color: var(--ink); font-size: 20px; font-variant-numeric: tabular-nums; margin-right: 4px; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 14px; color: var(--muted); margin-bottom: 6px; }
.legend i { display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; }
.legend i.ring { border-radius: 50%; border: 2px solid var(--ink); width: 10px; height: 10px; background: var(--paper); }
.chart { position: relative; }
.chart svg { display: block; width: 100%; overflow: visible; }
.chart text { fill: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.tip { position: absolute; pointer-events: none; background: var(--paper); border: 1px solid var(--line);
  border-radius: 10px; padding: 8px 10px; font-size: 14px; line-height: 1.5; box-shadow: 0 6px 18px rgba(0,0,0,.14);
  white-space: nowrap; display: none; z-index: 3; }
.tip i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; }
.empty { color: var(--muted); padding: 30px 0; text-align: center; }
table { width: 100%; border-collapse: collapse; font-size: 15px; font-variant-numeric: tabular-nums; margin-top: 8px; }
th, td { padding: 6px 8px; border-top: 1px solid var(--line); text-align: right; }
th:first-child, td:first-child { text-align: left; }
th { color: var(--muted); font-weight: 600; }
.ok { color: var(--up); } .miss { color: var(--down); }
.rule { color: var(--muted); font-size: 14px; margin: 4px 0 14px; }
.rule .zh { margin: 2px 0 0; }
.bal { font-size: clamp(34px, 9vw, 48px); font-weight: 800; line-height: 1.1; font-variant-numeric: tabular-nums; }
.bal small { font-size: .45em; font-weight: 700; margin-left: 8px; }
.pos { margin: 10px 0 12px; font-size: 16px; }
.pos b { font-variant-numeric: tabular-nums; }
footer { margin-top: 30px; padding: 18px 0 60px; border-top: 1px solid var(--line); color: var(--muted); font-size: 14px; }
footer .zh { display: block; margin: 4px 0 0; }
@media (max-width: 600px) { body { font-size: 17px; } .card { padding: 16px; } }
</style>
</head>
<body class="m-bi">
<header>
  <div class="wrap">
    <div class="top">
      <a class="back" href="./"><svg viewBox="0 0 24 24"><path d="M15 18 9 12l6-6" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg><span class="en" lang="en">Clint Daily News</span><span class="zh" lang="zh">返回主页</span></a>
      <div class="seg" id="lang" role="group" aria-label="语言 Language">
        <button data-m="bi" class="on">双语</button><button data-m="zh">中文</button><button data-m="en">EN</button>
      </div>
    </div>
    <h1><span class="en" lang="en">SOX Forecast</span><span class="zh" lang="zh">SOX预测</span></h1>
  </div>
</header>
<main class="wrap">
  <div class="card" id="today"></div>
  <div class="card" id="views" hidden></div>
  <div class="card">
    <div class="label blk" style="margin-bottom:10px"><span class="en" lang="en">Forecast vs. actual, daily % change of the SOX index</span><span class="zh" lang="zh">预测 vs 实际（SOX 指数当日涨跌幅 %）</span></div>
    <div class="stats" id="stats"></div>
    <div class="legend" id="legend"></div>
    <div class="chart" id="chart"></div>
    <details><summary><span class="en" lang="en">Table</span><span class="zh" lang="zh">数据表</span></summary><div id="table"></div></details>
  </div>
  <div class="card">
    <div class="label blk"><span class="en" lang="en">Paper trading: 8 rules compared, $10,000 each</span><span class="zh" lang="zh">模拟交易：8 种规则对比（各 $10,000 起始）</span></div>
    <div class="rule blk"><span class="en" lang="en">Unless a rule says otherwise: if the forecast is above the SOXX pre-market move at the call, buy SOXL (3x bull) at the open, otherwise SOXS (3x bear), whole shares with the whole balance, and sell at the close. Every trade pays 0.05% each way for fees and slippage. Thresholds are measured on the SOX index.</span><span class="zh" lang="zh">除非规则另有说明：预测涨幅高于预测时的 SOXX 盘前涨幅就按开盘价买入 SOXL（三倍做多），否则买入 SOXS（三倍做空），用全部余额买整数股，收盘价卖出。每次买入和卖出各扣 0.05% 的手续费和滑点。各规则的触发线都以 SOX 指数衡量。</span></div>
    <details class="rulebox"><summary><span class="en" lang="en">Rule details</span><span class="zh" lang="zh">规则说明</span></summary>
    <ul class="rules">
      <li><b>A</b> <span class="en" lang="en">Sell at the close.</span><span class="zh" lang="zh">收盘价卖出。</span></li>
      <li><b>B</b> <span class="en" lang="en">Sell as soon as the SOX's move on the day reaches twice the forecast, either way.</span><span class="zh" lang="zh">SOX 当日涨跌幅一旦达到预测值的两倍就卖出（止盈或止损）。</span></li>
      <li><b>1</b> <span class="en" lang="en">Baseline that ignores the forecast: SOXL if the pre-market is up, SOXS if down.</span><span class="zh" lang="zh">基准对照，不看预测：盘前涨买 SOXL，盘前跌买 SOXS。</span></li>
      <li><b>2</b> <span class="en" lang="en">Size by the forecast's confidence: high 100%, medium 50%, low 25% of the balance; the rest stays in cash.</span><span class="zh" lang="zh">按预测信心定仓位：高 100%、中 50%、低 25%，其余留现金。</span></li>
      <li><b>3</b> <span class="en" lang="en">Trade only if the forecast differs from the pre-market move by at least 0.5 points; otherwise stay in cash.</span><span class="zh" lang="zh">预测与盘前涨跌相差至少 0.5 个百分点才交易，否则空仓。</span></li>
      <li><b>4</b> <span class="en" lang="en">Sell once the SOX moves one daily standard deviation (last 20 days) from its open, either way.</span><span class="zh" lang="zh">SOX 相对开盘价涨跌达到 1 倍日波动率（近 20 天）就卖出。</span></li>
      <li><b>5</b> <span class="en" lang="en">Once the SOX is up 1% from the open in our favour, sell if half of the best gain is given back.</span><span class="zh" lang="zh">SOX 相对开盘价朝有利方向走出 1% 后启动保护，回吐一半最大涨幅就卖出。</span></li>
      <li><b>6</b> <span class="en" lang="en">Wait until 10:00: buy then only if the SOX has moved our way since the open; otherwise no trade.</span><span class="zh" lang="zh">等到 10:00，SOX 相对开盘价朝预测方向走才买入，否则当天不交易。</span></li>
    </ul></details>
    <div id="sim"></div>
    <div id="cmp"></div>
    <div class="legend" id="legend2" style="margin-top:14px"></div>
    <div class="chart" id="equity"></div>
    <details><summary><span class="en" lang="en">Daily detail</span><span class="zh" lang="zh">每日明细</span></summary><div id="trades"></div></details>
  </div>
  <footer>
    <span class="en" lang="en">Forecast written by Claude before the US open each trading day, from a web search of the factors that move chip stocks. Market data from Yahoo Finance, filled in automatically after the close. For reference only, not investment advice.</span>
    <span class="zh" lang="zh">每个美股交易日开盘前，由 Claude 搜索影响半导体股的各种因素后给出预测；行情数据来自 Yahoo Finance，收盘后自动更新。仅供参考，不构成投资建议。</span>
    <div class="meta" id="updated" style="margin-top:8px"></div>
  </footer>
</main>
<script type="application/json" id="data">__DATA__</script>
<script>
(function () {
  function get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  var t = get("dn-theme");
  if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
  var btns = document.querySelectorAll("#lang button");
  function pick(m) {
    document.body.className = "m-" + m;
    btns.forEach(function (b) { b.classList.toggle("on", b.dataset.m === m); });
  }
  btns.forEach(function (b) { b.onclick = function () { pick(b.dataset.m); set("dn-lang", b.dataset.m); }; });
  var saved = get("dn-lang");
  if (saved === "bi" || saved === "zh" || saved === "en") pick(saved);

  var D = JSON.parse(document.getElementById("data").textContent), rows = D.rows;
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function bi(en, zh) { return '<span class="en" lang="en">' + en + '</span><span class="zh" lang="zh">' + zh + "</span>"; }
  function pct(v) { return v == null ? "—" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(v === Math.round(v * 10) / 10 ? 1 : 2) + "%"; }
  function md(d) { var p = d.split("-"); return +p[1] + "/" + +p[2]; }
  function wk(d) { return new Date(d + "T12:00:00Z").getUTCDay(); }
  var WZ = "日一二三四五六", WE = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  function clock(isoStr) {
    if (!isoStr) return "";
    try { return new Date(isoStr).toLocaleTimeString("en-US", { timeZone: "America/Toronto", hour: "numeric", minute: "2-digit" }); }
    catch (e) { return isoStr.slice(11, 16) + " UTC"; }
  }
  function hit(r) { return r.a != null && r.a !== 0 && (r.a > 0) === (r.p > 0); }

  // --- Today's call ---
  var box = document.getElementById("today");
  if (!rows.length) {
    box.innerHTML = '<div class="empty blk">' + bi("The first forecast will appear before the next US market open.", "首个预测将在下一个美股交易日开盘前发布。") + "</div>";
  } else {
    var r = rows[rows.length - 1], p = r.d.split("-");
    var CF = { low: ["low", "低"], medium: ["medium", "中"], high: ["high", "高"] };
    var facts = (r.g != null && r.dr != null ? '<div><span class="label">' + bi("Gap", "缺口") + "</span> <b>" + pct(r.g) + "</b> + " +
      '<span class="label">' + bi("after the open", "开盘后") + "</span> <b>" + pct(r.dr) + "</b>" +
      (CF[r.cf] ? ' <span class="label">· ' + bi("confidence " + CF[r.cf][0], "信心" + CF[r.cf][1]) + "</span>" : "") + "</div>" : "") +
      (r.mo != null ? '<div><span class="label">' + bi("Statistical model at the call", "统计模型参考值") + "</span> <b>" + pct(r.mo) + "</b>" +
        (r.a != null ? ' <span class="label">(' + bi("error ", "误差 ") + Math.abs(r.mo - r.a).toFixed(2) + ")</span>" : "") + "</div>" : "") +
      '<div><span class="label">' + bi("SOXX pre-market at the call", "预测时 SOXX 盘前") + "</span> <b>" + pct(r.pre) + "</b>" +
      (r.preAt ? ' <span class="label">(' + clock(r.preAt) + ")</span>" : "") + "</div>";
    function bigNum(v) {
      return '<div class="big ' + (v > 0 ? "up" : "down") + '"><span class="arr">' + (v > 0 ? "▲" : "▼") + "</span>" + pct(v) + "</div>";
    }
    var actual = r.a != null ? bigNum(r.a) : '<div class="big wait">—</div>';
    var verdict = r.a != null
      ? '<div class="verdict">' + (hit(r) ? '<span class="ok">' + bi("✓ direction right", "✓ 方向正确") + "</span>" : '<span class="miss">' + bi("✗ direction wrong", "✗ 方向错误") + "</span>") +
        ' <span class="label">· ' + bi("error", "误差") + "</span> <b>" + Math.abs(r.p - r.a).toFixed(2) + "</b> " + bi("pts", "个百分点") + "</div>"
      : '<div class="verdict label">' + bi("The actual close fills in after the 4 PM close.", "实际收盘涨跌在美东 16:00 收盘后自动填入。") + "</div>";
    var f = (r.f || []).map(function (x) {
      var sym = x.dir === "up" ? "▲" : x.dir === "down" ? "▼" : "◆";
      return '<li><span class="dir ' + esc(x.dir) + '">' + sym + "</span><span>" + bi(esc(x.en), esc(x.zh)) + "</span></li>";
    }).join("");
    box.innerHTML =
      '<div class="label">' + bi("Forecast for " + WE[wk(r.d)] + ", " + md(r.d) + " · made " + clock(r.at) + " Toronto",
        p[1] * 1 + "月" + p[2] * 1 + "日 星期" + WZ[wk(r.d)] + " 的预测 · 多伦多时间 " + clock(r.at) + " 给出") + "</div>" +
      '<div class="duo"><div><div class="label">' + bi("Forecast", "预测") + "</div>" + bigNum(r.p) + "</div>" +
      '<div><div class="label">' + bi("Actual SOX close", "实际收盘") + "</div>" + actual + "</div></div>" +
      verdict + '<div class="facts">' + facts + "</div>" +
      (r.s ? '<p class="why">' + bi(esc(r.s.en), esc(r.s.zh)) + "</p>" : "") +
      (f ? "<details><summary>" + bi("Factors", "影响因素") + '</summary><ul class="factors">' + f + "</ul>" +
        (r.rk ? '<p class="why label blk">' + bi("What would prove it wrong: " + esc(r.rk.en), "什么情况会证明预测错了：" + esc(r.rk.zh)) + "</p>" : "") +
        "</details>" : "");
  }

  // --- What others say about the day (gathered by the routine, with sources) ---
  if (rows.length && rows[rows.length - 1].v && rows[rows.length - 1].v.length) {
    var vr = rows[rows.length - 1], vb = document.getElementById("views");
    var ARROW = '<svg viewBox="0 0 24 24"><path d="M7 17 17 7M9 7h8v8" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    vb.innerHTML = '<div class="label blk">' + bi("What others are saying about chip stocks today", "各方观点：今天的芯片股怎么看") + "</div>" +
      '<ul class="views">' + vr.v.map(function (x) {
        var sym = x.stance === "up" ? "▲" : x.stance === "down" ? "▼" : "◆";
        var who = x.who ? esc(x.who) + " · " : "";
        return '<li><span class="dir ' + esc(x.stance) + '">' + sym + "</span><div>" +
          '<div class="who">' + who + esc(x.source) + "</div>" +
          '<div class="txt">' + bi(esc(x.en), esc(x.zh)) + "</div>" +
          '<a class="src" href="' + esc(x.url) + '" target="_blank" rel="noopener">' + bi("Read the source", "查看原文") + ARROW + "</a></div></li>";
      }).join("") + "</ul>" +
      '<p class="note label blk">' + bi("Summaries by Claude from the morning's search; open the source for the full view. ▲ bullish ▼ bearish ◆ mixed.",
        "观点摘要由 Claude 根据当天早上的搜索整理，请以原文为准。▲ 看涨 ▼ 看跌 ◆ 中性/分歧。") + "</p>";
    vb.hidden = false;
  }

  // --- Stats ---
  var done = rows.filter(function (r) { return r.a != null; });
  if (done.length) {
    var h = done.filter(hit).length, mae = done.reduce(function (s, r) { return s + Math.abs(r.p - r.a); }, 0) / done.length;
    document.getElementById("stats").innerHTML =
      "<span><b>" + h + "/" + done.length + "</b>" + bi("direction right", "方向命中") + "</span>" +
      "<span><b>" + Math.round(h / done.length * 100) + "%</b>" + bi("hit rate", "命中率") + "</span>" +
      "<span><b>" + mae.toFixed(2) + "</b>" + bi("avg error (pts)", "平均误差（百分点）") + "</span>";
    // Naive baseline: "forecast = SOXX pre-market move". Beating it is the bar.
    var base = done.filter(function (r) { return r.pre != null; });
    if (base.length) {
      var bmae = base.reduce(function (s, r) { return s + Math.abs(r.pre - r.a); }, 0) / base.length;
      var cmae = base.reduce(function (s, r) { return s + Math.abs(r.p - r.a); }, 0) / base.length;
      var side = base.filter(function (r) { return (r.p > r.pre) === (r.a > r.pre); }).length;
      document.getElementById("stats").innerHTML +=
        "<span><b>" + bmae.toFixed(2) + "</b>" + bi("baseline error (forecast = pre-market)", "基准误差（直接用盘前涨跌）") +
        " " + (cmae < bmae ? '<span class="ok">' + bi("beating it", "跑赢基准") + "</span>" : '<span class="miss">' + bi("not beating it yet", "尚未跑赢基准") + "</span>") + "</span>" +
        "<span><b>" + side + "/" + base.length + "</b>" + bi("trade side right", "交易方向正确") + "</span>";
    }
    var withMo = done.filter(function (r) { return r.mo != null; });
    if (withMo.length) {
      var mmae = withMo.reduce(function (s, r) { return s + Math.abs(r.mo - r.a); }, 0) / withMo.length;
      var cm = withMo.reduce(function (s, r) { return s + Math.abs(r.p - r.a); }, 0) / withMo.length;
      document.getElementById("stats").innerHTML +=
        "<span><b>" + mmae.toFixed(2) + "</b>" + bi("statistical model's error", "统计模型误差") + " " +
        (cm < mmae ? '<span class="ok">' + bi("Claude ahead", "Claude 更准") + "</span>" : '<span class="miss">' + bi("model ahead", "模型更准") + "</span>") + "</span>";
    }
  }

  // --- Chart: grouped bars per day, forecast vs actual, ring = SOXX pre-market at the call ---
  var el = document.getElementById("chart");
  document.getElementById("legend").innerHTML =
    '<span><i style="background:var(--pred)"></i>' + bi("Forecast", "预测") + "</span>" +
    '<span><i style="background:var(--model)"></i>' + bi("Statistical model", "统计模型") + "</span>" +
    '<span><i style="background:var(--act)"></i>' + bi("Actual SOX", "实际 SOX") + "</span>" +
    '<span><i class="ring"></i>' + bi("SOXX pre-market at the call", "预测时 SOXX 盘前") + "</span>";
  var tip = document.createElement("div"); tip.className = "tip";

  function draw() {
    if (!rows.length) { el.innerHTML = '<div class="empty blk">' + bi("No data yet.", "暂无数据。") + "</div>"; return; }
    var W = el.clientWidth || 600, H = Math.max(220, Math.min(320, W * 0.5));
    var maxN = Math.max(5, Math.floor((W - 40) / 26)), show = rows.slice(-Math.min(maxN, 30));
    var m = { l: 40, r: 6, t: 10, b: 26 }, iw = W - m.l - m.r, ih = H - m.t - m.b;
    var top = 0.5;
    show.forEach(function (r) { [r.p, r.a, r.pre, r.mo].forEach(function (v) { if (v != null) top = Math.max(top, Math.abs(v)); }); });
    var steps = [0.5, 1, 2, 2.5, 5, 10], step = steps.find(function (s) { return top / s <= 4; }) || 10;
    top = Math.ceil(top / step) * step;
    function y(v) { return m.t + ih / 2 - v / top * ih / 2; }
    var gw = iw / show.length, bw = Math.max(3, Math.min(14, (gw - 10) / 3));
    var s = '<svg viewBox="0 0 ' + W + " " + H + '" height="' + H + '" role="img" aria-label="Forecast vs actual SOX daily change">';
    for (var v = -top; v <= top + 1e-9; v += step) {
      s += '<line x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="' + (Math.abs(v) < 1e-9 ? "var(--muted)" : "var(--grid)") + '" stroke-width="1"/>' +
        '<text x="' + (m.l - 6) + '" y="' + (y(v) + 4) + '" text-anchor="end">' + (v > 0 ? "+" : "") + (+v.toFixed(1)) + "%</text>";
    }
    function bar(x, v, color) {
      if (v == null) return "";
      var y0 = y(0), y1 = y(v), hgt = Math.abs(y1 - y0), rr = Math.min(4, hgt, bw / 2);
      if (hgt < 0.5) return '<line x1="' + x + '" x2="' + (x + bw) + '" y1="' + y0 + '" y2="' + y0 + '" stroke="' + color + '" stroke-width="2"/>';
      var up = v > 0, e = up ? y1 : y1;   // rounded data end, square baseline
      var d = up
        ? "M" + x + "," + y0 + "V" + (e + rr) + "Q" + x + "," + e + " " + (x + rr) + "," + e + "H" + (x + bw - rr) + "Q" + (x + bw) + "," + e + " " + (x + bw) + "," + (e + rr) + "V" + y0 + "Z"
        : "M" + x + "," + y0 + "V" + (e - rr) + "Q" + x + "," + e + " " + (x + rr) + "," + e + "H" + (x + bw - rr) + "Q" + (x + bw) + "," + e + " " + (x + bw) + "," + (e - rr) + "V" + y0 + "Z";
      return '<path d="' + d + '" fill="' + color + '"/>';
    }
    var every = Math.ceil(show.length / Math.max(1, Math.floor(iw / 44)));
    show.forEach(function (r, i) {
      var cx = m.l + gw * i + gw / 2;
      s += bar(cx - bw * 1.5 - 2, r.p, "var(--pred)") + bar(cx - bw / 2, r.mo, "var(--model)") + bar(cx + bw / 2 + 2, r.a, "var(--act)");
      if (r.pre != null) s += '<circle cx="' + cx + '" cy="' + y(r.pre) + '" r="4.5" fill="var(--paper)" stroke="var(--ink)" stroke-width="2"/>';
      if ((show.length - 1 - i) % every === 0) s += '<text x="' + cx + '" y="' + (H - 6) + '" text-anchor="middle">' + md(r.d) + "</text>";
      s += '<rect class="hit" data-i="' + i + '" x="' + (m.l + gw * i) + '" y="' + m.t + '" width="' + gw + '" height="' + ih + '" fill="transparent"/>';
    });
    el.innerHTML = s + "</svg>";
    el.appendChild(tip);
    el.querySelectorAll("rect.hit").forEach(function (rc) {
      function show_(ev) {
        var r = show[+rc.dataset.i];
        tip.innerHTML = "<b>" + r.d + "</b><br>" +
          '<i style="background:var(--pred)"></i>' + bi("Forecast ", "预测 ") + pct(r.p) + "<br>" +
          '<i style="background:var(--model)"></i>' + bi("Model ", "模型 ") + pct(r.mo) + "<br>" +
          '<i style="background:var(--act)"></i>' + bi("Actual SOX ", "实际 SOX ") + pct(r.a) + "<br>" +
          bi("SOXX pre-market ", "SOXX 盘前 ") + pct(r.pre) +
          (r.a != null ? "<br>" + bi("Error ", "误差 ") + Math.abs(r.p - r.a).toFixed(2) + (hit(r) ? " ✓" : " ✗") : "");
        tip.style.display = "block";
        var b = el.getBoundingClientRect(), x = (ev.touches ? ev.touches[0].clientX : ev.clientX) - b.left;
        var tw = tip.offsetWidth;
        tip.style.left = Math.max(0, Math.min(b.width - tw, x - tw / 2)) + "px";
        tip.style.top = Math.max(0, (ev.touches ? ev.touches[0].clientY : ev.clientY) - b.top - tip.offsetHeight - 14) + "px";
      }
      rc.addEventListener("mousemove", show_);
      rc.addEventListener("touchstart", show_, { passive: true });
      rc.addEventListener("mouseleave", function () { tip.style.display = "none"; });
    });
  }
  draw();
  var rt; window.addEventListener("resize", function () { clearTimeout(rt); rt = setTimeout(draw, 120); });

  // --- Paper trading: 8 rules, $10,000 each, 0.05% cost per side ---
  var START = 10000, COST = 0.0005;
  function usd(v) { return "$" + v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
  function sgn(v, f) { return (v > 0 ? "+" : v < 0 ? "−" : "") + f(Math.abs(v)); }
  function p2(v) { return v.toFixed(2) + "%"; }
  var RULES = [
    ["A", "Sell at the close", "收盘卖出"],
    ["B", "Exit at 2x the forecast", "预测两倍止盈止损"],
    ["1", "Baseline: follow the pre-market", "基准：只跟盘前方向"],
    ["2", "Size by confidence", "按信心定仓位"],
    ["3", "Only clear calls (≥0.5 pts)", "只做把握大的日子"],
    ["4", "Exit at 1 daily std dev", "波动率止盈止损"],
    ["5", "Trailing take-profit", "移动止盈"],
    ["6", "Buy at 10:00 if confirmed", "10:00 确认后进场"]
  ];
  var days = rows.filter(function (r) { return r.sim; });
  var res = RULES.map(function (R) {
    var cash = START, peak = START, mdd = 0, n = 0, wins = 0, skips = 0, curve = [START], log = [];
    days.forEach(function (r) {
      var s = r.sim[R[0]];
      if (!s || s.skip) { if (s) skips++; curve.push(cash); log.push({ d: r.d, s: s, pl: 0 }); return; }
      var sh = Math.floor(cash * (s.frac || 1) / (s.buy * (1 + COST)));
      var pl = sh * s.sell * (1 - COST) - sh * s.buy * (1 + COST);
      cash += pl; n++; if (pl > 0) wins++;
      peak = Math.max(peak, cash); mdd = Math.max(mdd, (peak - cash) / peak * 100);
      curve.push(cash);
      log.push({ d: r.d, s: s, sh: sh, pl: pl, pct: sh ? pl / (sh * s.buy * (1 + COST)) * 100 : 0 });
    });
    return { R: R, cash: cash, ret: (cash / START - 1) * 100, n: n, wins: wins, skips: skips, mdd: mdd, curve: curve, log: log };
  });
  var best = res.reduce(function (a, b) { return b.cash > a.cash ? b : a; });
  var sel = res[1];   // the chart compares rule A with the selected row (B to start)

  var last = rows.length ? rows[rows.length - 1] : null;
  document.getElementById("sim").innerHTML = last && last.ent && !last.sim
    ? '<div class="pos">' + bi("Today: " + last.ent.sym + " at the open, " + usd(last.ent.buy) + " (rules A, B, 2–5). Every rule's result is worked out after the 4 PM close.",
        "今天：开盘价 " + usd(last.ent.buy) + " 买入 " + last.ent.sym + "（规则A、B、2–5），各规则的结果在美东 16:00 收盘后计算。") + "</div>"
    : (!days.length ? '<div class="pos label blk">' + bi("The first trades are placed at the open after the next forecast.", "第一笔交易将在下一个预测后的开盘时买入。") + "</div>" : "");

  function drawTable() {
    if (!days.length) { document.getElementById("cmp").innerHTML = ""; return; }
    document.getElementById("cmp").innerHTML = '<div class="tablewrap"><table class="cmp"><thead><tr><th>' + bi("Rule", "规则") + "</th><th>" + bi("Balance", "余额") +
      "</th><th>" + bi("Return", "收益率") + "</th><th>" + bi("Trades", "交易") + "</th><th>" + bi("Win rate", "胜率") + "</th><th>" + bi("Max drawdown", "最大回撤") +
      "</th><th>" + bi("Last day", "最近一天") + "</th></tr></thead><tbody>" + res.map(function (x, i) {
        var lg = x.log[x.log.length - 1], lastCell = !lg.s ? "—" : lg.s.skip ? '<span class="label">' + bi("no trade", "未交易") + "</span>"
          : '<span class="' + (lg.pl > 0 ? "ok" : "miss") + '">' + sgn(lg.pct, p2) + "</span>";
        return '<tr data-i="' + i + '" class="' + (x === sel ? "sel " : "") + (x === best ? "best" : "") + '"><td><b>' + x.R[0] + "</b> " + bi(x.R[1], x.R[2]) + (x === best ? ' <span class="crown" title="Best balance 余额最高">★</span>' : "") +
          "</td><td><b>" + usd(x.cash) + '</b></td><td class="' + (x.ret > 0 ? "ok" : x.ret < 0 ? "miss" : "") + '">' + sgn(x.ret, p2) +
          "</td><td>" + x.n + (x.skips ? ' <span class="label">(' + bi(x.skips + " skipped", "空仓 " + x.skips) + ")</span>" : "") +
          "</td><td>" + (x.n ? Math.round(x.wins / x.n * 100) + "%" : "—") + "</td><td>" + (x.n ? (x.mdd >= 0.005 ? "−" : "") + x.mdd.toFixed(2) + "%" : "—") + "</td><td>" + lastCell + "</td></tr>";
      }).join("") + "</tbody></table></div>";
    document.querySelectorAll("table.cmp tbody tr").forEach(function (tr) {
      tr.onclick = function () { sel = res[+tr.dataset.i]; drawTable(); drawEquity(); };
    });
  }

  var eq = document.getElementById("equity"), tip2 = document.createElement("div"); tip2.className = "tip";
  function drawEquity() {
    var n = days.length;
    if (!n) { eq.innerHTML = ""; document.getElementById("legend2").innerHTML = ""; return; }
    var focus = [res[0]].concat(sel === res[0] ? [] : [sel]);
    var COL = function (x) { return x === res[0] ? "var(--pred)" : "var(--act)"; };
    document.getElementById("legend2").innerHTML = focus.map(function (x) {
      return '<span><i style="background:' + COL(x) + '"></i>' + x.R[0] + " " + bi(x.R[1], x.R[2]) + "</span>";
    }).join("") + '<span><i style="background:var(--muted);opacity:.4"></i>' + bi("Other rules", "其他规则") + "</span>" +
      '<span class="label">' + bi("Click a row in the table to compare it with A.", "点表格中的一行，与规则A对比。") + "</span>";
    var all = [].concat.apply([], res.map(function (x) { return x.curve; }));
    var W = eq.clientWidth || 600, H = Math.max(200, Math.min(280, W * 0.45));
    var m = { l: 62, r: 12, t: 12, b: 24 }, iw = W - m.l - m.r, ih = H - m.t - m.b;
    var lo = Math.min.apply(null, all), hi = Math.max.apply(null, all);
    var pad = Math.max((hi - lo) * 0.15, START * 0.02); lo -= pad; hi += pad;
    function x(i) { return m.l + iw * i / n; }
    function y(v) { return m.t + ih - (v - lo) / (hi - lo) * ih; }
    function line(c, col, w, op) {
      return '<polyline fill="none" stroke="' + col + '" stroke-width="' + w + '" stroke-linejoin="round" opacity="' + op + '" points="' +
        c.map(function (v, i) { return x(i) + "," + y(v); }).join(" ") + '"/>';
    }
    var s = '<svg viewBox="0 0 ' + W + " " + H + '" height="' + H + '" role="img" aria-label="Paper trading balance by rule">';
    for (var k = 0; k <= 3; k++) {
      var v = lo + (hi - lo) * k / 3;
      s += '<line x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="var(--grid)"/>' +
        '<text x="' + (m.l - 6) + '" y="' + (y(v) + 4) + '" text-anchor="end">$' + Math.round(v).toLocaleString("en-US") + "</text>";
    }
    s += '<line x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + y(START) + '" y2="' + y(START) + '" stroke="var(--muted)" stroke-dasharray="4 4"/>';
    res.forEach(function (r) { if (focus.indexOf(r) < 0) s += line(r.curve, "var(--muted)", 1.5, 0.35); });
    focus.slice().reverse().forEach(function (r) {
      s += line(r.curve, COL(r), 2.5, 1);
      r.curve.forEach(function (v, i) { s += '<circle cx="' + x(i) + '" cy="' + y(v) + '" r="4" fill="' + COL(r) + '" stroke="var(--paper)" stroke-width="2"/>'; });
    });
    var every = Math.ceil((n + 1) / Math.max(1, Math.floor(iw / 50)));
    for (var i = 0; i <= n; i++) {
      if ((n - i) % every === 0) s += '<text x="' + x(i) + '" y="' + (H - 6) + '" text-anchor="middle">' + (i ? md(days[i - 1].d) : "$10k") + "</text>";
      s += '<rect class="hit" data-i="' + i + '" x="' + (x(i) - iw / n / 2) + '" y="' + m.t + '" width="' + (iw / n) + '" height="' + ih + '" fill="transparent"/>';
    }
    eq.innerHTML = s + "</svg>";
    eq.appendChild(tip2);
    eq.querySelectorAll("rect.hit").forEach(function (rc) {
      function on(ev) {
        var i = +rc.dataset.i;
        tip2.innerHTML = "<b>" + (i ? days[i - 1].d : bi("Start", "起点")) + "</b>" + res.map(function (r) {
          var hl = focus.indexOf(r) >= 0;
          return "<br>" + (hl ? '<i style="background:' + COL(r) + '"></i>' : '<i style="background:var(--muted);opacity:.4"></i>') + (hl ? "<b>" : "") + r.R[0] + " " + usd(r.curve[i]) + (hl ? "</b>" : "");
        }).join("");
        tip2.style.display = "block";
        var b = eq.getBoundingClientRect(), cx = (ev.touches ? ev.touches[0].clientX : ev.clientX) - b.left, tw = tip2.offsetWidth;
        tip2.style.left = Math.max(0, Math.min(b.width - tw, cx - tw / 2)) + "px";
        tip2.style.top = "0px";
      }
      rc.addEventListener("mousemove", on);
      rc.addEventListener("touchstart", on, { passive: true });
      rc.addEventListener("mouseleave", function () { tip2.style.display = "none"; });
    });
  }
  drawTable();
  drawEquity();
  window.addEventListener("resize", function () { clearTimeout(rt); rt = setTimeout(function () { draw(); drawEquity(); }, 120); });

  // Per-day detail: what each rule did.
  if (days.length) {
    var WHY = { tp: ["take profit", "止盈"], sl: ["stop loss", "止损"], close: ["close", "收盘"], trail: ["trailing", "移动止盈"] };
    document.getElementById("trades").innerHTML = days.slice(-10).reverse().map(function (r) {
      return "<h4>" + r.d + "</h4>" + '<div class="tablewrap"><table><thead><tr><th>' + bi("Rule", "规则") + "</th><th>" + bi("Buy", "买入") + "</th><th>" + bi("Sell", "卖出") +
        "</th><th>" + bi("Size", "仓位") + "</th><th>" + bi("Result (after costs)", "盈亏（扣成本）") + "</th></tr></thead><tbody>" + res.map(function (x) {
          var lg = x.log.filter(function (l) { return l.d === r.d; })[0], s = lg && lg.s;
          if (!s) return "";
          if (s.skip) return "<tr><td><b>" + x.R[0] + '</b></td><td colspan="4" class="label">' + bi(s.skip === "filter" ? "No trade: expected move after the open under 0.5 pts" : "No trade: not moving our way at 10:00",
            s.skip === "filter" ? "未交易：预计开盘后涨跌不足 0.5 个百分点" : "未交易：10:00 时走势与预测方向不一致") + "</td></tr>";
          var inAt = s.in_at ? " " + clock(s.in_at) : "", outAt = s.at ? " " + clock(s.at) : "";
          return "<tr><td><b>" + x.R[0] + "</b></td><td>" + s.sym + " " + usd(s.buy) + '<br><span class="label">' + bi((s.in_at ? "" : "open") + inAt, (s.in_at ? "" : "开盘") + inAt) + "</span></td><td>" +
            usd(s.sell) + '<br><span class="label">' + bi(WHY[s.why][0] + outAt, WHY[s.why][1] + outAt) + "</span></td><td>" + Math.round((s.frac || 1) * 100) + "%</td>" +
            '<td class="' + (lg.pl > 0 ? "ok" : "miss") + '">' + sgn(lg.pl, usd) + "<br>" + sgn(lg.pct, p2) + "</td></tr>";
        }).join("") + "</tbody></table></div>";
    }).join("");
  }

  // --- Table ---
  if (rows.length) {
    document.getElementById("table").innerHTML = "<table><thead><tr><th>" + bi("Date", "日期") + "</th><th>" + bi("Forecast", "预测") +
      "</th><th>" + bi("Model", "模型") + "</th><th>" + bi("Pre-mkt SOXX", "盘前 SOXX") + "</th><th>" + bi("Actual SOX", "实际 SOX") + "</th><th>" + bi("Error", "误差") + "</th></tr></thead><tbody>" +
      rows.slice().reverse().map(function (r) {
        return "<tr><td>" + r.d + "</td><td>" + pct(r.p) + "</td><td>" + pct(r.mo) + "</td><td>" + pct(r.pre) + "</td><td>" + pct(r.a) + "</td><td>" +
          (r.a == null ? "—" : '<span class="' + (hit(r) ? "ok" : "miss") + '">' + Math.abs(r.p - r.a).toFixed(2) + (hit(r) ? " ✓" : " ✗") + "</span>") + "</td></tr>";
      }).join("") + "</tbody></table>";
  }
  document.getElementById("updated").innerHTML = bi("Updated " + new Date(D.updated).toLocaleString("en-US", { timeZone: "America/Toronto", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) + " (Toronto)",
    "更新于多伦多时间 " + new Date(D.updated).toLocaleString("zh-CN", { timeZone: "America/Toronto", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }));
})();
</script>
</body>
</html>
"""


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "check":
        errs = check(sys.argv[2])
        for e in errs:
            print("ERROR", e)
        print("OK" if not errs else f"{len(errs)} error(s)")
        raise SystemExit(1 if errs else 0)
    preds = load_predictions()
    market = update_market(preds)
    OUT.write_text(render(preds, market, datetime.now(timezone.utc)), encoding="utf-8")
    print("wrote", OUT, len(preds), "predictions")


if __name__ == "__main__":
    main()
