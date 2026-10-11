"""釣割（chowari.jp）から各船宿の釣果を集める。

使い方:
  python scripts/collect.py                 # 今日を基準に直近35日（5週） + 前年同時期を取得
  python scripts/collect.py --date 2026-10-16

出力: data/raw/<基準日>.json
"""
import argparse
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://www.chowari.jp"
UA = {"User-Agent": "Mozilla/5.0 (tsuri-report weekly; personal use)"}
WAIT = 0.6  # 先方サーバーに負担をかけないための間隔（秒）

ITEM_RE = re.compile(r'<li data-ship="(\d+)" data-choka="(\d+)" class="catch_item.*?(?=<li data-ship=|</ul>\s*<div|\Z)', re.S)
DATE_RE = re.compile(r'catch_item_date">釣行日：(\d{4})年(\d{1,2})月(\d{1,2})日（.）\s*([^<]*)<')
FISH_RE = re.compile(r'<tr>\s*<th><h2>(.*?)</h2></th>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*</tr>', re.S)
COMMENT_RE = re.compile(r'catch_item_comment_txt">(.*?)<span', re.S)
NUM_RE = re.compile(r'([\d.]+)')


def get(url):
    for i in range(3):
        try:
            b = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()
            try:
                return b.decode("utf-8")
            except UnicodeDecodeError:
                return b.decode("cp932", "replace")
        except Exception as e:  # noqa: BLE001
            if i == 2:
                print(f"  ! 取得失敗 {url}: {e}", file=sys.stderr)
                return ""
            time.sleep(3)


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s))).strip()


def parse_range(s):
    """'20～115匹' -> (20, 115, '匹')。数字がなければ None。"""
    s = clean(s)
    nums = [float(x) for x in NUM_RE.findall(s.replace(",", ""))]
    if not nums:
        return None
    m = re.search(r"(匹|本|枚|杯|尾|kg|ｋｇ|個)", s)
    unit = m.group(1) if m else ""
    return (nums[0], nums[-1], unit)


def parse_page(text, ship_id):
    out = []
    for m in ITEM_RE.finditer(text):
        block = m.group(0)
        d = DATE_RE.search(block)
        if not d:
            continue
        fish = []
        for f in FISH_RE.finditer(block):
            cnt = parse_range(f.group(3))
            size = parse_range(f.group(2))
            fish.append({
                "name": clean(f.group(1)),
                "size": clean(f.group(2)),
                "count": clean(f.group(3)),
                "min": cnt[0] if cnt else None,
                "max": cnt[1] if cnt else None,
                "unit": cnt[2] if cnt else "",
                "size_max": size[1] if size else None,
            })
        c = COMMENT_RE.search(block)
        out.append({
            "ship_id": ship_id,
            "choka_id": m.group(2),
            "date": f"{int(d.group(1)):04d}-{int(d.group(2)):02d}-{int(d.group(3)):02d}",
            "tide": d.group(4).strip(),
            "fish": fish,
            "comment": clean(c.group(1)) if c else "",
        })
    return out


def fetch_ship(ship_id, since, until, dt_param=None, max_pages=8):
    """since〜until（両端含む）の釣果を新しい順にページを辿って取る。"""
    res = []
    for page in range(1, max_pages + 1):
        q = []
        if dt_param:
            q.append(f"dt={dt_param}")
        if page > 1:
            q.append(f"page={page}")
        url = f"{BASE}/ship/{ship_id}/catch/" + ("?" + "&".join(q) if q else "")
        items = parse_page(get(url), ship_id)
        time.sleep(WAIT)
        if not items:
            break
        res += [it for it in items if since <= it["date"] <= until]
        if min(it["date"] for it in items) < since:
            break
    return res


# ---- 船宿の公式サイト（羽田かみや・かめだや等が使っている釣果ブログ形式） ----
BLOG_RE = re.compile(r'<div class="blog">(.*?)(?=<div class="blog">|<div id="links-right"|\Z)', re.S)
BLOG_FISH_RE = re.compile(r'<span class="fish-name">(.*?)</span>.*?<span class="fish-num">(.*?)</span>\s*<br\s*/?>(?:\s*<span class="fish-comment">(.*?)</span>)?', re.S)
RANGE_RE = re.compile(r'(\d+(?:\.\d+)?)\s*[-～~]\s*(\d+(?:\.\d+)?)\s*(匹|本|枚|杯|尾|cm|kg)')
SINGLE_RE = re.compile(r'(\d+(?:\.\d+)?)\s*(匹|本|枚|杯|尾|cm|kg)')


def _ranges(txt):
    txt = clean(txt).replace("ｃｍ", "cm").replace("ｋｇ", "kg")
    out = {"size": None, "count": None}
    for a, b, u in RANGE_RE.findall(txt):
        out["size" if u in ("cm", "kg") else "count"] = (float(a), float(b), u)
    if out["count"] is None:
        for a, u in SINGLE_RE.findall(txt):
            if u not in ("cm", "kg"):
                out["count"] = (float(a), float(a), u)
    return out, txt


def parse_blog(text, ship_id):
    out = []
    for m in BLOG_RE.finditer(text):
        block = m.group(1)
        d = re.search(r'<h2 class="date">(\d{4})年(\d{1,2})月(\d{1,2})日</h2>', block)
        if not d:
            continue
        title = clean((re.search(r'<h3 class="title">(.*?)</h3>', block, re.S) or [None, ""])[1])
        fish, notes = [], []
        for f in BLOG_FISH_RE.finditer(block):
            r, txt = _ranges(f.group(2))
            c, z = r["count"], r["size"]
            fish.append({"name": clean(f.group(1)), "size": f"{z[0]:g}-{z[1]:g}{z[2]}" if z else "",
                         "count": f"{c[0]:g}～{c[1]:g}{c[2]}" if c else txt,
                         "min": c[0] if c else None, "max": c[1] if c else None, "unit": c[2] if c else "",
                         "size_max": z[1] if z else None})
            if f.group(3):
                notes.append(clean(f.group(3)))
        fish = [f for f in fish if f["min"] is not None]
        if not fish:  # 休船・出船予定の記事は除く
            continue
        body = block.split("船長コメント", 1)[-1]
        body = clean(re.sub(r"<br\s*/?>", " ", body))
        body = re.sub(r"^：?\s*釣り座別釣果表.*?ご覧下さい！\s*", "", body)
        out.append({"ship_id": ship_id, "choka_id": "", "title": title,
                    "date": f"{int(d.group(1)):04d}-{int(d.group(2)):02d}-{int(d.group(3)):02d}", "tide": "",
                    "fish": fish, "comment": (" / ".join(notes) + " " + body)[:400].strip()})
    return out


def fetch_blog(base, ship_id, since, until):
    """日ごとの過去記事ページ（/search/Archive/YYYYMMDD/）を1日ずつ取る。"""
    res = []
    day = dt.date.fromisoformat(since)
    while day.isoformat() <= until:
        res += [it for it in parse_blog(get(f"{base}/search/Archive/{day:%Y%m%d}/"), ship_id) if it["date"] == day.isoformat()]
        time.sleep(WAIT)
        day += dt.timedelta(days=1)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="基準日 YYYY-MM-DD（省略時は今日）")
    ap.add_argument("--days", type=int, default=35)
    ap.add_argument("--no-lastyear", action="store_true")
    ap.add_argument("--merge", action="store_true", help="既存の data/raw/<日付>.json に無い船宿だけ取得して足す")
    a = ap.parse_args()

    base = dt.date.fromisoformat(a.date) if a.date else dt.date.today()
    since = (base - dt.timedelta(days=a.days - 1)).isoformat()
    until = base.isoformat()
    # 前年同時期: 前年の同じ日付の前後7日
    ly = base.replace(year=base.year - 1)
    ly_since = (ly - dt.timedelta(days=7)).isoformat()
    ly_until = (ly + dt.timedelta(days=7)).isoformat()
    ly_months = sorted({ly_since[2:7].replace("-", ""), ly_until[2:7].replace("-", "")}, reverse=True)

    cfg = json.loads((ROOT / "config" / "ports.json").read_text(encoding="utf-8"))
    p = ROOT / "data" / "raw" / f"{until}.json"
    have = {}
    if a.merge and p.exists():
        for g in json.loads(p.read_text(encoding="utf-8"))["groups"]:
            for s in g["ships"]:
                have[s["id"]] = s
    out = {"base_date": until, "since": since, "lastyear": [ly_since, ly_until], "groups": []}
    for g in cfg["groups"]:
        print(f"[{g['name']}] {len(g['ships'])}軒", file=sys.stderr)
        ships = []
        for s in g["ships"]:
            if s["id"] in have:
                ships.append({**have[s["id"]], **s})
                continue
            if s.get("source") == "blog":
                cur = fetch_blog(s["base"], s["id"], since, until)
                last = fetch_blog(s["base"], s["id"], ly_since, ly_until) if (cur and not a.no_lastyear) else []
                url = s.get("url") or f"{s['base']}/category/Choka/"
            else:
                cur = fetch_ship(s["id"], since, until)
                last = []
                if not a.no_lastyear and cur:  # 今期に釣果がある船宿だけ前年も見る
                    for ym in ly_months:
                        last += fetch_ship(s["id"], ly_since, ly_until, dt_param=ym)
                url = f"{BASE}/ship/{s['id']}/catch/"
            print(f"  {s['name']}: 今期{len(cur)}件 前年{len(last)}件", file=sys.stderr)
            ships.append({**s, "url": url, "catches": cur, "lastyear": last})
        out["groups"].append({"name": g["name"], "ships": ships})

    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved {p}", file=sys.stderr)


if __name__ == "__main__":
    main()
