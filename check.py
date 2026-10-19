"""Check a daily data file before publishing.

Usage: python check.py data/YYYY-MM-DD.json
Prints ERROR lines (must fix) and WARN lines (try to fix), then a summary.
Exit code 1 if there are errors.
"""

import json
import sys
from urllib.parse import urlparse

# id -> (min items, target items)
SECTIONS = {
    "canada": (10, 10),
    "gta": (10, 10),
    "usa": (10, 10),
    "europe": (10, 10),
    "asia": (10, 10),
    "china": (10, 10),
    "sports": (6, 10),
    "entertainment": (2, 6),
}
TAGS = {"politics", "military", "finance", "sports", "tech", "breaking",
        "nature", "art", "entertainment", "gossip"}
LEAGUES = {"EPL", "LaLiga", "UCL", "ATP", "WTA", "NBA", "NFL", "NHL", "MLB"}


def items_of(section):
    if "groups" in section:
        return [i for g in section["groups"] for i in g["items"]]
    return section.get("items", [])


def main(path):
    errors, warns = [], []
    d = json.load(open(path, encoding="utf-8"))
    ids = [s.get("id") for s in d.get("sections", [])]
    if ids != list(SECTIONS):
        errors.append(f"section ids/order {ids} != {list(SECTIONS)}")

    titles, outlets_all = {}, set()
    for s in d.get("sections", []):
        sid = s.get("id")
        items = items_of(s)
        lo, _ = SECTIONS.get(sid, (0, 0))
        if len(items) < lo:
            warns.append(f"{sid}: {len(items)} items, target {lo}")
        outlets = set()
        for n, it in enumerate(items, 1):
            where = f"{sid}[{n}]"
            for k in ("title", "summary"):
                for lang in ("zh", "en"):
                    if not it.get(k, {}).get(lang, "").strip():
                        errors.append(f"{where}: missing {k}.{lang}")
            en_words = len(it.get("summary", {}).get("en", "").split())
            zh_chars = len("".join(it.get("summary", {}).get("zh", "").split()))
            if en_words < 90 or zh_chars < 180:
                warns.append(f"{where}: summary short ({en_words} en words, {zh_chars} zh chars; "
                             "target 110-160 / 220-320)")
            bad = set(it.get("tags", [])) - TAGS
            if bad or not it.get("tags"):
                errors.append(f"{where}: bad/empty tags {sorted(bad) or it.get('tags')}")
            if sid == "sports":
                if it.get("league") not in LEAGUES:
                    errors.append(f"{where}: league must be one of {sorted(LEAGUES)}")
                if "sports" not in it.get("tags", []):
                    errors.append(f"{where}: sports item needs the 'sports' tag")
            srcs = it.get("sources", [])
            if not srcs:
                errors.append(f"{where}: no sources")
            for src in srcs:
                u = urlparse(src.get("url", ""))
                if u.scheme not in ("http", "https") or not u.netloc:
                    errors.append(f"{where}: bad url {src.get('url')!r}")
                elif u.path.strip("/") == "":
                    errors.append(f"{where}: url is a homepage {src['url']}")
                outlets.add(u.netloc.removeprefix("www."))
            key = it.get("title", {}).get("en", "").lower()
            if key in titles:
                errors.append(f"{where}: duplicate of {titles[key]}")
            titles[key] = where
        if sid in ("canada", "gta", "usa", "europe", "asia", "china") and len(outlets) < 4:
            warns.append(f"{sid}: only {len(outlets)} distinct outlets {sorted(outlets)}")
        outlets_all |= outlets

    if "entertainment" in ids:
        ent = d["sections"][ids.index("entertainment")]
        if len(ent.get("groups", [])) != 2:
            errors.append("entertainment: needs two groups (Entertainment, Gossip)")

    for e in errors:
        print("ERROR", e)
    for w in warns:
        print("WARN ", w)
    total = sum(len(items_of(s)) for s in d.get("sections", []))
    print(f"{total} items, {len(outlets_all)} distinct outlets, "
          f"{len(errors)} errors, {len(warns)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
