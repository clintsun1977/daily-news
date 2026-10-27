"""Build docs/index.html (the site's home page) and docs/cbc.html, the same page:
极简CBC / CBC Lite, 200 plain headlines from CBC News RSS, led by a
Burlington & Oakville section (inSauga feeds + CBC headlines naming the area).

Runs in GitHub Actions (.github/workflows/cbc.yml) every few hours; the cloud
news routine can't reach news sites, but Actions runners can.

Usage: python cbc.py
"""

import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import escape, unescape
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "docs" / "cbc.html"
HOME = ROOT / "docs" / "index.html"   # CBC Lite is the home page; cbc.html kept for old links
# Chinese headlines by story id, so each headline is translated only once.
CACHE = ROOT / "data" / "cbc-zh.json"
TOTAL = 200

# Sections in page and nav order, as the user asked (2026-10-26):
#   row 1: Top Stories, Canada, Toronto, Burlington & Oakville, World
#   row 2: Politics, Business, Science & Tech, Health, Arts, Sports
# Each entry is (id, zh, en, feeds, quota); "halton" is the local section built
# from LOCAL_FEEDS below, and BREAK starts the second nav row. A CBC feed holds
# at most ~20 items and the same story often sits in several, so some sections
# take extra feeds after their main one (Hamilton news in Toronto, NHL and
# soccer in Sports, other cities in Canada). Quotas add up to TOTAL; a section
# that comes up short leaves its spare slots to the sections after it.
BREAK = "|"
SECTIONS = [
    ("topstories", "头条", "Top Stories", ["rss-topstories"], 20),
    ("canada", "加拿大", "Canada", ["rss-canada", "rss-canada-ottawa", "rss-canada-kitchenerwaterloo",
                                  "rss-canada-montreal", "rss-canada-britishcolumbia", "rss-canada-calgary"], 20),
    ("toronto", "多伦多", "Toronto", ["rss-canada-toronto", "rss-canada-hamiltonnews"], 20),
    ("halton", "伯灵顿·奥克维尔", "Burlington & Oakville", [], 15),
    ("world", "国际", "World", ["rss-world"], 20),
    BREAK,
    ("politics", "政治", "Politics", ["rss-politics"], 20),
    ("business", "财经", "Business", ["rss-business"], 20),
    ("technology", "科技", "Science & Tech", ["rss-technology"], 15),
    ("health", "健康", "Health", ["rss-health"], 15),
    ("arts", "文艺", "Arts", ["rss-arts"], 15),
    ("sports", "体育", "Sports", ["rss-sports", "rss-sports-nhl", "rss-sports-soccer"], 20),
]
assert sum(x[4] for x in SECTIONS if x != BREAK) == TOTAL

# The reader lives in Burlington/Oakville (Halton). CBC has no Halton feed, so
# the "halton" section draws on local outlets: inSauga's area feeds (often
# blocked from GitHub's servers) and Google News searches (Inside Halton,
# BurlingtonToday, CHCH, The Spec...), plus any CBC headline naming the area.
# Sources take turns so neither town crowds out the other. It is filled first,
# so area stories land here rather than under Toronto.
GNEWS = "https://news.google.com/rss/search?q={}+when:2d&hl=en-CA&gl=CA&ceid=CA:en"
LOCAL_FEEDS = [
    (GNEWS.format("Burlington+Ontario"), "google"),
    (GNEWS.format("Oakville+Ontario"), "google"),
    ("https://www.insauga.com/region/burlington/feed/", "inSauga"),
    ("https://www.insauga.com/region/oakville/feed/", "inSauga"),
]
LOCAL_WORDS = re.compile(r"\b(burlington|oakville|halton)\b", re.I)
# Search results also bring obituaries and the U.S. towns with the same names.
NOT_LOCAL = re.compile(r"(?i:obituar|connecticut|vermont|iowa|missouri|new jersey|north carolina|kentucky|"
                       r"massachusetts|wisconsin)|\b(CT|Conn|VT|IA|MO|WA|NJ|NC|KY|MA|WI)\b")
URL = "https://www.cbc.ca/webfeed/rss/{}"
# CBC stalls requests whose user agent names a bot, so send a plain one.
UA = "Mozilla/5.0"
DC = "{http://purl.org/dc/elements/1.1/}"
TRANSLATE = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-CN&dt=t&q={}"

try:
    from zoneinfo import ZoneInfo
    TORONTO = ZoneInfo("America/Toronto")
except Exception:   # no tz database (e.g. Windows without tzdata)
    TORONTO = None


def fetch(feed, src="CBC"):
    """Items of one RSS feed: a CBC feed name, or a full feed URL from `src`."""
    url = feed if feed.startswith("https://") else URL.format(feed)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        root = ET.fromstring(r.read())
    items = []
    for it in root.iter("item"):
        title = unescape((it.findtext("title") or "").strip())
        link = (it.findtext("link") or "").strip()
        if not title or not link.startswith("https://") or (src == "CBC" and not link.startswith("https://www.cbc.ca/")):
            continue
        name = src
        if src == "google":
            name = (it.findtext("source") or "").strip() or "Google News"
            title = title.removesuffix(" - " + name)
            if not LOCAL_WORDS.search(title) or NOT_LOCAL.search(title + " | " + name) or name == "Legacy":
                continue
        try:
            when = parsedate_to_datetime(it.findtext("pubDate"))
        except (TypeError, ValueError):
            when = None
        items.append({
            "id": (it.findtext("guid") or link).strip(),
            "title": re.sub(r"\s+", " ", title),
            "url": link,
            "src": name,
            "when": when,
            "type": it.findtext(DC + "type") or "",
        })
    # Stories first, then video/other; newest first within each.
    items.sort(key=lambda i: (i["type"] != "story", -(i["when"].timestamp() if i["when"] else 0)))
    return items


def collect():
    secs = [x for x in SECTIONS if x != BREAK]
    feeds = {}
    for f in dict.fromkeys(f for x in secs for f in x[3]):
        try:
            feeds[f] = fetch(f)
        except Exception as e:
            print("skip", f, e)
            feeds[f] = []
    # A section's candidates: its main feed in CBC's order, then its extra feeds.
    pools = {sid: [i for f in fl for i in feeds[f]] for sid, _, _, fl, _ in secs}
    seen, picked = set(), {}

    def take(i):
        if i["id"] in seen or i["url"] in seen:
            return False
        seen.update((i["id"], i["url"]))
        return True

    # Local section first: local outlets in turn, plus CBC headlines naming the area.
    lquota = next(q for sid, *_, q in secs if sid == "halton")
    lists = []
    for url, src in LOCAL_FEEDS:
        try:
            lists.append(fetch(url, src))
        except Exception as e:
            print("skip", url, e)
    lists.append([i for items in feeds.values() for i in items if LOCAL_WORDS.search(i["title"])])
    for lst in lists:
        lst.sort(key=lambda i: -(i["when"].timestamp() if i["when"] else 0))
    local, titles = [], set()
    while len(local) < lquota and any(lists):
        for lst in lists:
            while lst and len(local) < lquota:
                i = lst.pop(0)
                key = re.sub(r"\W+", " ", i["title"].lower()).strip()
                if key in titles or not take(i):
                    continue
                titles.add(key)
                local.append(i)
                break
    local.sort(key=lambda i: -(i["when"].timestamp() if i["when"] else 0))
    picked["halton"] = local
    spare = lquota - len(local)
    # Then the CBC sections in page order; a short one passes its spare slots on.
    for sid, _, _, _, quota in secs:
        if sid == "halton":
            continue
        want, got = quota + spare, []
        for i in pools[sid]:
            if len(got) >= want:
                break
            if take(i):
                got.append(i)
        picked[sid] = got
        spare = want - len(got)
    # Slots still free go back to the sections in order, from their leftovers.
    for sid, *_ in secs:
        for i in pools[sid]:
            if spare <= 0:
                break
            if take(i):
                picked[sid].append(i)
                spare -= 1
    row2 = {x[0] for x in SECTIONS[SECTIONS.index(BREAK) + 1:]}
    return [{"id": sid, "zh": zh, "en": en, "items": picked[sid], "row": 2 if sid in row2 else 1}
            for sid, zh, en, _, _ in secs if picked.get(sid)]


def translate(text):
    req = urllib.request.Request(TRANSLATE.format(urllib.parse.quote(text)), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        out = json.loads(r.read())
    return "".join(seg[0] for seg in out[0] if seg[0]).strip()


def add_chinese(sections):
    """Give every headline a "zh" title, from the cache or machine translation.

    A headline that can't be translated keeps zh = None and shows in English.
    """
    try:
        cache = json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    keep, failed = {}, 0
    for s in sections:
        for i in s["items"]:
            hit = cache.get(i["id"])
            if hit and hit["en"] == i["title"]:
                i["zh"] = hit["zh"]
            elif failed < 3:   # stop asking once the service keeps failing
                try:
                    i["zh"] = translate(i["title"])
                    time.sleep(0.3)
                except Exception as e:
                    print("translate failed:", e)
                    failed += 1
            if i.get("zh"):
                keep[i["id"]] = {"en": i["title"], "zh": i["zh"]}
    # Only the headlines on the page are kept, so the file stays small.
    CACHE.write_text(json.dumps(keep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def local(dt):
    if dt is None:
        return None
    return dt.astimezone(TORONTO) if TORONTO else dt


def clock(dt):
    return f"{dt.strftime('%b')} {dt.day}, {dt.hour % 12 or 12}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def headline(i):
    en = escape(i["title"])
    if not i.get("zh"):
        return f'<span class="t" lang="en">{en}</span>'
    return (f'<span class="t en" lang="en">{en}</span>'
            f'<span class="t zh" lang="zh">{escape(i["zh"])}</span>')


def render(sections, now):
    n = 0
    body = ""
    nav = ""
    for s in sections:
        rows = ""
        for i in s["items"]:
            n += 1
            when = local(i["when"])
            t = (f'<time datetime="{when.isoformat()}">{escape(clock(when))}</time>' if when else "")
            rows += (f'<li><span class="n">{n}</span>'
                     f'<a class="h" href="{escape(i["url"])}" target="_blank" rel="noopener">{headline(i)}</a>'
                     f'{t}'
                     f'<a class="src" href="{escape(i["url"])}" target="_blank" rel="noopener" '
                     f'aria-label="Open on {escape(i["src"])}">{escape(i["src"])}<svg viewBox="0 0 24 24"><path d="M7 17 17 7M9 7h8v8" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg></a></li>')
        if s["row"] == 2 and '<span class="br">' not in nav:
            nav += '<span class="br"></span>'
        nav += (f'<a href="#{s["id"]}"><span class="en" lang="en">{s["en"]}</span>'
                f'<span class="zh" lang="zh">{s["zh"]}</span></a>')
        body += (f'<section id="{s["id"]}"><h2><span class="en" lang="en">{s["en"]}</span>'
                 f'<span class="zh" lang="zh">{s["zh"]}</span><span class="count">{len(s["items"])}</span></h2>'
                 f'<ol>{rows}</ol></section>')
    upd = local(now)
    if TORONTO is None:   # borrow CBC's own offset (EDT/EST) from the newest item
        first = next((i["when"] for s in sections for i in s["items"] if i["when"]), None)
        if first:
            upd = now.astimezone(first.tzinfo)
    date_en = f"{upd.strftime('%A, %B')} {upd.day}, {upd.year}"
    date_zh = f"{upd.year}年{upd.month}月{upd.day}日 星期{'一二三四五六日'[upd.weekday()]}"
    return TEMPLATE.format(nav=nav, body=body, total=n, updated_iso=upd.isoformat(),
                           date_en=escape(date_en), date_zh=escape(date_zh),
                           updated=escape(clock(upd)), updated_zh=f"{upd.month}月{upd.day}日 {upd.hour}:{upd.minute:02d}")


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CLINT DAILY NEWS · 极简CBC</title>
<style>
:root {{
  --bg: #f2f7f6; --paper: #ffffff; --ink: #1f2b30; --muted: #66767c; --line: #dfe9e6; --hover: #f6fbfa;
  --accent: #0e8a7c; --accent-soft: #dff3ef; --accent-ink: #ffffff; --cbc: #d71920;
  --mast-a: #e3f4f0; --mast-b: #eef5fb; --shadow-up: 0 2px 4px rgba(20, 60, 55, .06), 0 10px 24px rgba(20, 60, 55, .09);
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg: #0f1719; --paper: #162123; --ink: #e4eeee; --muted: #93a5a8; --line: #24363a; --hover: #1b282b;
    --accent: #3cc8b4; --accent-soft: #123430; --accent-ink: #062320; --cbc: #ff6b6b; color-scheme: dark;
    --mast-a: #11282a; --mast-b: #121d26; --shadow-up: 0 6px 20px rgba(0, 0, 0, .4);
  }}
}}
:root[data-theme="dark"] {{
  --bg: #0f1719; --paper: #162123; --ink: #e4eeee; --muted: #93a5a8; --line: #24363a; --hover: #1b282b;
  --accent: #3cc8b4; --accent-soft: #123430; --accent-ink: #062320; --cbc: #ff6b6b; color-scheme: dark;
    --mast-a: #11282a; --mast-b: #121d26; --shadow-up: 0 6px 20px rgba(0, 0, 0, .4);
}}
* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
@media (prefers-reduced-motion: reduce) {{ html {{ scroll-behavior: auto; }} }}
body {{ margin: 0; background: var(--bg); color: var(--ink);
  font: 19px/1.6 -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif;
  -webkit-font-smoothing: antialiased; }}
.wrap {{ max-width: 920px; margin: 0 auto;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }}
.zh {{ margin-left: 6px; opacity: .75; }}
/* language modes, shared with the main page (body.m-bi / m-zh / m-en) */
body.m-en .zh {{ display: none !important; }}
body.m-zh .en {{ display: none !important; }}
body.m-en .zh, body.m-zh .zh {{ margin-left: 0; }}
body.m-zh .zh {{ opacity: 1; }}
.seg {{ display: inline-flex; border: 1px solid var(--line); border-radius: 999px; overflow: hidden; background: var(--bg); padding: 2px; }}
.seg button {{ border: 0; background: none; color: var(--muted); padding: 4px 12px; font: inherit; font-size: 15px; cursor: pointer;
  border-radius: 999px; transition: background .15s, color .15s; }}
.seg button.on {{ background: var(--accent); color: var(--accent-ink); }}
.top {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; margin-top: 18px; }}
header.masthead {{ padding-block: 28px 18px; background: linear-gradient(135deg, var(--mast-a), var(--mast-b));
  border-bottom: 1px solid var(--line); }}
.masthead .mast-top {{ display: flex; align-items: center; justify-content: center; gap: clamp(16px, 4vw, 36px); }}
.masthead .portrait {{ flex: none; width: clamp(92px, 18vw, 140px); height: auto; border-radius: 16px;
  border: 4px solid var(--paper); box-shadow: var(--shadow-up); }}
.masthead .titles {{ min-width: 0; }}
.masthead .brand {{ font-family: Georgia, "Songti SC", "SimSun", serif; font-size: clamp(30px, 6.4vw, 54px);
  font-weight: 700; letter-spacing: .05em; line-height: 1.05; margin: 0; text-wrap: balance; }}
.masthead .brand small {{ display: block; font-size: .32em; letter-spacing: .3em; color: var(--accent);
  font-family: inherit; margin-top: 10px; font-weight: 600; }}
.masthead .date {{ margin-top: 10px; color: var(--muted); font-size: 18px; }}
.masthead .date b {{ color: var(--ink); font-weight: 600; }}
.masthead .meta {{ margin: 14px auto 0; max-width: 760px; text-align: center; font-size: 14px; }}
.hero {{ position: relative; margin: 44px 0 0; border-radius: 18px; overflow: hidden;
  box-shadow: var(--shadow-up); background: var(--line); }}
.hero img {{ display: block; width: 100%; max-width: 100%; height: auto; aspect-ratio: 1600 / 683; object-fit: cover; }}
.hero figcaption {{ position: absolute; left: 0; right: 0; bottom: 0; display: flex; flex-wrap: wrap; align-items: baseline;
  gap: 4px 12px; padding: 28px 18px 12px; font-size: 16px; line-height: 1.4; color: #fff;
  background: linear-gradient(to top, rgba(10,30,30,.6), rgba(10,30,30,0)); text-shadow: 0 1px 2px rgba(0,0,0,.35); }}
.hero figcaption .en {{ font-family: Georgia, serif; font-style: italic; font-size: 17px; }}
.hero figcaption .zh {{ font-size: 15px; opacity: .9; margin-left: 0; }}
.sox-btn {{ display: inline-flex; align-items: baseline; gap: 5px; color: var(--ink); text-decoration: none;
  font-weight: 600; font-size: 16px; padding: 4px 12px; border-radius: 999px; background: var(--paper);
  border: 1px solid color-mix(in srgb, #2a78d6 40%, var(--line)); }}
.sox-btn:hover {{ background: #2a78d6; border-color: #2a78d6; color: #fff; }}
.sox-btn b {{ color: #2a78d6; font-weight: 800; letter-spacing: .03em; }}
.sox-btn:hover b {{ color: inherit; }}
body.m-bi .sox-btn .zh {{ font-size: 14px; opacity: .75; }}
.back {{ display: inline-flex; align-items: center; gap: 4px; color: var(--accent); text-decoration: none;
  font-weight: 600; font-size: 16px; }}
.back:hover {{ text-decoration: underline; }}
.back svg {{ width: 18px; height: 18px; }}
h1 {{ margin: 10px 0 2px; font-size: clamp(28px, 6vw, 40px); line-height: 1.15; letter-spacing: .01em; }}
h1 .mark {{ color: var(--cbc); }}
h1 .zh {{ font-size: .6em; font-weight: 600; color: var(--muted); opacity: 1; }}
body.m-zh h1 .zh {{ font-size: 1em; color: inherit; }}
body.m-zh h1 .mark {{ display: none; }}   /* "极简CBC" already says CBC */
.meta {{ color: var(--muted); font-size: 15px; }}
.meta .zh {{ display: block; margin-left: 0; }}
.nav {{ position: sticky; top: 0; z-index: 5; background: color-mix(in srgb, var(--bg) 90%, transparent);
  backdrop-filter: blur(10px); border-bottom: 1px solid var(--line); }}
.nav .wrap {{ display: flex; flex-wrap: wrap; gap: 2px; padding-block: 8px; }}
.nav a {{ flex: none; color: var(--ink); text-decoration: none; padding: 4px 8px; border-radius: 999px;
  font-size: 15px; font-weight: 600; }}
.nav a .zh {{ margin-left: 4px; }}
.nav a:hover {{ background: var(--accent-soft); color: var(--accent); }}
.nav .br {{ flex-basis: 100%; height: 0; }}   /* second row of sections */
section {{ padding-top: 26px; scroll-margin-top: var(--navh, 56px); }}
h2 {{ margin: 0 0 8px; font-size: 22px; padding-left: 12px; border-left: 4px solid var(--accent); line-height: 1.3; }}
.count {{ display: inline-block; min-width: 1.6em; margin-left: 8px; padding: 0 7px; border-radius: 999px;
  background: var(--accent-soft); color: var(--accent); font-size: 13px; font-weight: 700; text-align: center;
  vertical-align: middle; line-height: 1.7; }}
ol {{ list-style: none; margin: 0; padding: 0; background: var(--paper); border: 1px solid var(--line); border-radius: 14px; overflow: hidden; }}
li {{ display: grid; grid-template-columns: 2em minmax(0, 1fr) auto; grid-template-areas: "n h src" "n t src";
  column-gap: 10px; align-items: center; padding: 11px 12px 11px 10px; border-top: 1px solid var(--line); }}
li:first-child {{ border-top: 0; }}
li:hover {{ background: var(--hover); }}
.n {{ grid-area: n; align-self: start; padding-top: 2px; color: var(--muted); font-size: 14px; font-weight: 700; text-align: right;
  font-variant-numeric: tabular-nums; }}
.h {{ grid-area: h; color: var(--ink); text-decoration: none; font-weight: 600; line-height: 1.4; }}
.h .t {{ display: block; }}
.h .t.zh {{ margin: 2px 0 0; font-size: .9em; font-weight: 500; color: var(--muted); opacity: 1; }}
body.m-zh .h .t.zh {{ margin: 0; font-size: 1em; font-weight: 600; color: inherit; }}
.h:hover {{ color: var(--accent); }}
.h:visited, .h:visited .t {{ color: var(--muted); }}
time {{ grid-area: t; color: var(--muted); font-size: 14px; }}
.src {{ grid-area: src; display: inline-flex; align-items: center; gap: 2px; padding: 4px 10px; border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--cbc) 40%, var(--line)); color: var(--cbc); text-decoration: none;
  font-size: 14px; font-weight: 800; letter-spacing: .03em; white-space: nowrap; }}
.src:hover {{ background: var(--cbc); border-color: var(--cbc); color: #fff; }}
.src svg {{ width: 15px; height: 15px; }}
footer {{ margin-top: 36px; padding: 18px 0 90px; border-top: 1px solid var(--line); color: var(--muted); font-size: 14px; }}
footer a {{ color: var(--accent); }}
.totop {{ position: fixed; z-index: 10; right: max(18px, env(safe-area-inset-right, 0px)); bottom: max(18px, env(safe-area-inset-bottom, 0px));
  width: 50px; height: 50px; border-radius: 50%; border: 0; padding: 0; cursor: pointer;
  display: grid; place-items: center; background: var(--accent); color: var(--accent-ink);
  box-shadow: 0 6px 20px rgba(0, 0, 0, .18);
  opacity: 0; visibility: hidden; transform: translateY(12px); transition: opacity .2s, transform .2s, visibility .2s; }}
.totop.show {{ opacity: 1; visibility: visible; transform: none; }}
.totop svg {{ width: 24px; height: 24px; }}
@media (max-width: 600px) {{
  body {{ font-size: 18px; }}
  header.masthead {{ padding-block: 20px 14px; }}
  .masthead .date {{ font-size: 16px; }}
  .hero {{ margin-top: 28px; border-radius: 14px; }}
  .hero figcaption {{ position: static; padding: 8px 12px 10px; color: var(--muted); background: var(--paper);
    text-shadow: none; font-size: 14px; }}
  .hero figcaption .en {{ font-size: 15px; color: var(--ink); }}
  li {{ grid-template-columns: 1.6em minmax(0, 1fr) auto; column-gap: 8px; padding: 10px 10px 10px 6px; }}
  .src {{ padding: 4px 8px; }}
  .nav a {{ padding: 3px 9px; font-size: 15px; }}
}}
</style>
</head>
<body class="m-bi">
<header class="masthead">
  <div class="wrap">
    <div class="mast-top">
      <img class="portrait" src="header-sketch.jpg" width="150" height="223" alt="">
      <div class="titles">
        <h1 class="brand">CLINT DAILY NEWS<small>每日新闻 · 中英双语</small></h1>
        <div class="date"><b>{date_en}</b> · <b>{date_zh}</b></div>
      </div>
    </div>
    <div class="meta" data-updated="{updated_iso}"><span class="en" lang="en">{total} headlines from CBC News (Burlington &amp; Oakville from local outlets) · updated {updated} (Toronto) · Chinese by machine translation</span><span class="zh" lang="zh">{total} 条新闻标题（CBC 为主，伯灵顿·奥克维尔取自当地媒体）· 更新于多伦多时间 {updated_zh} · 中文为机器翻译，点右侧按钮打开原文</span></div>
    <div class="top">
    <a class="sox-btn" href="sox.html"><b>SOX</b><span class="en" lang="en">Forecast</span><span class="zh" lang="zh">SOX预测</span></a>
    <div class="seg" id="lang" role="group" aria-label="语言 Language">
      <button data-m="bi" class="on">双语</button><button data-m="zh">中文</button><button data-m="en">EN</button>
    </div>
    </div>
  </div>
</header>
<nav class="nav"><div class="wrap">{nav}</div></nav>
<main class="wrap">
  {body}
  <figure class="hero">
    <img src="hero-goose-eagle.jpg" srcset="hero-goose-eagle-800.jpg 800w, hero-goose-eagle.jpg 1600w"
         sizes="(max-width: 920px) 100vw, 888px" width="1600" height="683" loading="lazy"
         alt="A Canada goose with wings spread honks at a bald eagle on snowy ice">
    <figcaption><span class="en" lang="en">Standoff on the ice: a Canada goose takes on a bald eagle</span><span class="zh" lang="zh">冰上对峙：加拿大雁硬刚白头海雕</span></figcaption>
  </figure>
  <footer>
    <span class="en" lang="en">Headlines and links from <a href="https://www.cbc.ca/rss/" target="_blank" rel="noopener">CBC News RSS</a> and, for Burlington &amp; Oakville, local outlets found through Google News and inSauga, refreshed every few hours; Chinese headlines are machine-translated. Stories belong to their publishers.</span>
    <span class="zh" lang="zh">标题和链接来自 CBC 新闻 RSS，伯灵顿·奥克维尔栏目取自 Google 新闻搜索到的当地媒体和 inSauga，每隔几小时自动更新；中文标题为机器翻译，请以英文原文为准。新闻版权归原媒体所有。</span>
  </footer>
</main>
<button type="button" id="totop" class="totop" aria-label="回到顶部 Back to top" title="回到顶部 Back to top">
  <svg viewBox="0 0 24 24"><path d="M12 19V6M5.5 11.5 12 5l6.5 6.5" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
</button>
<script>
(function () {{
  // Theme and language follow the main page (same site, same storage keys).
  function get(k) {{ try {{ return localStorage.getItem(k); }} catch (e) {{ return null; }} }}
  function set(k, v) {{ try {{ localStorage.setItem(k, v); }} catch (e) {{}} }}
  var t = get("dn-theme");
  if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
  var btns = document.querySelectorAll("#lang button");
  function pick(m) {{
    document.body.className = "m-" + m;
    btns.forEach(function (b) {{ b.classList.toggle("on", b.dataset.m === m); }});
  }}
  btns.forEach(function (b) {{ b.onclick = function () {{ pick(b.dataset.m); set("dn-lang", b.dataset.m); }}; }});
  var saved = get("dn-lang");
  if (saved === "bi" || saved === "zh" || saved === "en") pick(saved);
  // "3h ago" for recent headlines, the date and time for older ones.
  var now = Date.now();
  function both(en, zh) {{ return '<span class="en" lang="en">' + en + '</span><span class="zh" lang="zh">' + zh + "</span>"; }}
  document.querySelectorAll("li time").forEach(function (el) {{
    var d = new Date(el.dateTime), m = Math.round((now - d) / 60000);
    if (!(m >= 0)) return;
    if (m < 60) {{ m = Math.max(m, 1); el.innerHTML = both(m + " min ago", m + " 分钟前"); }}
    else if (m < 24 * 60) {{ var h = Math.round(m / 60); el.innerHTML = both(h + "h ago", h + " 小时前"); }}
    else el.innerHTML = both(el.textContent, (d.getMonth() + 1) + "月" + d.getDate() + "日 " + d.getHours() + ":" + ("0" + d.getMinutes()).slice(-2));
  }});
  var nav = document.querySelector(".nav");
  function navh() {{ document.documentElement.style.setProperty("--navh", nav.offsetHeight + 4 + "px"); }}
  window.addEventListener("resize", navh);
  navh();
  var totop = document.getElementById("totop");
  function onScroll() {{ totop.classList.toggle("show", window.scrollY > 300); }}
  window.addEventListener("scroll", onScroll, {{ passive: true }});
  onScroll();
  totop.onclick = function () {{ window.scrollTo({{ top: 0 }}); }};
}})();
</script>
</body>
</html>
"""


def main():
    sections = collect()
    add_chinese(sections)
    total = sum(len(s["items"]) for s in sections)
    if total < 10:
        raise SystemExit(f"only {total} headlines fetched; keeping the old page")
    page = render(sections, datetime.now(timezone.utc))
    OUT.write_text(page, encoding="utf-8")
    HOME.write_text(page, encoding="utf-8")
    print("wrote", OUT, total, "headlines:", ", ".join(f'{s["en"]} {len(s["items"])}' for s in sections))


if __name__ == "__main__":
    main()
