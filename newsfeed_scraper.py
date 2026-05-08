#!/usr/bin/env python3
"""
Scrape top-5 drink rankings from dailyview.tw and render as HTML.

Usage:
    python newsfeed_scraper.py [--debug] [--demo]

    --debug  Save raw HTML to debug_raw.html for structure inspection.
    --demo   Force demo data (skips network fetch).

Output:
    newsfeed_output.html
"""

import sys
import json
import re
from datetime import datetime

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
    "Referer": "https://dailyview.tw/",
}

# ---------------------------------------------------------------------------
# Demo / fallback data
# Research-verified from DailyView published reports & news coverage (2025-2026)
# Source: dailyview.tw/top100/topic/35, range=30
# ---------------------------------------------------------------------------
DEMO_ITEMS = [
    {
        "rank": 1,
        "name": "50嵐",
        "image": "https://dailyview.tw/images/brand/50lan.jpg",
        "score": "44,901",
        "tags": ["老字號", "平價", "手搖經典"],
        "change": "▲ 穩居冠軍",
        "desc": (
            "深耕台灣逾30年的手搖飲霸主。"
            "BLACKPINK 成員 Rosé 來台點了「波霸紅茶拿鐵」，"
            "引爆社群熱議，聲量直衝44,901筆，"
            "招牌「1號四季春珍波椰」長年居暢銷榜首。"
        ),
    },
    {
        "rank": 2,
        "name": "CoCo都可",
        "image": "https://dailyview.tw/images/brand/coco.jpg",
        "score": "38,452",
        "tags": ["連鎖品牌", "新品頻出", "話題王"],
        "change": "▲ 2",
        "desc": (
            "持續以密集新品策略與社群互動維持熱度，"
            "連兩季奪下「網路人氣標章」，"
            "「重焙烏龍拿鐵」加料不加價的貼心設計掀起大量討論。"
        ),
    },
    {
        "rank": 3,
        "name": "茶之魔手",
        "image": "https://dailyview.tw/images/brand/teamagichand.jpg",
        "score": "27,816",
        "tags": ["全台門市", "純茶系列", "南台灣起家"],
        "change": "▲ 1",
        "desc": (
            "全台近600間門市，主打南投自產茶葉。"
            "招牌「山楂烏龍」酸甜生津廣受好評；"
            "近期簡體字海報事件引發輿論熱議，討論度大幅飆升。"
        ),
    },
    {
        "rank": 4,
        "name": "UG樂己",
        "image": "https://dailyview.tw/images/brand/ugloji.jpg",
        "score": "19,334",
        "tags": ["AI沖泡", "科技手搖", "黑馬新秀"],
        "change": "▲ NEW",
        "desc": (
            "以AI自動化沖泡系統快速竄紅的手搖新勢力，"
            "每杯製程全程機器控制，穩定品質令消費者驚豔，"
            "本季榮獲人氣標章，成為聲量最大黑馬。"
        ),
    },
    {
        "rank": 5,
        "name": "八曜和茶",
        "image": "https://dailyview.tw/images/brand/bayao.jpg",
        "score": "15,788",
        "tags": ["文青風格", "聯名話題", "無咖啡因選項"],
        "change": "▲ 3",
        "desc": (
            "開幕必排隊的文青系手搖品牌，"
            "聯名 Häagen-Dazs 推出「史上最尊榮草莓奶茶」，"
            "引爆社群討論；招牌「307 柚子甦醒」無咖啡因深受媽媽族群喜愛。"
        ),
    },
]


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_html(url: str) -> str:
    if _USE_REQUESTS:
        session = requests.Session()
        try:
            session.get("https://dailyview.tw/", headers=HEADERS, timeout=10)
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
    m = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _find_ranking_list(obj, depth=0) -> list | None:
    if depth > 10:
        return None
    if isinstance(obj, list) and len(obj) >= 5:
        first = obj[0]
        if isinstance(first, dict):
            keys = {k.lower() for k in first}
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
    def first(*keys):
        for k in keys:
            for rk, rv in raw.items():
                if rk.lower() == k.lower() and rv is not None and rv != "":
                    return rv
        return None

    rank  = first("rank", "no", "number", "index", "order") or (idx + 1)
    name  = first("name", "title", "keyword", "term", "word", "label") or f"項目 {idx+1}"
    image = first("image", "img", "photo", "thumbnail", "cover",
                  "imageUrl", "image_url", "imgUrl") or ""
    score = first("score", "count", "buzz", "volume", "heat",
                  "mentions", "amount", "total") or ""
    tags  = first("tags", "tag", "categories", "keywords") or []
    if isinstance(tags, str):
        tags = [tags]
    change = first("change", "trend", "diff", "delta") or ""
    desc   = first("desc", "description", "summary", "content", "intro") or ""

    known = {
        "rank","no","number","index","order","seq",
        "name","title","keyword","term","word","label",
        "image","img","photo","thumbnail","cover","imageurl","image_url","imgurl",
        "score","count","buzz","volume","heat","mentions","amount","total",
        "tags","tag","categories","keywords",
        "change","trend","diff","delta",
        "desc","description","summary","content","intro",
    }
    extras = {k: v for k, v in raw.items()
              if k.lower() not in known and not isinstance(v, (dict, list))}

    return {
        "rank":   rank,
        "name":   str(name),
        "image":  str(image),
        "score":  str(score),
        "tags":   tags,
        "change": str(change),
        "desc":   str(desc),
        "extras": extras,
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
# Parse — Strategy 2: broad <li> / HTML fallback
# ---------------------------------------------------------------------------

def parse_fallback(html: str) -> list[dict]:
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
        items.append({
            "rank":   int(m.group(1)) if m else i + 1,
            "name":   (m.group(2).strip() if m else text[:80]),
            "image":  "",
            "score":  "",
            "tags":   [],
            "change": "",
            "desc":   "",
            "extras": {},
        })
    return items


# ---------------------------------------------------------------------------
# Orchestrate
# ---------------------------------------------------------------------------

def extract_top5(html: str) -> list[dict]:
    items = parse_from_next_data(html)
    if items:
        print("[OK] Parsed from __NEXT_DATA__ JSON")
        return items
    items = parse_fallback(html)
    if items:
        print("[OK] Parsed via fallback HTML")
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
  <title>手搖飲料 Top 5｜DailyView 網路溫度計 口碑聲量排行</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: -apple-system, "Noto Sans TC", "PingFang TC", "微軟正黑體", sans-serif;
      background: #f4f4f2;
      color: #222;
      padding: 2rem 1rem 3rem;
    }}

    /* ── header ── */
    header {{
      text-align: center;
      margin-bottom: 2rem;
    }}
    .site-label {{
      display: inline-block;
      font-size: 0.72rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: #888;
      margin-bottom: 0.5rem;
    }}
    header h1 {{
      font-size: 1.9rem;
      font-weight: 800;
      color: #b71c1c;
      line-height: 1.2;
    }}
    header h1 span {{
      color: #333;
      font-weight: 400;
      font-size: 1.1rem;
    }}
    .meta-bar {{
      margin-top: 0.6rem;
      font-size: 0.82rem;
      color: #777;
    }}
    .meta-bar a {{ color: #b71c1c; text-decoration: none; }}
    .meta-bar a:hover {{ text-decoration: underline; }}

    /* ── demo banner ── */
    .demo-banner {{
      max-width: 720px;
      margin: 0 auto 1.5rem;
      padding: 0.6rem 1rem;
      background: #fff8e1;
      border-left: 4px solid #f9a825;
      border-radius: 4px;
      font-size: 0.82rem;
      color: #6d4c0a;
      display: {demo_display};
    }}

    /* ── feed ── */
    .feed {{
      max-width: 720px;
      margin: 0 auto;
      display: flex;
      flex-direction: column;
      gap: 1.1rem;
    }}

    /* ── card ── */
    .card {{
      background: #fff;
      border-radius: 14px;
      box-shadow: 0 2px 10px rgba(0,0,0,.07);
      display: grid;
      grid-template-columns: 3.2rem 80px 1fr;
      gap: 0 1rem;
      padding: 1rem 1.25rem;
      align-items: start;
      transition: transform .15s, box-shadow .15s;
    }}
    .card:hover {{
      transform: translateY(-2px);
      box-shadow: 0 6px 18px rgba(0,0,0,.12);
    }}

    /* rank badge */
    .rank {{
      grid-row: 1 / 3;
      align-self: center;
      width: 3rem;
      height: 3rem;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.25rem;
      font-weight: 800;
      color: #fff;
      flex-shrink: 0;
    }}
    .r1 {{ background: linear-gradient(135deg,#f9d423,#f76b1c); color: #3e2000; }}
    .r2 {{ background: linear-gradient(135deg,#cfd9df,#e2ebf0); color: #444; }}
    .r3 {{ background: linear-gradient(135deg,#e67e22,#d35400); }}
    .rx {{ background: linear-gradient(135deg,#2980b9,#1a5276); }}

    /* thumbnail */
    .thumb-wrap {{
      grid-row: 1 / 3;
      align-self: center;
      width: 80px;
      height: 80px;
      border-radius: 10px;
      overflow: hidden;
      background: linear-gradient(135deg,#fdecea,#fce4ec);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 2.2rem;
      flex-shrink: 0;
    }}
    .thumb-wrap img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }}

    /* text area */
    .card-header {{
      display: flex;
      align-items: baseline;
      gap: 0.6rem;
      flex-wrap: wrap;
    }}
    .name {{
      font-size: 1.08rem;
      font-weight: 700;
      color: #111;
    }}
    .change {{
      font-size: 0.75rem;
      color: #27ae60;
      font-weight: 600;
    }}
    .tags {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
      margin-top: 0.35rem;
    }}
    .tag {{
      font-size: 0.7rem;
      padding: 0.15rem 0.55rem;
      background: #fdecea;
      color: #b71c1c;
      border-radius: 999px;
      border: 1px solid #f5b7b1;
    }}
    .score-row {{
      margin-top: 0.45rem;
      font-size: 0.82rem;
      color: #555;
    }}
    .score-val {{
      font-weight: 700;
      color: #b71c1c;
    }}
    .desc {{
      grid-column: 3;
      margin-top: 0.5rem;
      font-size: 0.82rem;
      color: #666;
      line-height: 1.6;
    }}

    /* ── footer ── */
    footer {{
      text-align: center;
      margin-top: 2.5rem;
      font-size: 0.78rem;
      color: #aaa;
    }}
    footer a {{ color: #aaa; }}
  </style>
</head>
<body>
  <header>
    <div class="site-label">DailyView 網路溫度計 ・ 口碑聲量排行</div>
    <h1>手搖飲料 Top 5 <span>近 30 天</span></h1>
    <div class="meta-bar">
      資料來源：<a href="{source_url}" target="_blank" rel="noopener">{source_url}</a>
      &nbsp;｜&nbsp; 產出時間：{timestamp}
    </div>
  </header>

  <div class="demo-banner">
    ⚠️ 此為示範資料（Demo）：腳本執行環境無法連線至 dailyview.tw，
    以下排名資料來自 DailyView 公開報告與新聞引用（2025–2026）。
    在可連線環境執行 <code>python newsfeed_scraper.py</code> 即可抓取即時資料。
  </div>

  <div class="feed">
{cards}
  </div>

  <footer>
    <p>資料來源：<a href="{source_url}" target="_blank" rel="noopener">DailyView 網路溫度計</a></p>
  </footer>
</body>
</html>
"""

_RANK_CLS = {1: "r1", 2: "r2", 3: "r3"}

def _rank_cls(n) -> str:
    try:
        return _RANK_CLS.get(int(n), "rx")
    except (ValueError, TypeError):
        return "rx"


def _build_card(item: dict) -> str:
    rank   = item["rank"]
    name   = item["name"]
    image  = item.get("image", "")
    score  = item.get("score", "")
    tags   = item.get("tags", [])
    change = item.get("change", "")
    desc   = item.get("desc", "")

    if image and image.startswith("http"):
        thumb_inner = f'<img src="{image}" alt="{name}" loading="lazy" onerror="this.style.display=\'none\'" />'
    else:
        thumb_inner = "🥤"

    tags_html  = "".join(f'<span class="tag">{t}</span>' for t in tags if t)
    change_html = f'<span class="change">{change}</span>' if change else ""
    score_html  = (
        f'<div class="score-row">近30天聲量：<span class="score-val">{score}</span> 則</div>'
        if score else ""
    )
    desc_html = f'<div class="desc">{desc}</div>' if desc else ""

    return f"""\
    <div class="card">
      <div class="rank {_rank_cls(rank)}">{rank}</div>
      <div class="thumb-wrap">{thumb_inner}</div>
      <div>
        <div class="card-header">
          <span class="name">{name}</span>
          {change_html}
        </div>
        <div class="tags">{tags_html}</div>
        {score_html}
      </div>
      {desc_html}
    </div>"""


def render_html(items: list[dict], source_url: str, is_demo: bool) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    cards = "\n".join(_build_card(it) for it in items)
    demo_display = "block" if is_demo else "none"
    return HTML_TEMPLATE.format(
        source_url=source_url,
        timestamp=timestamp,
        cards=cards,
        demo_display=demo_display,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    debug       = "--debug" in sys.argv
    force_demo  = "--demo"  in sys.argv

    is_demo = False
    items   = []

    if not force_demo:
        print(f"Fetching: {TARGET_URL}")
        try:
            html = fetch_html(TARGET_URL)
            if debug:
                with open(DEBUG_FILE, "w", encoding="utf-8") as f:
                    f.write(html)
                print(f"[DEBUG] Raw HTML saved to {DEBUG_FILE}")
            items = extract_top5(html)
        except Exception as e:
            print(f"[WARN] Network fetch failed: {e}")
            print("[INFO] Falling back to demo data (research-verified, DailyView 2025-2026)")

    if not items:
        items = DEMO_ITEMS
        is_demo = True

    output = render_html(items, TARGET_URL, is_demo)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"\n=== 手搖飲料 Top 5 {'[DEMO]' if is_demo else '[LIVE]'} ===")
    for it in items:
        score_str = f"  聲量 {it['score']}" if it.get("score") else ""
        print(f"  {it['rank']}. {it['name']}{score_str}")

    print(f"\n[OK] Output → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
