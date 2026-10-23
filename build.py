"""Build the daily news pages.

Reads every data/YYYY-MM-DD.json and writes:
  docs/YYYY-MM-DD.html  - one page per day (GitHub Pages serves docs/)
  docs/index.html       - copy of the latest day (with archive links)
  build/artifact.html   - latest day in claude.ai Artifact format (not published to Pages)

Usage: python build.py
"""

import json
import re
from datetime import date
from html import escape
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
SITE = ROOT / "docs"

TAGS = {
    "breaking": ("突发", "Breaking"),
    "politics": ("政治", "Politics"),
    "military": ("军事", "Military"),
    "finance": ("财经", "Business"),
    "sports": ("体育", "Sports"),
    "tech": ("科技", "Tech"),
    "nature": ("自然", "Nature"),
    "art": ("艺术", "Arts"),
    "entertainment": ("娱乐圈", "Entertainment"),
    "gossip": ("八卦", "Gossip"),
}

LEAGUES = {
    "EPL": ("英超", "Premier League"),
    "LaLiga": ("西甲", "LaLiga"),
    "UCL": ("欧冠", "Champions League"),
    "ATP": ("网球", "Tennis"),
    "WTA": ("网球", "Tennis"),
    "NBA": ("NBA", "NBA"),
    "NFL": ("NFL", "NFL"),
    "NHL": ("NHL", "NHL"),
    "MLB": ("MLB", "MLB"),
    "CFL": ("CFL", "CFL"),
}

# Tags that still label items but get no button in the filter bar.
NO_FILTER = {"entertainment", "gossip"}

WEEKDAYS_ZH = "一二三四五六日"
CUR = ' class="cur"'
# First entry in the section bar: the CBC Lite headline page (built by cbc.py).
CBC_LINK = ('<a class="cbc-btn" href="cbc.html"><b>CBC</b><span class="en" lang="en">Lite</span>'
            '<span class="zh" lang="zh">极简CBC</span></a>')
# Second entry: SOX预测, the daily semiconductor-index forecast (built by sox.py).
SOX_LINK = ('<a class="sox-btn" href="sox.html"><b>SOX</b><span class="en" lang="en">Forecast</span>'
            '<span class="zh" lang="zh">预测</span></a>')


def bi(zh, en, tag="span", cls=""):
    """Render a bilingual pair; CSS decides which halves are visible."""
    c = f" {cls}" if cls else ""
    if zh == en:
        return f'<{tag} class="{cls}">{escape(zh)}</{tag}>'
    # English first and primary; Chinese second as the supporting line.
    return (f'<{tag} class="en{c}" lang="en">{escape(en)}</{tag}>'
            f'<{tag} class="zh{c}" lang="zh">{escape(zh)}</{tag}>')


def render_item(item):
    tags = item.get("tags", [])
    chips = []
    if item.get("league"):
        zh, en = LEAGUES.get(item["league"], (item["league"], item["league"]))
        chips.append(f'<span class="chip league">{bi(zh, en)}</span>')
    for t in sorted(tags, key=list(TAGS).index):
        if t == "sports" and item.get("league"):
            continue
        zh, en = TAGS[t]
        chips.append(f'<span class="chip t-{t}">{bi(zh, en)}</span>')
    sources = " · ".join(
        f'<a href="{escape(s["url"])}" target="_blank" rel="noopener">{escape(s["name"])}</a>'
        for s in item.get("sources", [])
    )
    t, s = item["title"], item["summary"]
    # Text for the listen button lives in data attributes so the script can
    # read title + summary in whichever language mode is active.
    speech = (f'data-tzh="{escape(t["zh"])}" data-ten="{escape(t["en"])}" '
              f'data-szh="{escape(s["zh"])}" data-sen="{escape(s["en"])}"')
    return f"""
      <details class="item{' is-breaking' if 'breaking' in tags else ''}" data-tags="{' '.join(tags)}" {speech}>
        <summary>
          <div class="head">
            <div class="chips">{''.join(chips)}</div>
            {bi(t['zh'], t['en'], 'span', 'h')}
          </div>
          <button type="button" class="stopbtn" hidden aria-label="结束 Stop" title="结束 Stop">
            <svg viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>
          </button>
          <button type="button" class="speak" aria-label="朗读 Listen" title="朗读 Listen">
            <svg viewBox="0 0 24 24" class="i-play"><path d="M4 9v6h4l5 4V5L8 9H4z"/><path d="M16 8.5a5 5 0 0 1 0 7M18.5 6a8.5 8.5 0 0 1 0 12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
            <svg viewBox="0 0 24 24" class="i-pause"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>
            <svg viewBox="0 0 24 24" class="i-resume"><path d="M8 5.5v13l11-6.5z"/></svg>
          </button>
          <svg class="chev" viewBox="0 0 24 24"><path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </summary>
        <div class="body">
          {bi(s['zh'], s['en'], 'p', 'sum')}
          <div class="src"><span class="src-label">{bi('来源', 'Sources')}</span> {sources}</div>
        </div>
      </details>"""


def count_items(section):
    if "groups" in section:
        return sum(len(g["items"]) for g in section["groups"])
    return len(section["items"])


def breaking_first(items):
    return sorted(items, key=lambda i: "breaking" not in i.get("tags", []))


def render_section(section):
    n = count_items(section)
    head = (f'<h2>{bi(section["title"]["zh"], section["title"]["en"])}'
            f'<span class="count">{n}</span></h2>')
    if "groups" in section:
        body = ""
        for g in section["groups"]:
            body += (f'<h3 class="group">{bi(g["title"]["zh"], g["title"]["en"])}'
                     f'<span class="count">{len(g["items"])}</span></h3>')
            body += '<div class="list">' + "".join(render_item(i) for i in breaking_first(g["items"])) + "</div>"
    else:
        body = '<div class="list">' + "".join(render_item(i) for i in breaking_first(section["items"])) + "</div>"
    return f'<section id="{section["id"]}">{head}{body}</section>'


def render_page(day, all_days):
    d = date.fromisoformat(day["date"])
    date_zh = f"{d.year}年{d.month}月{d.day}日 星期{WEEKDAYS_ZH[d.weekday()]}"
    date_en = f"{d.strftime('%A, %B')} {d.day}, {d.year}"

    nav = CBC_LINK + SOX_LINK + "".join(
        f'<a href="#{s["id"]}">{bi(s["title"]["zh"], s["title"]["en"])}'
        f'<span class="count">{count_items(s)}</span></a>'
        for s in day["sections"]
    )
    filters = '<button class="on" data-f="all">' + bi("全部", "All") + "</button>" + "".join(
        f'<button data-f="{k}">{bi(zh, en)}</button>' for k, (zh, en) in TAGS.items()
        if k not in NO_FILTER
    )
    sections = "".join(render_section(s) for s in day["sections"])
    archive = "".join(
        f'<a href="{x}.html"{CUR if x == day["date"] else ""}>{x}</a>'
        for x in sorted(all_days, reverse=True)
    )
    upd = day.get("updated", {"zh": "", "en": ""})

    return TEMPLATE.format(
        date=day["date"], date_zh=escape(date_zh), date_en=escape(date_en),
        updated=bi(upd["zh"], upd["en"]), nav=nav, filters=filters,
        sections=sections, archive=archive, archive_label=bi("往期", "Archive"),
        expand=bi("全部展开", "Expand all"), collapse=bi("全部收起", "Collapse all"),
    )


TEMPLATE = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Clint Daily News · {date}</title>
<style>
:root {{
  --bg: #f2f7f6; --paper: #ffffff; --ink: #1f2b30; --muted: #66767c; --line: #dfe9e6; --hover: #f6fbfa;
  --accent: #0e8a7c; --accent-soft: #dff3ef; --accent-ink: #ffffff;
  --mast-a: #e3f4f0; --mast-b: #eef5fb; --shadow: 0 1px 2px rgba(20, 60, 55, .05), 0 4px 14px rgba(20, 60, 55, .05);
  --shadow-up: 0 2px 4px rgba(20, 60, 55, .06), 0 10px 24px rgba(20, 60, 55, .09);
  --politics: #3b63d6; --finance: #2b9348; --sports: #e8590c; --tech: #7048e8; --breaking: #e03131; --ent: #c2255c; --gossip: #0b7285; --military: #66802a; --nature: #0ca678; --art: #c2255c;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg: #0f1719; --paper: #162123; --ink: #e4eeee; --muted: #93a5a8; --line: #24363a; --hover: #1b282b;
    --accent: #3cc8b4; --accent-soft: #123430; --accent-ink: #062320;
    --mast-a: #11282a; --mast-b: #121d26; --shadow: 0 1px 2px rgba(0, 0, 0, .3); --shadow-up: 0 6px 20px rgba(0, 0, 0, .4);
    --politics: #91a7ff; --finance: #69db7c; --sports: #ffa94d; --tech: #b197fc; --breaking: #ff8787; --ent: #f783ac; --gossip: #66d9e8; --military: #c0ca33; --nature: #63e6be; --art: #faa2c1; color-scheme: dark;
  }}
}}
:root[data-theme="dark"] {{
  --bg: #0f1719; --paper: #162123; --ink: #e4eeee; --muted: #93a5a8; --line: #24363a; --hover: #1b282b;
  --accent: #3cc8b4; --accent-soft: #123430; --accent-ink: #062320;
  --mast-a: #11282a; --mast-b: #121d26; --shadow: 0 1px 2px rgba(0, 0, 0, .3); --shadow-up: 0 6px 20px rgba(0, 0, 0, .4);
  --politics: #91a7ff; --finance: #69db7c; --sports: #ffa94d; --tech: #b197fc; --breaking: #ff8787; --ent: #f783ac; --gossip: #66d9e8; --military: #c0ca33; --nature: #63e6be; --art: #faa2c1; color-scheme: dark;
}}
* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
@media (prefers-reduced-motion: reduce) {{ html {{ scroll-behavior: auto; }} }}
body {{ margin: 0; background: var(--bg); color: var(--ink);
  font: 19px/1.7 -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif;
  -webkit-font-smoothing: antialiased; }}
.wrap {{ max-width: 920px; margin: 0 auto;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }}
header.masthead {{ padding-block: 28px 24px; background: linear-gradient(135deg, var(--mast-a), var(--mast-b)); }}
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
.masthead .upd {{ margin-top: 2px; font-size: 15px; }}
.hero {{ position: relative; margin: 44px 0 0; border-radius: 18px; overflow: hidden;
  box-shadow: var(--shadow-up); background: var(--line); }}
.hero img {{ display: block; width: 100%; max-width: 100%; height: auto; aspect-ratio: 1600 / 683; object-fit: cover; }}
.hero figcaption {{ position: absolute; left: 0; right: 0; bottom: 0; display: flex; flex-wrap: wrap; align-items: baseline;
  gap: 4px 12px; padding: 28px 18px 12px; font-size: 16px; line-height: 1.4; color: #fff;
  background: linear-gradient(to top, rgba(10,30,30,.6), rgba(10,30,30,0)); text-shadow: 0 1px 2px rgba(0,0,0,.35); }}
.hero figcaption .en {{ font-family: Georgia, serif; font-style: italic; font-size: 17px; }}
.hero figcaption .zh {{ font-size: 15px; opacity: .9; }}
.bar {{ position: sticky; top: env(safe-area-inset-top, 0px); z-index: 5;
  background: color-mix(in srgb, var(--paper) 88%, transparent); backdrop-filter: saturate(1.4) blur(10px);
  border-bottom: 1px solid var(--line); box-shadow: 0 2px 12px rgba(20, 60, 55, .04); }}
.bar .wrap {{ display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; padding-block: 10px; }}
.nav {{ display: flex; gap: 4px; flex-wrap: wrap; }}
.nav a {{ color: var(--ink); text-decoration: none; padding: 5px 12px; border-radius: 999px; font-weight: 600; font-size: 17px;
  transition: background .15s, color .15s; }}
.nav a:hover {{ background: var(--accent-soft); color: var(--accent); }}
.nav .zh {{ margin-left: 4px; }}
.ctrls {{ margin-left: auto; display: flex; gap: 10px; flex-wrap: wrap; }}
.seg {{ display: inline-flex; border: 1px solid var(--line); border-radius: 999px; overflow: hidden; background: var(--bg); padding: 2px; }}
.seg button {{ border: 0; background: none; color: var(--muted); padding: 5px 12px; font: inherit; font-size: 15px; cursor: pointer;
  border-radius: 999px; transition: background .15s, color .15s; }}
.seg button.on {{ background: var(--accent); color: var(--accent-ink); }}
.tools {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; padding: 22px 0 0; }}
.tools button {{ border: 1px solid var(--line); background: var(--paper); color: var(--ink); border-radius: 999px;
  padding: 5px 14px; font: inherit; font-size: 15px; cursor: pointer; transition: border-color .15s, background .15s, color .15s; }}
.tools button:hover {{ border-color: var(--accent); color: var(--accent); }}
.tools .filters button.on {{ border-color: var(--accent); background: var(--accent); color: var(--accent-ink); }}
.tools .filters button[data-f="breaking"] {{ color: var(--breaking); border-color: color-mix(in srgb, var(--breaking) 45%, var(--line)); }}
.tools .filters button[data-f="breaking"].on {{ background: var(--breaking); border-color: var(--breaking); color: #fff; }}
.tools .filters {{ display: flex; gap: 8px; flex-wrap: wrap; }}
.tools .fold {{ margin-left: auto; display: flex; gap: 8px; }}
.tools .zh, .chip .zh, .src-label .zh {{ margin-left: 4px; }}
.masthead .upd .zh {{ margin-left: 10px; }}
.nav a.cbc-btn {{ display: inline-flex; align-items: baseline; gap: 5px; background: var(--paper);
  border: 1px solid color-mix(in srgb, #d71920 40%, var(--line)); padding: 4px 12px; }}
.nav a.cbc-btn:hover {{ background: #d71920; border-color: #d71920; color: #fff; }}
.cbc-btn b {{ color: #d71920; font-weight: 800; letter-spacing: .03em; }}
.cbc-btn:hover b {{ color: inherit; }}
.nav .cbc-btn .zh {{ margin-left: 0; }}
body.m-zh .cbc-btn b {{ display: none; }}   /* "极简CBC" already says CBC */
.nav a.sox-btn {{ display: inline-flex; align-items: baseline; gap: 5px; background: var(--paper);
  border: 1px solid color-mix(in srgb, #2a78d6 40%, var(--line)); padding: 4px 12px; }}
.nav a.sox-btn:hover {{ background: #2a78d6; border-color: #2a78d6; color: #fff; }}
.sox-btn b {{ color: #2a78d6; font-weight: 800; letter-spacing: .03em; }}
.sox-btn:hover b {{ color: inherit; }}
.nav .sox-btn .zh {{ margin-left: 0; }}
.count {{ display: inline-block; min-width: 1.6em; margin-left: 8px; padding: 0 7px; border-radius: 999px;
  background: var(--accent-soft); color: var(--accent); font-size: 13px; font-weight: 700; text-align: center;
  vertical-align: middle; line-height: 1.7; font-family: -apple-system, "Segoe UI", sans-serif; }}
section {{ padding: 34px 0 4px; scroll-margin-top: 72px; }}
section h2 {{ font-size: 27px; font-weight: 800; margin: 0 0 14px; padding-left: 14px; line-height: 1.3;
  border-left: 5px solid var(--accent); letter-spacing: .01em; }}
section h2 .zh, h3.group .zh {{ margin-left: 10px; color: var(--muted); font-weight: 600; }}
h3.group {{ margin: 22px 0 8px; font-size: 18px; color: var(--accent); letter-spacing: .04em; }}
.list {{ display: flex; flex-direction: column; gap: 10px; }}
.item {{ background: var(--paper); border: 1px solid var(--line); border-radius: 16px; box-shadow: var(--shadow);
  overflow: hidden; transition: box-shadow .2s, border-color .2s; }}
.item:hover {{ box-shadow: var(--shadow-up); }}
.item[open] {{ border-color: color-mix(in srgb, var(--accent) 35%, var(--line)); box-shadow: var(--shadow-up); }}
.item.is-breaking {{ border-left: 5px solid var(--breaking); }}
.item.hide {{ display: none; }}
.item summary {{ list-style: none; display: flex; align-items: center; gap: 12px; padding: 14px 14px 14px 18px; cursor: pointer; }}
.item summary::-webkit-details-marker {{ display: none; }}
.item summary:hover {{ background: var(--hover); }}
.head {{ flex: 1; min-width: 0; }}
.chips {{ display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 4px; }}
.chip {{ font-size: 13px; font-weight: 700; padding: 1px 9px; border-radius: 999px; line-height: 1.6;
  background: color-mix(in srgb, currentColor 12%, transparent); }}
.t-politics {{ color: var(--politics); }} .t-finance {{ color: var(--finance); }} .t-sports, .league {{ color: var(--sports); }}
.t-tech {{ color: var(--tech); }} .t-breaking {{ color: var(--breaking); }}
.t-entertainment {{ color: var(--ent); }} .t-gossip {{ color: var(--gossip); }}
.t-military {{ color: var(--military); }} .t-nature {{ color: var(--nature); }} .t-art {{ color: var(--art); }}
.head .h {{ display: block; font-size: 21px; font-weight: 700; line-height: 1.45; }}
.head .zh.h {{ font-size: 18px; font-weight: 500; color: var(--muted); margin-top: 2px; }}
.speak {{ flex: none; width: 46px; height: 46px; border-radius: 50%; border: 0;
  background: var(--accent-soft); color: var(--accent); display: grid; place-items: center; cursor: pointer; padding: 0;
  transition: background .15s, color .15s; }}
.speak:hover {{ background: var(--accent); color: var(--accent-ink); }}
.speak svg {{ width: 24px; height: 24px; fill: currentColor; }}
.speak .i-pause, .speak .i-resume {{ display: none; }}
.speak.playing {{ background: var(--accent); color: var(--accent-ink); animation: pulse 1.4s ease-in-out infinite; }}
.speak.playing .i-play {{ display: none; }} .speak.playing .i-pause {{ display: block; }}
.speak.paused {{ background: var(--paper); box-shadow: inset 0 0 0 2px var(--accent); color: var(--accent); }}
.speak.paused .i-play {{ display: none; }} .speak.paused .i-resume {{ display: block; }}
.stopbtn {{ flex: none; width: 46px; height: 46px; border-radius: 50%; border: 1px solid var(--line);
  background: var(--paper); color: var(--ink); display: grid; place-items: center; cursor: pointer; padding: 0; }}
.stopbtn[hidden] {{ display: none; }}
.stopbtn:hover {{ border-color: var(--accent); color: var(--accent); }}
.stopbtn svg {{ width: 20px; height: 20px; fill: currentColor; }}
@media (prefers-reduced-motion: reduce) {{ .speak.playing {{ animation: none; }} }}
@keyframes pulse {{ 50% {{ box-shadow: 0 0 0 6px var(--accent-soft); }} }}
.chev {{ flex: none; width: 26px; height: 26px; color: var(--muted); transition: transform .2s; }}
.item[open] .chev {{ transform: rotate(180deg); color: var(--accent); }}
.item[open] summary {{ background: var(--hover); }}
.body {{ padding: 6px 76px 18px 18px; }}
.body .sum {{ margin: 0 0 12px; font-size: 19px; }}
.body p.zh.sum {{ color: var(--muted); font-size: 18px; }}
.src {{ padding-top: 10px; border-top: 1px dashed var(--line); font-size: 15px; color: var(--muted); }}
.src a {{ color: var(--accent); text-decoration: none; font-weight: 600; }} .src a:hover {{ text-decoration: underline; }}
/* language modes */
body.m-en .zh {{ display: none !important; }}
body.m-zh .en {{ display: none !important; }}
body.m-zh .head .zh.h {{ color: var(--ink); font-weight: 700; font-size: 21px; margin: 0; }}
body.m-zh .body p.zh.sum {{ color: var(--ink); font-size: 19px; }}
body.m-en .zh, body.m-zh .zh {{ margin-left: 0 !important; }}
.nav .zh, .tools .zh, .chip .zh, .src-label .zh, .masthead .upd .zh {{ opacity: .75; }}
#rate .zh {{ margin-left: 4px; font-size: 13px; }}
#rate button.on .zh {{ opacity: .85; }}
.voicebox {{ margin-top: 14px; border: 1px solid var(--line); border-radius: 14px; background: var(--paper); font-size: 16px; }}
.voicebox > summary {{ cursor: pointer; padding: 9px 16px; font-weight: 600; color: var(--muted); }}
.voicebox > summary .zh {{ margin-left: 6px; opacity: .75; }}
.vrows {{ display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 10px 10px; align-items: center; padding: 4px 16px 0; }}
.vrows label .zh {{ display: block; font-size: 13px; color: var(--muted); }}
.vrows select {{ min-width: 0; width: 100%; font: inherit; font-size: 15px; padding: 6px 8px; border-radius: 10px;
  border: 1px solid var(--line); background: var(--bg); color: var(--ink); }}
.vrows button {{ font: inherit; font-size: 15px; padding: 6px 14px; border-radius: 999px; border: 1px solid var(--line);
  background: var(--bg); color: var(--ink); cursor: pointer; white-space: nowrap; }}
.vrows button.playing {{ background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }}
.vrows button .zh {{ margin-left: 4px; }}
.voicebox .hint {{ margin: 10px 16px 12px; font-size: 14px; color: var(--muted); }}
.voicebox .hint .zh {{ display: block; margin-top: 4px; }}
.notice {{ margin-top: 12px; padding: 8px 12px; border-radius: 10px; background: var(--accent-soft); color: var(--accent); font-size: 15px; }}
.totop {{ position: fixed; z-index: 10; right: max(18px, env(safe-area-inset-right, 0px)); bottom: max(18px, env(safe-area-inset-bottom, 0px));
  width: 52px; height: 52px; border-radius: 50%; border: 0; padding: 0; cursor: pointer;
  display: grid; place-items: center; background: var(--accent); color: var(--accent-ink); box-shadow: var(--shadow-up);
  opacity: 0; visibility: hidden; transform: translateY(12px); transition: opacity .2s, transform .2s, visibility .2s; }}
.totop.show {{ opacity: 1; visibility: visible; transform: none; }}
.totop:hover {{ filter: brightness(1.08); }}
.totop:focus-visible {{ outline: 3px solid var(--accent-soft); outline-offset: 2px; }}
.totop svg {{ width: 26px; height: 26px; }}
footer {{ margin: 44px 0 0; padding: 22px 0 90px; border-top: 1px solid var(--line); color: var(--muted); font-size: 15px; }}
.archive {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }}
.archive a {{ color: var(--ink); background: var(--paper); border: 1px solid var(--line); border-radius: 999px; padding: 2px 12px; text-decoration: none; }}
.archive a:hover {{ border-color: var(--accent); color: var(--accent); }}
.archive a.cur {{ border-color: var(--accent); background: var(--accent-soft); color: var(--accent); }}
@media (max-width: 600px) {{
  .hero {{ margin-top: 28px; border-radius: 14px; }}
  .hero figcaption {{ position: static; padding: 8px 12px 10px; color: var(--muted); background: var(--paper);
    text-shadow: none; font-size: 14px; }}
  .hero figcaption .en {{ font-size: 15px; color: var(--ink); }}
  body {{ font-size: 18px; }}
  header.masthead {{ padding-block: 20px 18px; }}
  .ctrls, .tools .fold {{ margin-left: 0; }}
  .bar {{ position: static; }}   /* three rows of controls is too much to pin on a phone */
  body:not(.m-zh) .nav .zh {{ display: none; }}
  section h2 {{ font-size: 24px; }}
  .list {{ gap: 8px; }}
  .item {{ border-radius: 14px; }}
  .item summary {{ padding: 12px 10px 12px 14px; gap: 8px; }}
  .head .h {{ font-size: 19px; }}
  .head .zh.h {{ font-size: 16px; }}
  .chev {{ display: none; }}
  .body {{ padding: 4px 14px 16px; }}
  .totop {{ width: 48px; height: 48px; }}
}}
</style>
</head>
<body class="m-bi">
<header class="masthead">
  <div class="wrap mast-top">
    <img class="portrait" src="header-sketch.jpg" width="150" height="223" alt="">
    <div class="titles">
      <h1 class="brand">CLINT DAILY NEWS<small>每日新闻 · 中英双语</small></h1>
      <div class="date"><b>{date_en}</b> · <b>{date_zh}</b></div>
      <div class="date upd">{updated}</div>
    </div>
  </div>
</header>

<div class="bar"><div class="wrap">
  <nav class="nav">{nav}</nav>
  <div class="ctrls">
    <div class="seg" id="lang">
      <button data-m="bi" class="on">双语</button><button data-m="zh">中文</button><button data-m="en">EN</button>
    </div>
    <div class="seg" id="rate" role="group" aria-label="语速 Speed">
      <button data-r="1" class="on"><span class="en" lang="en">Normal</span><span class="zh" lang="zh">正常语速</span></button><button data-r="0.8"><span class="en" lang="en">Slower</span><span class="zh" lang="zh">稍慢语速</span></button>
    </div>
    <div class="seg" id="theme">
      <button data-t="auto" class="on">Auto</button><button data-t="light">☀</button><button data-t="dark">☾</button>
    </div>
  </div>
</div></div>

<main class="wrap">
  <div class="tools">
    <div class="filters" id="filters">{filters}</div>
    <div class="fold"><button id="expand">{expand}</button><button id="collapse">{collapse}</button></div>
  </div>
  <details class="voicebox">
    <summary><span class="en" lang="en">Voice settings</span><span class="zh" lang="zh">朗读设置</span></summary>
    <div class="vrows">
      <label for="v-en"><span class="en" lang="en">English voice</span><span class="zh" lang="zh">英文语音</span></label>
      <select id="v-en"><option value="">Auto 自动</option></select>
      <button type="button" data-test="en"><span class="en" lang="en">Test</span><span class="zh" lang="zh">试听</span></button>
      <label for="v-zh"><span class="en" lang="en">Chinese voice</span><span class="zh" lang="zh">中文语音</span></label>
      <select id="v-zh"><option value="">自动 Auto</option></select>
      <button type="button" data-test="zh"><span class="en" lang="en">Test</span><span class="zh" lang="zh">试听</span></button>
    </div>
    <p class="hint"><span class="en" lang="en">If a voice sounds odd, pick another and tap Test; your choice is remembered. On iPhone, download an Enhanced voice under Settings › Accessibility › Spoken Content › Voices.</span><span class="zh" lang="zh">声音奇怪时，换一个语音点"试听"，选好后自动记住。iPhone 可在 设置 › 辅助功能 › 朗读内容 › 声音 里下载"增强音质"语音，效果更自然。</span></p>
  </details>
  <div class="notice" id="notice" hidden>Text-to-speech is not supported in this browser. · 此浏览器不支持语音朗读</div>
  {sections}
  <figure class="hero">
    <img src="hero-goose-eagle.jpg" srcset="hero-goose-eagle-800.jpg 800w, hero-goose-eagle.jpg 1600w"
         sizes="(max-width: 920px) 100vw, 888px" width="1600" height="683" loading="lazy"
         alt="A Canada goose with wings spread honks at a bald eagle on snowy ice">
    <figcaption><span class="en" lang="en">Standoff on the ice: a Canada goose takes on a bald eagle</span><span class="zh" lang="zh">冰上对峙：加拿大雁硬刚白头海雕</span></figcaption>
  </figure>
  <footer>
    <div>{archive_label}</div>
    <div class="archive">{archive}</div>
    <p>Summaries compiled by AI from public reporting; check original sources for details. · 新闻摘要由AI根据公开报道整理，请以原始来源为准。</p>
  </footer>
</main>

<button type="button" id="totop" class="totop" aria-label="回到顶部 Back to top" title="回到顶部 Back to top">
  <svg viewBox="0 0 24 24"><path d="M12 19V6M5.5 11.5 12 5l6.5 6.5" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
</button>

<script>
(function () {{
  // localStorage can be unavailable (private mode, sandboxed previews); keep an
  // in-memory copy so choices still apply for this visit.
  var mem = {{}};
  var store = {{
    get: function (k) {{ try {{ var v = localStorage.getItem(k); if (v !== null) return v; }} catch (e) {{}} return k in mem ? mem[k] : null; }},
    set: function (k, v) {{ mem[k] = v; try {{ localStorage.setItem(k, v); }} catch (e) {{}} }}
  }};
  var mode = "bi";
  function seg(id, attr, apply) {{
    var box = document.getElementById(id), btns = box.querySelectorAll("button");
    function pick(v) {{
      btns.forEach(function (b) {{ b.classList.toggle("on", b.getAttribute(attr) === v); }});
      apply(v); store.set("dn-" + id, v);
    }}
    btns.forEach(function (b) {{ b.onclick = function () {{ pick(b.getAttribute(attr)); }}; }});
    var saved = store.get("dn-" + id);
    if (saved && box.querySelector("[" + attr + '="' + saved + '"]')) pick(saved);
  }}
  seg("lang", "data-m", function (m) {{ mode = m; document.body.className = "m-" + m; stop(); }});
  seg("theme", "data-t", function (t) {{
    if (t === "auto") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", t);
  }});

  var items = document.querySelectorAll(".item");
  var fbtns = document.querySelectorAll("#filters button");
  fbtns.forEach(function (b) {{
    b.onclick = function () {{
      var f = b.dataset.f;
      fbtns.forEach(function (x) {{ x.classList.toggle("on", x === b); }});
      items.forEach(function (c) {{
        c.classList.toggle("hide", f !== "all" && c.dataset.tags.split(" ").indexOf(f) < 0);
      }});
    }};
  }});
  var totop = document.getElementById("totop");
  function onScroll() {{ totop.classList.toggle("show", window.scrollY > 300); }}
  window.addEventListener("scroll", onScroll, {{ passive: true }});
  onScroll();
  totop.onclick = function () {{
    var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({{ top: 0, behavior: still ? "auto" : "smooth" }});
  }};

  document.getElementById("expand").onclick = function () {{ items.forEach(function (i) {{ i.open = true; }}); }};
  document.getElementById("collapse").onclick = function () {{ items.forEach(function (i) {{ i.open = false; }}); }};

  // ---- Listen (text-to-speech) ----
  var tts = window.speechSynthesis, voices = [], current = null;
  // Phones ship joke/robotic voices (iOS "Albert", "Bubbles", "Eddy"...) and
  // Cantonese voices under "zh"; taking the first match is what made playback
  // sound distorted on mobile. Score voices instead and let the user override.
  var NOVELTY = /\\b(albert|bad news|bahh|bells|boing|bubbles|cellos|good news|jester|organ|superstar|trinoids|whisper|wobble|zarvox|deranged|hysterical|junior|ralph|fred|kathy|grandma|grandpa|eddy|flo|reed|rocko|sandy|shelley|agnes|bruce|vicki|princess)\\b/i;
  var GOOD = {{
    zh: /tingting|ting-ting|lili|yu-shu|meijia|xiaoxiao|yunxi|huihui|普通话|mandarin|google/i,
    en: /samantha|ava|allison|susan|zoe|alex|daniel|karen|serena|aria|jenny|guy|google us|google uk/i
  }};
  function norm(l) {{ return (l || "").replace(/_/g, "-").toLowerCase(); }}
  function family(v) {{
    var l = norm(v.lang);
    return /^(zh|cmn|yue)/.test(l) ? "zh" : /^en/.test(l) ? "en" : "";
  }}
  function score(v, fam) {{
    var l = norm(v.lang), s;
    if (fam === "zh") s = /^(zh-cn|zh-hans|cmn)/.test(l) ? 100 : /^zh-tw/.test(l) ? 40 : /^(zh-hk|yue)/.test(l) ? 5 : 20;
    else s = l === "en-us" ? 100 : /^en-(gb|ca|au)/.test(l) ? 80 : 40;
    if (NOVELTY.test(v.name)) s -= 200;
    if (GOOD[fam].test(v.name)) s += 30;
    if (/enhanced|premium|natural|neural|增强|高音质/i.test(v.name)) s += 20;
    if (v.default) s += 3;
    return s;
  }}
  function ranked(fam) {{
    return voices.filter(function (v) {{ return family(v) === fam; }})
      .sort(function (a, b) {{ return score(b, fam) - score(a, fam); }});
  }}
  function voiceFor(fam) {{
    var uri = store.get("dn-voice-" + fam);
    var list = ranked(fam);
    if (uri) {{ var m = list.filter(function (v) {{ return v.voiceURI === uri; }})[0]; if (m) return m; }}
    return list[0] && score(list[0], fam) > 0 ? list[0] : null;
  }}
  function fillSelect(fam) {{
    var sel = document.getElementById("v-" + fam), saved = store.get("dn-voice-" + fam) || "";
    sel.innerHTML = "";
    sel.add(new Option(fam === "zh" ? "自动 Auto" : "Auto 自动", ""));
    ranked(fam).forEach(function (v) {{ sel.add(new Option(v.name + " (" + v.lang + ")", v.voiceURI)); }});
    sel.value = saved;
    if (sel.value !== saved) sel.value = "";
  }}
  function loadVoices() {{
    voices = tts ? tts.getVoices() : [];
    if (voices.length) {{ fillSelect("en"); fillSelect("zh"); }}
  }}
  if (tts) {{ loadVoices(); tts.addEventListener ? tts.addEventListener("voiceschanged", loadVoices) : (tts.onvoiceschanged = loadVoices); }}
  ["en", "zh"].forEach(function (fam) {{
    document.getElementById("v-" + fam).onchange = function () {{ store.set("dn-voice-" + fam, this.value); }};
  }});
  // Speed: "Normal" (1.0) or "Slower" (0.8). A change applies from the next sentence.
  var rate = 1;
  seg("rate", "data-r", function (r) {{ rate = parseFloat(r) || 1; }});
  // Speech engines read "1–1" as "one dash one" (English) or "十" (Chinese).
  // Rewrite dashes between numbers into words before speaking.
  function spoken(text, fam) {{
    var zh = fam === "zh";
    // records like 3-4-2 (wins-losses-OT)
    text = text.replace(/(^|[^\\d.,])(\\d{{1,2}})[-–—](\\d{{1,2}})[-–—](\\d{{1,2}})(?!\\d|\\.\\d)/g,
      zh ? "$1$2、$3、$4" : "$1$2, $3, $4");
    // season/year ranges like 2026–27
    text = text.replace(/(\\d{{4}})\\s*[-–—]\\s*(\\d{{2,4}})(?!\\d)/g, zh ? "$1至$2" : "$1 to $2");
    // percentage ranges like 4.5%–5%
    text = text.replace(/(\\d%?)\\s*[-–—]\\s*(\\d+(?:\\.\\d+)?%)/g, zh ? "$1至$2" : "$1 to $2");
    // scores like 1–1, 34–31 (in Chinese, date ranges like 20–21日 read as 至)
    text = text.replace(/(^|[^\\d.,])(\\d{{1,3}})\\s*[-–—]\\s*(\\d{{1,3}})(?!\\d|\\.\\d|%)/g,
      function (m, pre, a, b, off, str) {{
        if (!zh) return pre + a + " to " + b;
        return pre + a + (/[日号月年时点岁]/.test(str.charAt(off + m.length)) ? "至" : "比") + b;
      }});
    return text;
  }}
  // Long utterances get cut off in some browsers, so speak sentence by sentence.
  function chunks(text) {{
    return text.split(/(?<=[。！？!?；;])\\s*|(?<=[a-z0-9%)]\\.)\\s+/)
      .reduce(function (out, s) {{ s = s.trim(); if (s) out.push(s); return out; }}, []);
  }}
  // Playback state. Sentences are spoken one at a time so pause/resume can be
  // done by cancelling and restarting from the current sentence: the built-in
  // speechSynthesis.pause() is unreliable on Android.
  var play = null;   // {{ btn, stopBtn, queue, idx, paused }}
  var gen = 0;       // bumps on every cancel so stale end/error events are ignored
  var LABELS = {{ idle: "朗读 Listen", playing: "暂停 Pause", paused: "继续 Resume" }};
  function setState(btn, state) {{
    btn.classList.toggle("playing", state === "playing");
    btn.classList.toggle("paused", state === "paused");
    if (btn.classList.contains("speak")) {{ btn.title = LABELS[state]; btn.setAttribute("aria-label", LABELS[state]); }}
    var sb = play && play.btn === btn ? play.stopBtn : null;
    if (sb) sb.hidden = state === "idle";
  }}
  function stop() {{
    gen++;
    if (tts) tts.cancel();
    if (play) {{ var p = play; setState(p.btn, "idle"); play = null; }}
  }}
  function next() {{
    if (!play || play.paused) return;
    if (play.idx >= play.queue.length) {{ stop(); return; }}
    var my = ++gen, q = play.queue[play.idx];
    var u = new SpeechSynthesisUtterance(q[1]), v = voiceFor(q[0]);
    if (v) {{ u.voice = v; u.lang = v.lang; }} else u.lang = q[0] === "zh" ? "zh-CN" : "en-US";
    u.rate = rate; u.pitch = 1;
    u.onend = function () {{ if (my !== gen || !play) return; play.idx++; next(); }};
    u.onerror = function (e) {{
      if (my !== gen || !play || e.error === "interrupted" || e.error === "canceled") return;
      play.idx++; next();
    }};
    play.u = u;   // keep a reference so the browser doesn't drop the end event
    tts.speak(u);
  }}
  // parts: [["en"|"zh", text], ...], spoken in order.
  function start(btn, parts) {{
    stop();
    if (!voices.length) loadVoices();
    var queue = [];
    parts.forEach(function (p) {{ chunks(spoken(p[1], p[0])).forEach(function (c) {{ queue.push([p[0], c]); }}); }});
    var item = btn.closest(".item");
    play = {{ btn: btn, stopBtn: item ? item.querySelector(".stopbtn") : null, queue: queue, idx: 0, paused: false }};
    setState(btn, "playing");
    next();
  }}
  function pause() {{
    play.paused = true; gen++; tts.cancel();
    setState(play.btn, "paused");
  }}
  function resume() {{
    play.paused = false;
    setState(play.btn, "playing");
    next();   // restarts the sentence that was interrupted
  }}
  function partsFor(item) {{
    var parts = [];
    // Bilingual mode reads English first, then Chinese (for listening practice).
    if (mode !== "zh") parts.push(["en", item.dataset.ten + ". " + item.dataset.sen]);
    if (mode !== "en") parts.push(["zh", item.dataset.tzh + "。" + item.dataset.szh]);
    return parts;
  }}
  function supported() {{
    if (tts) return true;
    document.getElementById("notice").hidden = false;
    return false;
  }}
  document.querySelectorAll(".speak").forEach(function (btn) {{
    btn.addEventListener("click", function (e) {{
      e.preventDefault(); e.stopPropagation();   // don't toggle the <details>
      if (!supported()) return;
      if (play && play.btn === btn) {{ play.paused ? resume() : pause(); }}
      else start(btn, partsFor(btn.closest(".item")));
    }});
  }});
  document.querySelectorAll(".stopbtn").forEach(function (btn) {{
    btn.addEventListener("click", function (e) {{ e.preventDefault(); e.stopPropagation(); stop(); }});
  }});
  var SAMPLE = {{ en: "Good morning. Here is today's news.", zh: "早上好，这是今天的新闻。" }};
  document.querySelectorAll("[data-test]").forEach(function (btn) {{
    btn.onclick = function () {{
      if (!supported()) return;
      if (play && play.btn === btn) stop();
      else start(btn, [[btn.dataset.test, SAMPLE[btn.dataset.test]]]);
    }};
  }});
  window.addEventListener("beforeunload", stop);
}})();
</script>
</body>
</html>
"""


def main():
    days = {}
    # Daily issues only (data/cbc-zh.json is cbc.py's translation cache).
    for p in sorted(DATA.glob("????-??-??.json")):
        days[p.stem] = json.loads(p.read_text(encoding="utf-8"))
    if not days:
        raise SystemExit("no data/*.json found")
    SITE.mkdir(exist_ok=True)
    (SITE / ".nojekyll").touch()
    for key, day in days.items():
        html = render_page(day, days.keys())
        (SITE / f"{key}.html").write_text(html, encoding="utf-8")
        print("wrote", SITE / f"{key}.html")
    latest = max(days)
    (SITE / "index.html").write_text((SITE / f"{latest}.html").read_text(encoding="utf-8"), encoding="utf-8")
    print("wrote", SITE / "index.html", "->", latest)
    write_artifact(SITE / f"{latest}.html")


def write_artifact(page):
    """Write build/artifact.html: the latest page in the claude.ai Artifact format.

    The Artifact host supplies <html>/<head>/<body> itself, so strip ours and
    keep a stable title (the date is shown on the page).
    """
    html = page.read_text(encoding="utf-8")
    head_end = html.index("<title>")
    html = '<meta name="claude:viewport-fit-sides" content="cover">\n' + html[head_end:]
    html = re.sub(r"<title>.*?</title>", "<title>每日新闻 Daily News</title>", html, count=1)
    html = html.replace('</head>\n<body class="m-bi">\n', "").replace("</body>\n</html>\n", "")
    out = ROOT / "build" / "artifact.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
