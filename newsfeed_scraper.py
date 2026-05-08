#!/usr/bin/env python3
"""
Scrape top-5 drink rankings from dailyview.tw and render as HTML.

Usage:
    python newsfeed_scraper.py [--debug]

    --debug  Save raw HTML to debug_raw.html for structure inspection.

Output:
    newsfeed_output.html  — Styled HTML page with top-5 ranked drinks.
"""

import sys
import json
import re
import os
from html.parser import HTMLParser

try:
    import requests
    _USE_REQUESTS = True
except ImportError:
    import urllib.request
    import urllib.error
    _USE_REQUESTS = False

TARGET_URL = "https://dailyview.tw/top100/topic/35?range=30"
OUTPUT_FILE = "newsfeed_output.html"
DEBUG_FILE = "debug_raw.html"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://dailyview.tw/",
    "Connection": "keep-alive",
}


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_html(url: str) -> str:
    if _USE_REQUESTS:
        session = requests.Session()
        # Warm up with a homepage visit
        try:
            session.get("https://dailyview.tw/", headers=HEADERS, timeout=15)
        except Exception:
            pass
        resp = session.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.text
    else:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            charset = r.headers.get_content_charset() or "utf-8"
            return r.read().decode(charset, errors="replace")


# ---------------------------------------------------------------------------
# Parse — Strategy 1: __NEXT_DATA__ JSON (Next.js)
# ---------------------------------------------------------------------------

def _extract_next_data(html: str) -> dict | None:
    m = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
                  html, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _find_ranking_list(obj, depth=0) -> list | None:
    """Recursively search for a list of objects that look like ranking items."""
    if depth > 10:
        return None
    if isinstance(obj, list) and len(obj) >= 5:
        first = obj[0]
        if isinstance(first, dict):
            keys = {k.lower() for k in first}
            # Accept if the item has name-like and rank-like keys
            has_name = any(k in keys for k in ("name", "title", "keyword", "term", "word"))
            has_rank = any(k in keys for k in ("rank", "no", "number", "index", "order", "seq"))
            if has_name or has_rank:
                return obj
    if isinstance(obj, dict):
        for v in obj.values():
            result = _find_ranking_list(v, depth + 1)
            if result:
                return result
    if isinstance(obj, list):
        for item in obj:
            result = _find_ranking_list(item, depth + 1)
            if result:
                return result
    return None


def _normalise_item(raw: dict, idx: int) -> dict:
    """Map arbitrary key names to a consistent schema."""
    def first(*keys):
        for k in keys:
            for rk, rv in raw.items():
                if rk.lower() == k.lower() and rv is not None and rv != "":
                    return rv
        return None

    rank = first("rank", "no", "number", "index", "order", "seq") or (idx + 1)
    name = first("name", "title", "keyword", "term", "word", "label") or f"項目 {idx+1}"
    image = first("image", "img", "photo", "picture", "thumbnail", "cover",
                  "imageUrl", "image_url", "imgUrl", "img_url", "coverImage") or ""
    score = first("score", "count", "buzz", "volume", "heat", "views",
                  "mentions", "amount", "total", "value") or ""
    tags = first("tags", "tag", "categories", "category", "keywords") or []
    if isinstance(tags, str):
        tags = [tags]
    change = first("change", "trend", "diff", "delta", "movement") or ""

    # Collect any remaining fields as extras
    known = {"rank", "no", "number", "index", "order", "seq",
              "name", "title", "keyword", "term", "word", "label",
              "image", "img", "photo", "picture", "thumbnail", "cover",
              "imageur", "image_url", "imgurl", "img_url", "coverimage",
              "score", "count", "buzz", "volume", "heat", "views",
              "mentions", "amount", "total", "value",
              "tags", "tag", "categories", "category", "keywords",
              "change", "trend", "diff", "delta", "movement"}
    extras = {k: v for k, v in raw.items()
              if k.lower() not in known and not isinstance(v, (dict, list))}

    return {
        "rank": rank,
        "name": str(name),
        "image": str(image),
        "score": str(score),
        "tags": tags,
        "change": str(change),
        "extras": extras,
        "raw": raw,
    }


def parse_from_next_data(html: str) -> list[dict]:
    data = _extract_next_data(html)
    if not data:
        return []
    items = _find_ranking_list(data)
    if not items:
        return []
    return [_normalise_item(it, i) for i, it in enumerate(items[:5])]


# ---------------------------------------------------------------------------
# Parse — Strategy 2: HTML structural patterns
# ---------------------------------------------------------------------------

class RankingParser(HTMLParser):
    """Best-effort HTML parser for common ranking-list structures."""

    # Tags that likely wrap a single ranked item
    CONTAINER_CLASSES = {
        "top100-item", "ranking-item", "rank-item", "list-item",
        "item-card", "rank-card", "item-wrap", "item-wrapper",
        "rankItem", "topItem",
    }

    def __init__(self):
        super().__init__()
        self._items: list[dict] = []
        self._stack: list[dict] = []   # [{tag, attrs, text_parts, children}]
        self._in_item: bool = False
        self._item_depth: int = 0
        self._depth: int = 0

    # -- helpers --

    @staticmethod
    def _classes(attrs) -> set[str]:
        for name, val in attrs:
            if name == "class" and val:
                return set(val.split())
        return set()

    @staticmethod
    def _attr(attrs, key) -> str:
        for name, val in attrs:
            if name == key:
                return val or ""
        return ""

    # -- handlers --

    def handle_starttag(self, tag, attrs):
        self._depth += 1
        classes = self._classes(attrs)

        # Detect item container start
        if not self._in_item and classes & self.CONTAINER_CLASSES:
            self._in_item = True
            self._item_depth = self._depth
            self._stack = [{"tag": tag, "attrs": attrs,
                            "text": [], "children": []}]
            return

        if self._in_item:
            frame = {"tag": tag, "attrs": attrs, "text": [], "children": []}
            self._stack.append(frame)

            # Capture image src inline
            if tag == "img":
                src = self._attr(attrs, "src") or self._attr(attrs, "data-src")
                if src:
                    self._stack[0].setdefault("_images", []).append(src)

    def handle_endtag(self, tag):
        if self._in_item:
            if self._stack:
                frame = self._stack.pop()
                text = " ".join("".join(frame["text"]).split())
                if text and len(self._stack) > 0:
                    self._stack[-1]["children"].append(
                        {"tag": frame["tag"], "text": text,
                         "attrs": frame["attrs"]}
                    )

            if self._depth == self._item_depth:
                # End of container
                self._in_item = False
                if self._stack:
                    root = self._stack[0]
                    self._items.append(root)
                    self._stack = []
        self._depth -= 1

    def handle_data(self, data):
        if self._in_item and self._stack:
            self._stack[-1]["text"].append(data)

    # -- post-process --

    def get_items(self) -> list[dict]:
        results = []
        for i, root in enumerate(self._items[:5]):
            texts = self._collect_texts(root)
            rank = i + 1
            name = texts[0] if texts else f"項目 {i+1}"
            image = (root.get("_images") or [""])[0]
            score = ""
            for t in texts[1:]:
                if re.search(r"[\d,]+", t):
                    score = t
                    break
            results.append({
                "rank": rank,
                "name": name,
                "image": image,
                "score": score,
                "tags": [],
                "change": "",
                "extras": {},
                "raw": {},
            })
        return results

    def _collect_texts(self, frame: dict) -> list[str]:
        out = []
        t = " ".join("".join(frame.get("text", [])).split())
        if t:
            out.append(t)
        for child in frame.get("children", []):
            out.append(child.get("text", ""))
        return [x for x in out if x]


def parse_from_html(html: str) -> list[dict]:
    parser = RankingParser()
    parser.feed(html)
    return parser.get_items()


# ---------------------------------------------------------------------------
# Parse — Strategy 3: Broad text extraction fallback
# ---------------------------------------------------------------------------

def parse_fallback(html: str) -> list[dict]:
    """
    Very broad fallback: look for numbered list patterns (1. 2. 3. …)
    or ordered list <li> sequences with substantial text.
    """
    # Try to find <li> elements with rank-like content
    li_texts = re.findall(r"<li[^>]*>(.*?)</li>", html, re.DOTALL)
    candidates = []
    for lt in li_texts:
        text = re.sub(r"<[^>]+>", " ", lt)
        text = " ".join(text.split())
        if len(text) > 3:
            candidates.append(text)

    items = []
    for i, text in enumerate(candidates[:5]):
        m = re.match(r"^(\d+)[.\s、](.+)", text)
        if m:
            items.append({"rank": int(m.group(1)), "name": m.group(2).strip(),
                          "image": "", "score": "", "tags": [],
                          "change": "", "extras": {}, "raw": {}})
        else:
            items.append({"rank": i + 1, "name": text[:80],
                          "image": "", "score": "", "tags": [],
                          "change": "", "extras": {}, "raw": {}})
    return items


# ---------------------------------------------------------------------------
# Orchestrate parsing
# ---------------------------------------------------------------------------

def extract_top5(html: str) -> list[dict]:
    items = parse_from_next_data(html)
    if items:
        print("[OK] Parsed from __NEXT_DATA__ JSON")
        return items

    items = parse_from_html(html)
    if items:
        print("[OK] Parsed from HTML structural patterns")
        return items

    items = parse_fallback(html)
    if items:
        print("[OK] Parsed via broad text fallback")
        return items

    return []


# ---------------------------------------------------------------------------
# Render HTML
# ---------------------------------------------------------------------------

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>熱門飲料 Top 5｜DailyView 網路溫度計</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: -apple-system, "Noto Sans TC", "微軟正黑體", sans-serif;
      background: #f5f5f5;
      color: #222;
      padding: 2rem 1rem;
    }}

    header {{
      text-align: center;
      margin-bottom: 2rem;
    }}
    header h1 {{
      font-size: 1.8rem;
      font-weight: 700;
      color: #c0392b;
    }}
    header p {{
      font-size: 0.9rem;
      color: #666;
      margin-top: 0.4rem;
    }}

    .feed {{
      max-width: 720px;
      margin: 0 auto;
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }}

    .card {{
      background: #fff;
      border-radius: 12px;
      box-shadow: 0 2px 8px rgba(0,0,0,.08);
      display: flex;
      align-items: center;
      gap: 1rem;
      padding: 1rem 1.25rem;
      transition: box-shadow .2s;
    }}
    .card:hover {{ box-shadow: 0 4px 16px rgba(0,0,0,.14); }}

    .rank {{
      flex-shrink: 0;
      width: 2.4rem;
      height: 2.4rem;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.1rem;
      font-weight: 800;
      color: #fff;
    }}
    .rank-1 {{ background: #f1c40f; color: #7d6608; }}
    .rank-2 {{ background: #bdc3c7; color: #555; }}
    .rank-3 {{ background: #e67e22; }}
    .rank-other {{ background: #2980b9; }}

    .thumb {{
      flex-shrink: 0;
      width: 72px;
      height: 72px;
      border-radius: 8px;
      object-fit: cover;
      background: #eee;
    }}
    .thumb-placeholder {{
      flex-shrink: 0;
      width: 72px;
      height: 72px;
      border-radius: 8px;
      background: linear-gradient(135deg, #f8c8c8, #f4e2e2);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 2rem;
    }}

    .info {{ flex: 1; min-width: 0; }}
    .name {{
      font-size: 1.05rem;
      font-weight: 600;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.4rem;
      margin-top: 0.4rem;
      align-items: center;
    }}
    .score {{
      font-size: 0.82rem;
      color: #c0392b;
      font-weight: 600;
    }}
    .change {{
      font-size: 0.78rem;
      color: #27ae60;
    }}
    .tag {{
      font-size: 0.72rem;
      padding: 0.15rem 0.5rem;
      background: #fdecea;
      color: #c0392b;
      border-radius: 999px;
      border: 1px solid #f5b7b1;
    }}

    .extras {{
      margin-top: 0.5rem;
      font-size: 0.78rem;
      color: #888;
    }}
    .extras span {{ margin-right: 0.8rem; }}

    footer {{
      text-align: center;
      margin-top: 2.5rem;
      font-size: 0.8rem;
      color: #aaa;
    }}
    footer a {{ color: #aaa; }}
  </style>
</head>
<body>
  <header>
    <h1>熱門飲料 Top 5</h1>
    <p>資料來源：<a href="{source_url}" target="_blank" rel="noopener">DailyView 網路溫度計</a>　｜　近 30 天聲量排行</p>
  </header>

  <div class="feed">
{cards}
  </div>

  <footer>
    <p>資料抓取時間：{timestamp}　｜　<a href="{source_url}" target="_blank" rel="noopener">{source_url}</a></p>
  </footer>
</body>
</html>
"""

RANK_CLASS = {1: "rank-1", 2: "rank-2", 3: "rank-3"}


def _rank_class(n) -> str:
    try:
        return RANK_CLASS.get(int(n), "rank-other")
    except (ValueError, TypeError):
        return "rank-other"


def _build_card(item: dict) -> str:
    rank = item["rank"]
    name = item["name"]
    image = item.get("image", "")
    score = item.get("score", "")
    tags = item.get("tags", [])
    change = item.get("change", "")
    extras = item.get("extras", {})

    rank_cls = _rank_class(rank)

    if image and image.startswith("http"):
        thumb = f'<img class="thumb" src="{image}" alt="{name}" loading="lazy" />'
    else:
        thumb = '<div class="thumb-placeholder">🥤</div>'

    score_html = f'<span class="score">聲量 {score}</span>' if score else ""
    change_html = f'<span class="change">{change}</span>' if change else ""
    tags_html = "".join(f'<span class="tag">{t}</span>' for t in tags if t)

    extras_html = ""
    if extras:
        parts = "".join(
            f'<span>{k}：{v}</span>' for k, v in list(extras.items())[:4]
        )
        extras_html = f'<div class="extras">{parts}</div>'

    return f"""\
    <div class="card">
      <div class="rank {rank_cls}">{rank}</div>
      {thumb}
      <div class="info">
        <div class="name">{name}</div>
        <div class="meta">{score_html}{change_html}{tags_html}</div>
        {extras_html}
      </div>
    </div>"""


def render_html(items: list[dict], source_url: str) -> str:
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    cards = "\n".join(_build_card(it) for it in items)
    return HTML_TEMPLATE.format(
        source_url=source_url,
        timestamp=timestamp,
        cards=cards,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    debug = "--debug" in sys.argv

    print(f"Fetching: {TARGET_URL}")
    try:
        html = fetch_html(TARGET_URL)
    except Exception as e:
        sys.exit(f"[ERROR] Failed to fetch page: {e}")

    if debug:
        with open(DEBUG_FILE, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[DEBUG] Raw HTML saved to {DEBUG_FILE}")

    items = extract_top5(html)

    if not items:
        msg = (
            "[ERROR] Could not extract ranking items.\n"
            "Try running with --debug to inspect the raw HTML,\n"
            f"then open {DEBUG_FILE} to identify the correct selectors."
        )
        sys.exit(msg)

    output = render_html(items, TARGET_URL)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"\n=== Top 5 飲料排行 ===")
    for it in items:
        score_str = f"  聲量 {it['score']}" if it["score"] else ""
        print(f"  {it['rank']}. {it['name']}{score_str}")

    print(f"\n[OK] HTML output written to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
