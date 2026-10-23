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


def rule_b(sym, date, predict, sox_prev):
    """Rule B exit: sell once the SOX's move on the day reaches twice the forecast,
    either way (take profit or stop loss); otherwise hold to the close.

    Returns (price, time, why) with why = "tp", "sl" or "close", or None when
    the 1-minute bars are no longer available.
    """
    band = 2 * abs(predict)
    sox = session_bars("^SOX", date, "regular")
    etf = session_bars(sym, date, "regular")
    if not sox or not etf:
        return None
    for ts, c in sox:
        chg = (c / sox_prev - 1) * 100
        if abs(chg) >= band:
            px = [e for e in etf if e[0] <= ts] or etf[:1]
            why = "tp" if (chg > 0) == (sym == "SOXL") else "sl"
            return px[-1][1], ts, why
    return None


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
    sox, sox_final = daily("^SOX")
    soxx, soxx_final = daily("SOXX")
    sox_chg, soxx_chg = changes(sox, sox_final), changes(soxx, soxx_final)
    etf = {}   # SOXL/SOXS daily closes, fetched once when a trade needs them
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
        # Paper trade: forecast above the pre-market move (gain still to come) ->
        # buy SOXL (3x bull) at the open, otherwise SOXS (3x bear). Rule A sells
        # at the close; rule B sells earlier if the SOX's move on the day reaches
        # twice the forecast either way, else at the close.
        t = m.get("trade")
        if t and t.get("entry") != "open":   # older rule (bought pre-market): redo
            t = m["trade"] = None
        if "pre" in m and not t:
            t = m["trade"] = {"sym": "SOXL" if p["predict"] > m["pre"] else "SOXS", "entry": "open"}
        if t:
            sym = t["sym"]
            if sym not in etf:
                opens = {}
                etf[sym] = daily(sym, opens) + (opens,)
            closes, final, opens = etf[sym]
            if date in opens:
                t["buy"] = round(opens[date], 4)
            if date in final:
                # Re-read on every run so a later run picks up the settled close.
                t["a_sell"] = round(closes[date], 4)
                if "b_why" not in t:
                    prev = [d for d in sorted(sox) if d < date]
                    try:
                        got = rule_b(sym, date, p["predict"], sox[prev[-1]]) if prev else None
                    except Exception as e:
                        got = None
                        print(date, "rule B lookup failed:", e)
                    if got:
                        t.update(b_sell=round(got[0], 4), b_at=iso(got[1]), b_why=got[2])
                    elif session_bars(sym, date, "regular"):
                        t.update(b_why="close")
                if t.get("b_why") == "close":
                    t["b_sell"] = t["a_sell"]
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
            "s": p.get("summary"), "f": p.get("factors", []), "t": m.get("trade"),
            "g": p.get("gap_est"), "dr": p.get("drift_est"), "cf": p.get("confidence"), "rk": p.get("risk"),
            "v": p.get("views", []),
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
  --pred: #2a78d6; --act: #eb6834; --up: #12805c; --down: #c8372d;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0f1719; --paper: #162123; --ink: #e4eeee; --muted: #93a5a8; --line: #24363a; --grid: #1e2d30;
    --accent: #3cc8b4; --accent-soft: #123430; --accent-ink: #062320;
    --pred: #3987e5; --act: #d95926; --up: #3fbf8f; --down: #ff7a6e; color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #0f1719; --paper: #162123; --ink: #e4eeee; --muted: #93a5a8; --line: #24363a; --grid: #1e2d30;
  --accent: #3cc8b4; --accent-soft: #123430; --accent-ink: #062320;
  --pred: #3987e5; --act: #d95926; --up: #3fbf8f; --down: #ff7a6e; color-scheme: dark;
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
    <div class="label blk"><span class="en" lang="en">Paper trading: two ways to sell, $10,000 each</span><span class="zh" lang="zh">模拟交易：两种卖出规则对比（各 $10,000 起始）</span></div>
    <div class="rule blk"><span class="en" lang="en">Each trading day, if the forecast is above the SOXX pre-market move at the call (gain still expected), buy SOXL (3x bull) at the open, otherwise SOXS (3x bear); whole shares with the whole balance, no fees. <b>Rule A</b>: sell at the close. <b>Rule B</b>: sell as soon as the SOX's move on the day reaches twice the forecast, either way (take profit or stop loss); otherwise at the close.</span><span class="zh" lang="zh">每个交易日：预测涨幅高于预测时的 SOXX 盘前涨幅（还有上涨空间）就按开盘价买入 SOXL（三倍做多），否则买入 SOXS（三倍做空），用全部余额买整数股，不计手续费。<b>规则A</b>：收盘价卖出。<b>规则B</b>：盘中 SOX 当日涨幅或跌幅一旦达到预测值的两倍就卖出（止盈或止损），没出现就按收盘价卖出。</span></div>
    <div id="sim"></div>
    <div class="legend" id="legend2" style="margin-top:14px"></div>
    <div class="chart" id="equity"></div>
    <details><summary><span class="en" lang="en">Trades</span><span class="zh" lang="zh">交易记录</span></summary><div id="trades"></div></details>
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
  }

  // --- Chart: grouped bars per day, forecast vs actual, ring = SOXX pre-market at the call ---
  var el = document.getElementById("chart");
  document.getElementById("legend").innerHTML =
    '<span><i style="background:var(--pred)"></i>' + bi("Forecast", "预测") + "</span>" +
    '<span><i style="background:var(--act)"></i>' + bi("Actual SOX", "实际 SOX") + "</span>" +
    '<span><i class="ring"></i>' + bi("SOXX pre-market at the call", "预测时 SOXX 盘前") + "</span>";
  var tip = document.createElement("div"); tip.className = "tip";

  function draw() {
    if (!rows.length) { el.innerHTML = '<div class="empty blk">' + bi("No data yet.", "暂无数据。") + "</div>"; return; }
    var W = el.clientWidth || 600, H = Math.max(220, Math.min(320, W * 0.5));
    var maxN = Math.max(5, Math.floor((W - 40) / 26)), show = rows.slice(-Math.min(maxN, 30));
    var m = { l: 40, r: 6, t: 10, b: 26 }, iw = W - m.l - m.r, ih = H - m.t - m.b;
    var top = 0.5;
    show.forEach(function (r) { [r.p, r.a, r.pre].forEach(function (v) { if (v != null) top = Math.max(top, Math.abs(v)); }); });
    var steps = [0.5, 1, 2, 2.5, 5, 10], step = steps.find(function (s) { return top / s <= 4; }) || 10;
    top = Math.ceil(top / step) * step;
    function y(v) { return m.t + ih / 2 - v / top * ih / 2; }
    var gw = iw / show.length, bw = Math.max(4, Math.min(18, (gw - 8) / 2));
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
      s += bar(cx - bw - 1, r.p, "var(--pred)") + bar(cx + 1, r.a, "var(--act)");
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

  // --- Paper trading: rule A (sell at the close) vs rule B (sell at 2x the forecast) ---
  var START = 10000;
  function usd(v) { return "$" + v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
  function sgn(v, f) { return (v > 0 ? "+" : v < 0 ? "−" : "") + f(Math.abs(v)); }
  function p2(v) { return v.toFixed(2) + "%"; }
  function simulate(rule) {
    var cash = START, trades = [], open = null;
    rows.forEach(function (r) {
      var t = r.t;
      if (!t || !t.buy || t.entry !== "open") return;
      var sh = Math.floor(cash / t.buy);
      // Rule B falls back to the close if its minute data was never recorded.
      var sell = rule === "A" ? t.a_sell : (t.b_sell != null ? t.b_sell : t.a_sell);
      if (sell == null) { open = { r: r, t: t, sh: sh }; return; }
      var pl = sh * (sell - t.buy);
      cash += pl;
      trades.push({ d: r.d, sym: t.sym, buy: t.buy, sell: sell, sh: sh, pl: pl, pct: (sell / t.buy - 1) * 100, bal: cash,
        why: rule === "A" ? "close" : (t.b_why || "close"), at: rule === "A" ? null : t.b_at });
    });
    return { cash: cash, trades: trades, open: open };
  }
  var SA = simulate("A"), SB = simulate("B");
  var RULES = [["A", SA, "var(--pred)", "Rule A · sell at the close", "规则A · 收盘卖出"],
               ["B", SB, "var(--act)", "Rule B · sell at 2x the forecast", "规则B · 两倍止盈止损"]];
  var simEl = document.getElementById("sim");
  simEl.innerHTML = '<div class="duo2">' + RULES.map(function (R) {
    var S = R[1], ret = (S.cash / START - 1) * 100, wins = S.trades.filter(function (x) { return x.pl > 0; }).length;
    return "<div>" + '<div class="label"><span class="tag" style="background:' + R[2] + '"></span>' + bi(R[3], R[4]) + "</div>" +
      '<div class="bal">' + usd(S.cash) + '<small class="' + (ret > 0 ? "ok" : ret < 0 ? "miss" : "") + '">' + sgn(ret, p2) + "</small></div>" +
      (S.trades.length ? '<div class="stats"><span><b>' + S.trades.length + "</b>" + bi("trades", "笔") + "</span><span><b>" + wins + "/" + S.trades.length + "</b>" + bi("winning", "盈利") + "</span></div>" : "") +
      "</div>";
  }).join("") + "</div>" +
    (SA.open ? '<div class="pos">' + bi(
      "Today: bought <b>" + SA.open.t.sym + "</b> at the open, <b>" + usd(SA.open.t.buy) + "</b> (A: " + SA.open.sh + " shares, B: " + (SB.open ? SB.open.sh : "—") + "). Results after the close.",
      "今天：开盘价 <b>" + usd(SA.open.t.buy) + "</b> 买入 <b>" + SA.open.t.sym + "</b>（规则A " + SA.open.sh + " 股，规则B " + (SB.open ? SB.open.sh : "—") + " 股），收盘后出结果。") + "</div>"
    : (!SA.trades.length ? '<div class="pos label blk">' + bi("The first trade is placed at the open after the next forecast.", "第一笔交易将在下一个预测后的开盘时买入。") + "</div>" : ""));

  document.getElementById("legend2").innerHTML = RULES.map(function (R) {
    return '<span><i style="background:' + R[2] + '"></i>' + bi(R[3], R[4]) + "</span>";
  }).join("") + '<span><i style="background:none;border-top:2px dashed var(--muted);border-radius:0;height:0;vertical-align:3px"></i>' + bi("$10,000 start", "本金 $10,000") + "</span>";

  var eq = document.getElementById("equity"), tip2 = document.createElement("div"); tip2.className = "tip";
  function drawEquity() {
    var n = SA.trades.length;
    if (!n) { eq.innerHTML = ""; return; }
    var curves = RULES.map(function (R) { return [START].concat(R[1].trades.map(function (x) { return x.bal; })); });
    var all = curves[0].concat(curves[1]);
    var W = eq.clientWidth || 600, H = Math.max(200, Math.min(280, W * 0.45));
    var m = { l: 62, r: 12, t: 12, b: 24 }, iw = W - m.l - m.r, ih = H - m.t - m.b;
    var lo = Math.min.apply(null, all), hi = Math.max.apply(null, all);
    var pad = Math.max((hi - lo) * 0.15, START * 0.02); lo -= pad; hi += pad;
    function x(i) { return m.l + iw * i / n; }
    function y(v) { return m.t + ih - (v - lo) / (hi - lo) * ih; }
    var s = '<svg viewBox="0 0 ' + W + " " + H + '" height="' + H + '" role="img" aria-label="Paper trading balance, rule A vs rule B">';
    for (var k = 0; k <= 3; k++) {
      var v = lo + (hi - lo) * k / 3;
      s += '<line x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="var(--grid)"/>' +
        '<text x="' + (m.l - 6) + '" y="' + (y(v) + 4) + '" text-anchor="end">$' + Math.round(v).toLocaleString("en-US") + "</text>";
    }
    s += '<line x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + y(START) + '" y2="' + y(START) + '" stroke="var(--muted)" stroke-dasharray="4 4"/>';
    RULES.forEach(function (R, j) {
      s += '<polyline fill="none" stroke="' + R[2] + '" stroke-width="2" stroke-linejoin="round" points="' +
        curves[j].map(function (v, i) { return x(i) + "," + y(v); }).join(" ") + '"/>';
      curves[j].forEach(function (v, i) {
        s += '<circle cx="' + x(i) + '" cy="' + y(v) + '" r="4" fill="' + R[2] + '" stroke="var(--paper)" stroke-width="2"/>';
      });
    });
    var every = Math.ceil((n + 1) / Math.max(1, Math.floor(iw / 50)));
    for (var i = 0; i <= n; i++) {
      if ((n - i) % every === 0) s += '<text x="' + x(i) + '" y="' + (H - 6) + '" text-anchor="middle">' + (i ? md(SA.trades[i - 1].d) : "$10k") + "</text>";
      var w = iw / n;
      s += '<rect class="hit" data-i="' + i + '" x="' + (x(i) - w / 2) + '" y="' + m.t + '" width="' + w + '" height="' + ih + '" fill="transparent"/>';
    }
    eq.innerHTML = s + "</svg>";
    eq.appendChild(tip2);
    eq.querySelectorAll("rect.hit").forEach(function (rc) {
      function on(ev) {
        var i = +rc.dataset.i;
        tip2.innerHTML = "<b>" + (i ? SA.trades[i - 1].d + " · " + SA.trades[i - 1].sym : bi("Start", "起点")) + "</b>" + RULES.map(function (R, j) {
          var tr = R[1].trades[i - 1];
          return '<br><i style="background:' + R[2] + '"></i>' + R[0] + " " + usd(curves[j][i]) + (tr ? " (" + sgn(tr.pl, usd) + ")" : "");
        }).join("");
        tip2.style.display = "block";
        var b = eq.getBoundingClientRect(), cx = (ev.touches ? ev.touches[0].clientX : ev.clientX) - b.left, tw = tip2.offsetWidth;
        tip2.style.left = Math.max(0, Math.min(b.width - tw, cx - tw / 2)) + "px";
        tip2.style.top = Math.max(0, Math.min(y(curves[0][i]), y(curves[1][i])) - tip2.offsetHeight - 12) + "px";
      }
      rc.addEventListener("mousemove", on);
      rc.addEventListener("touchstart", on, { passive: true });
      rc.addEventListener("mouseleave", function () { tip2.style.display = "none"; });
    });
  }
  drawEquity();
  window.addEventListener("resize", function () { clearTimeout(rt); rt = setTimeout(function () { draw(); drawEquity(); }, 120); });
  if (SA.trades.length || SA.open) {
    var WHY = { tp: ["take profit", "止盈"], sl: ["stop loss", "止损"], close: ["at close", "收盘"] };
    function cell(x) {
      var when = x.why !== "close" && x.at ? " " + clock(x.at) : "";
      return usd(x.sell) + '<br><span class="label">' + bi(WHY[x.why][0] + when, WHY[x.why][1] + when) + "</span>" +
        '</td><td class="' + (x.pl > 0 ? "ok" : "miss") + '">' + sgn(x.pl, usd) + "<br>" + sgn(x.pct, p2) + "</td><td>" + usd(x.bal);
    }
    document.getElementById("trades").innerHTML = '<div class="tablewrap"><table><thead><tr><th>' + bi("Date", "日期") + "</th><th>" + bi("Buy at open", "开盘买入") +
      "</th><th>" + bi("A: sell", "A 卖出") + "</th><th>" + bi("A: P/L", "A 盈亏") + "</th><th>" + bi("A: balance", "A 余额") +
      "</th><th>" + bi("B: sell", "B 卖出") + "</th><th>" + bi("B: P/L", "B 盈亏") + "</th><th>" + bi("B: balance", "B 余额") + "</th></tr></thead><tbody>" +
      (SA.open ? "<tr><td>" + SA.open.r.d + "</td><td>" + SA.open.t.sym + "<br>" + usd(SA.open.t.buy) + '</td><td colspan="6">' + bi("open", "持仓中") + "</td></tr>" : "") +
      SA.trades.map(function (a, i) { return [a, SB.trades[i]]; }).reverse().map(function (ab) {
        return "<tr><td>" + ab[0].d + "</td><td>" + ab[0].sym + "<br>" + usd(ab[0].buy) + "</td><td>" + cell(ab[0]) + "</td><td>" + cell(ab[1]) + "</td></tr>";
      }).join("") + "</tbody></table></div>";
  }

  // --- Table ---
  if (rows.length) {
    document.getElementById("table").innerHTML = "<table><thead><tr><th>" + bi("Date", "日期") + "</th><th>" + bi("Forecast", "预测") +
      "</th><th>" + bi("Pre-mkt SOXX", "盘前 SOXX") + "</th><th>" + bi("Actual SOX", "实际 SOX") + "</th><th>" + bi("Error", "误差") + "</th></tr></thead><tbody>" +
      rows.slice().reverse().map(function (r) {
        return "<tr><td>" + r.d + "</td><td>" + pct(r.p) + "</td><td>" + pct(r.pre) + "</td><td>" + pct(r.a) + "</td><td>" +
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
