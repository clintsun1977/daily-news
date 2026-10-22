"""Build docs/cbc.html: 极简CBC / CBC Lite, 50 plain headlines from CBC News RSS.

Runs in GitHub Actions (.github/workflows/cbc.yml) every few hours; the cloud
news routine can't reach news sites, but Actions runners can.

Usage: python cbc.py
"""

import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import escape, unescape
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "docs" / "cbc.html"
TOTAL = 50

# (feed, zh, en, quota) in page order. Quotas add up to TOTAL; a feed that
# comes up short leaves its spare slots to the feeds after it.
FEEDS = [
    ("rss-topstories", "头条", "Top Stories", 10),
    ("rss-canada-toronto", "多伦多", "Toronto", 12),
    ("rss-canada", "加拿大", "Canada", 8),
    ("rss-politics", "政治", "Politics", 6),
    ("rss-business", "财经", "Business", 6),
    ("rss-world", "国际", "World", 4),
    ("rss-sports", "体育", "Sports", 4),
]
URL = "https://www.cbc.ca/webfeed/rss/{}"
# CBC stalls requests whose user agent names a bot, so send a plain one.
UA = "Mozilla/5.0"
DC = "{http://purl.org/dc/elements/1.1/}"

try:
    from zoneinfo import ZoneInfo
    TORONTO = ZoneInfo("America/Toronto")
except Exception:   # no tz database (e.g. Windows without tzdata)
    TORONTO = None


def fetch(feed):
    req = urllib.request.Request(URL.format(feed), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        root = ET.fromstring(r.read())
    items = []
    for it in root.iter("item"):
        title = unescape((it.findtext("title") or "").strip())
        link = (it.findtext("link") or "").strip()
        if not title or not link.startswith("https://www.cbc.ca/"):
            continue
        try:
            when = parsedate_to_datetime(it.findtext("pubDate"))
        except (TypeError, ValueError):
            when = None
        items.append({
            "id": (it.findtext("guid") or link).strip(),
            "title": re.sub(r"\s+", " ", title),
            "url": link,
            "when": when,
            "type": it.findtext(DC + "type") or "",
        })
    # Stories first, then video/other; newest first within each.
    items.sort(key=lambda i: (i["type"] != "story", -(i["when"].timestamp() if i["when"] else 0)))
    return items


def collect():
    seen, sections, spare = set(), [], 0
    fetched = []
    for feed, zh, en, quota in FEEDS:
        try:
            fetched.append((feed, zh, en, quota, fetch(feed)))
        except Exception as e:
            print("skip", feed, e)
            fetched.append((feed, zh, en, quota, []))
    for feed, zh, en, quota, items in fetched:
        want, picked = quota + spare, []
        for i in items:
            if len(picked) >= want:
                break
            if i["id"] in seen or i["url"] in seen:
                continue
            seen.update((i["id"], i["url"]))
            picked.append(i)
        spare = want - len(picked)
        if picked:
            sections.append({"id": feed.replace("rss-", ""), "zh": zh, "en": en, "items": picked})
    # Any slots still free go back to the feeds in order, from their leftovers.
    for feed, zh, en, quota, items in fetched:
        if spare <= 0:
            break
        sec = next((s for s in sections if s["id"] == feed.replace("rss-", "")), None)
        for i in items:
            if spare <= 0 or sec is None:
                break
            if i["id"] in seen or i["url"] in seen:
                continue
            seen.update((i["id"], i["url"]))
            sec["items"].append(i)
            spare -= 1
    return sections


def local(dt):
    if dt is None:
        return None
    return dt.astimezone(TORONTO) if TORONTO else dt


def clock(dt):
    return f"{dt.strftime('%b')} {dt.day}, {dt.hour % 12 or 12}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


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
                     f'<a class="h" href="{escape(i["url"])}" target="_blank" rel="noopener">{escape(i["title"])}</a>'
                     f'{t}'
                     f'<a class="src" href="{escape(i["url"])}" target="_blank" rel="noopener" '
                     f'aria-label="Open on CBC News">CBC<svg viewBox="0 0 24 24"><path d="M7 17 17 7M9 7h8v8" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg></a></li>')
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
    return TEMPLATE.format(nav=nav, body=body, total=n,
                           updated_iso=upd.isoformat(), updated=escape(clock(upd)))


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>极简CBC · CBC Lite</title>
<style>
:root {{
  --bg: #f2f7f6; --paper: #ffffff; --ink: #1f2b30; --muted: #66767c; --line: #dfe9e6; --hover: #f6fbfa;
  --accent: #0e8a7c; --accent-soft: #dff3ef; --accent-ink: #ffffff; --cbc: #d71920;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg: #0f1719; --paper: #162123; --ink: #e4eeee; --muted: #93a5a8; --line: #24363a; --hover: #1b282b;
    --accent: #3cc8b4; --accent-soft: #123430; --accent-ink: #062320; --cbc: #ff6b6b; color-scheme: dark;
  }}
}}
:root[data-theme="dark"] {{
  --bg: #0f1719; --paper: #162123; --ink: #e4eeee; --muted: #93a5a8; --line: #24363a; --hover: #1b282b;
  --accent: #3cc8b4; --accent-soft: #123430; --accent-ink: #062320; --cbc: #ff6b6b; color-scheme: dark;
}}
* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
@media (prefers-reduced-motion: reduce) {{ html {{ scroll-behavior: auto; }} }}
body {{ margin: 0; background: var(--bg); color: var(--ink);
  font: 19px/1.6 -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif;
  -webkit-font-smoothing: antialiased; }}
.wrap {{ max-width: 820px; margin: 0 auto;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }}
.zh {{ margin-left: 6px; opacity: .75; }}
header {{ padding-block: 22px 18px; border-bottom: 1px solid var(--line); background: var(--paper); }}
.back {{ display: inline-flex; align-items: center; gap: 4px; color: var(--accent); text-decoration: none;
  font-weight: 600; font-size: 16px; }}
.back:hover {{ text-decoration: underline; }}
.back svg {{ width: 18px; height: 18px; }}
h1 {{ margin: 10px 0 2px; font-size: clamp(28px, 6vw, 40px); line-height: 1.15; letter-spacing: .01em; }}
h1 .mark {{ color: var(--cbc); }}
h1 .zh {{ font-size: .6em; font-weight: 600; color: var(--muted); opacity: 1; }}
.meta {{ color: var(--muted); font-size: 15px; }}
.nav {{ position: sticky; top: 0; z-index: 5; background: color-mix(in srgb, var(--bg) 90%, transparent);
  backdrop-filter: blur(10px); border-bottom: 1px solid var(--line); }}
.nav .wrap {{ display: flex; gap: 4px; overflow-x: auto; padding-block: 8px; scrollbar-width: none; }}
.nav a {{ flex: none; color: var(--ink); text-decoration: none; padding: 4px 12px; border-radius: 999px;
  font-size: 16px; font-weight: 600; }}
.nav a:hover {{ background: var(--accent-soft); color: var(--accent); }}
section {{ padding-top: 26px; scroll-margin-top: 52px; }}
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
.h:hover {{ color: var(--accent); }}
.h:visited {{ color: var(--muted); }}
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
  li {{ grid-template-columns: 1.6em minmax(0, 1fr) auto; column-gap: 8px; padding: 10px 10px 10px 6px; }}
  .src {{ padding: 4px 8px; }}
}}
</style>
</head>
<body>
<header>
  <div class="wrap">
    <a class="back" href="./"><svg viewBox="0 0 24 24"><path d="M15 18 9 12l6-6" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>Clint Daily News<span class="zh" lang="zh">返回主页</span></a>
    <h1><span class="mark">CBC</span> Lite<span class="zh" lang="zh">极简CBC</span></h1>
    <div class="meta">{total} headlines from CBC News · updated <time id="upd" datetime="{updated_iso}">{updated}</time> (Toronto)<span class="zh" lang="zh">{total} 条 CBC 新闻标题，点右侧 CBC 打开原文</span></div>
  </div>
</header>
<nav class="nav"><div class="wrap">{nav}</div></nav>
<main class="wrap">
  {body}
  <footer>
    Headlines and links from <a href="https://www.cbc.ca/rss/" target="_blank" rel="noopener">CBC News RSS</a>, refreshed every few hours. Stories belong to CBC/Radio-Canada.
    <span class="zh" lang="zh">标题和链接来自 CBC 新闻 RSS，每隔几小时自动更新；新闻版权归 CBC/Radio-Canada 所有。</span>
  </footer>
</main>
<button type="button" id="totop" class="totop" aria-label="回到顶部 Back to top" title="回到顶部 Back to top">
  <svg viewBox="0 0 24 24"><path d="M12 19V6M5.5 11.5 12 5l6.5 6.5" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
</button>
<script>
(function () {{
  // Follow the theme picked on the main page (same site, same storage key).
  try {{ var t = localStorage.getItem("dn-theme"); if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t); }} catch (e) {{}}
  // Show "3h ago" next to recent headlines; older ones keep the printed date.
  var now = Date.now();
  document.querySelectorAll("li time").forEach(function (el) {{
    var m = Math.round((now - Date.parse(el.dateTime)) / 60000);
    if (!(m >= 0)) return;
    if (m < 60) el.textContent = (m < 1 ? 1 : m) + " min ago · " + (m < 1 ? 1 : m) + " 分钟前";
    else if (m < 24 * 60) el.textContent = Math.round(m / 60) + "h ago · " + Math.round(m / 60) + " 小时前";
  }});
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
    total = sum(len(s["items"]) for s in sections)
    if total < 10:
        raise SystemExit(f"only {total} headlines fetched; keeping the old page")
    OUT.write_text(render(sections, datetime.now(timezone.utc)), encoding="utf-8")
    print("wrote", OUT, total, "headlines:", ", ".join(f'{s["en"]} {len(s["items"])}' for s in sections))


if __name__ == "__main__":
    main()
