"""釣割（chowari.jp）から各船宿の釣果を集める。

使い方:
  python scripts/collect.py                 # 今日を基準に直近35日（5週） + 前年同時期を取得
  python scripts/collect.py --date 2026-10-16

出力: data/raw/<基準日>.json
"""
import argparse
import unicodedata
import urllib.parse
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


STATS = {"ok": 0, "fail": 0}


def get(url, tries=3, wait=3):
    for i in range(tries):
        try:
            b = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()
            STATS["ok"] += 1
            try:
                return b.decode("utf-8")
            except UnicodeDecodeError:
                return b.decode("cp932", "replace")
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                STATS["fail"] += 1
                print(f"  ! 取得失敗 {url}: {e}", file=sys.stderr)
                return ""
            time.sleep(wait * (i + 1))


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


# ---- 釣りビジョン（釣割に無い船宿用） ----
FV_BOX_RE = re.compile(r'<div class="choka_box">(.*?)(?=<div class="choka_box">|<div class="pager|\Z)', re.S)


def fetch_fv(sid, ship_id, since, until, max_pages=6):
    """釣りビジョンの船宿ページ（choka_detail.php?s=ID）から日ごとの釣果を取る。"""
    out = []
    for page in range(1, max_pages + 1):
        t = get(f"https://www.fishing-v.jp/choka/choka_detail.php?s={sid}&pageID={page}")
        time.sleep(WAIT)
        boxes = FV_BOX_RE.findall(t)
        if not boxes:
            break
        oldest = None
        for b in boxes:
            d = re.search(r'<li class="date">(\d{4})年(\d{1,2})月(\d{1,2})日', b)
            if not d:
                continue
            day = f"{int(d.group(1)):04d}-{int(d.group(2)):02d}-{int(d.group(3)):02d}"
            oldest = day if (oldest is None or day < oldest) else oldest
            if not (since <= day <= until):
                continue
            fish = []
            for row in re.findall(r"<tr>\s*<td><span class=\"choka_number\">\d+</span></td>(.*?)</tr>", b, re.S):
                tds = [clean(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
                if len(tds) < 3 or not tds[0]:
                    continue
                r, _ = _ranges(tds[1] + " " + tds[2])
                c, z = r["count"], r["size"]
                fish.append({"name": tds[0], "size": tds[2], "count": tds[1],
                             "min": c[0] if c else None, "max": c[1] if c else None, "unit": c[2] if c else "",
                             "size_max": z[1] if z else None})
            fish = [f for f in fish if f["min"] is not None]
            if not fish:
                continue
            com = " ".join(clean(x) for x in re.findall(r'<div class="choka_comment">(.*?)</div>', b, re.S))
            out.append({"ship_id": ship_id, "choka_id": "", "date": day, "tide": "", "fish": fish,
                        "comment": re.sub(r"^\d+", "", com)[:400]})
        if oldest and oldest < since:
            break
    return out


# ---- 船宿の公式サイト（日付と「魚種 ○～○匹 ○～○kg」が並ぶ日記形式。那珂湊かもめ丸など） ----
def fetch_diary(url, ship_id, since, until):
    """年の表記がない日記形式。月が基準日より先なら前年とみなす。"""
    t = get(url)
    t = re.sub(r"<br\s*/?>", "\n", t)
    t = re.sub(r"<[^>]+>", "\n", t)
    t = unicodedata.normalize("NFKC", html.unescape(t))
    lines = [l.strip() for l in t.split("\n") if l.strip()]
    base = dt.date.fromisoformat(until)
    out, cur = [], None
    for l in lines:
        m = re.match(r"^(\d{1,2})月(\d{1,2})日", l)
        if m:
            mo, da = int(m.group(1)), int(m.group(2))
            yr = base.year if mo <= base.month else base.year - 1
            try:
                cur = {"ship_id": ship_id, "choka_id": "", "date": dt.date(yr, mo, da).isoformat(), "tide": "", "fish": [], "comment": ""}
            except ValueError:
                cur = None
                continue
            out.append(cur)
            continue
        if cur is None:
            continue
        f = re.match(r"^([ァ-ヶー一-龠]+)\s*(\d+)\s*[～~-]\s*(\d+)\s*(匹|杯|ハイ|本|枚)(?:\s*([\d.]+)\s*[～~-]\s*([\d.]+)\s*[kK])?", l)
        if f:
            unit = "杯" if f.group(4) == "ハイ" else f.group(4)
            cur["fish"].append({"name": f.group(1), "count": f"{f.group(2)}～{f.group(3)}{unit}",
                                "size": f"{f.group(5)}～{f.group(6)}kg" if f.group(5) else "",
                                "min": float(f.group(2)), "max": float(f.group(3)), "unit": unit,
                                "size_max": float(f.group(6)) if f.group(6) else None})
        elif len(cur["comment"]) < 300:
            cur["comment"] = (cur["comment"] + " " + l).strip()
    return [x for x in out if x["fish"] and since <= x["date"] <= until]


# ---- 那珂湊 岡重丸の釣果ページ（最新10件のみ。過去分はさかのぼれない） ----
def fetch_okaju(url, ship_id, since, until):
    t = get(url)
    out = []
    for blk in re.split(r"<dt>", t)[1:]:
        txt = unicodedata.normalize("NFKC", clean(re.sub(r"<br\s*/?>", " ", blk)))
        txt = re.sub(r"(\d)・(\d)", r"\1.\2", txt)  # 0・3 → 0.3
        post = re.search(r"投稿日\s*:\s*(\d{4})/(\d{1,2})/(\d{1,2})", txt)
        if not post:
            continue
        kind = re.search(r"釣り物\s*[:：]\s*(\S+)\s*(?:(\d{1,2})月(\d{1,2})日)?", txt)
        res = re.search(r"釣果\s*[:：]\s*(\d+)\s*[～~-]\s*(\d+)\s*(尾|匹|杯|本|枚)\s*(?:([\d.]+)\s*[～~-]\s*([\d.]+)\s*kg)?", txt)
        if not kind or not res:
            continue
        y = int(post.group(1))
        if kind.group(2):
            mo, da = int(kind.group(2)), int(kind.group(3))
            if mo > int(post.group(2)):
                y -= 1
        else:
            mo, da = int(post.group(2)), int(post.group(3))
        day = dt.date(y, mo, da).isoformat()
        if not (since <= day <= until):
            continue
        unit = "杯" if ("タコ" in kind.group(1) or "ダコ" in kind.group(1)) else ("匹" if res.group(3) == "尾" else res.group(3))
        tail = re.split(r"水深\s*[:：]\s*\S+", txt)
        out.append({"ship_id": ship_id, "choka_id": "", "date": day, "tide": "",
                    "fish": [{"name": kind.group(1), "count": f"{res.group(1)}～{res.group(2)}{unit}",
                              "size": f"{res.group(4)}～{res.group(5)}kg" if res.group(4) else "",
                              "min": float(res.group(1)), "max": float(res.group(2)), "unit": unit,
                              "size_max": float(res.group(5)) if res.group(5) else None}],
                    "comment": (tail[-1].split("[管理用]")[0].strip() if len(tail) > 1 else "")[:300]})
    return out


# ---- 陸っぱり・施設 ----
YFP_API = "https://iqqdsybr6beovaix6btxwykuha.appsync-api.ap-northeast-1.amazonaws.com/graphql"
YFP_KEY = "da2-of4bzmdi4vhjha5buiog37mki4"  # 横浜フィッシングピアーズの公式サイトが閲覧用に公開しているキー
YFP_NAMES = {"daikoku": "大黒", "isogo": "磯子", "honmoku": "本牧"}


def fetch_yfp(fac, since, until):
    """横浜の海づり施設（大黒・磯子・本牧）の日ごとの最終釣果。"""
    q = (ROOT / "config" / "yfp_query.graphql").read_text(encoding="utf-8")
    out, token = [], None
    while True:
        v = {"facility": fac, "date": {"between": [since.replace("-", "/"), until.replace("-", "/")]},
             "sortDirection": "DESC", "limit": 50}
        if token:
            v["nextToken"] = token
        req = urllib.request.Request(YFP_API, data=json.dumps({"query": q, "variables": v}).encode(),
                                     headers={"Content-Type": "application/json", "x-api-key": YFP_KEY,
                                              "Origin": "https://yokohama-fishingpiers.jp", **UA})
        try:
            r = json.loads(urllib.request.urlopen(req, timeout=30).read())["data"]["lastPostsByFacilityAndDate"]
        except Exception as e:  # noqa: BLE001
            print(f"  ! 取得失敗 {fac}: {e}", file=sys.stderr)
            break
        for it in r["items"]:
            fish = []
            for n in range(1, 31):
                name = it.get(f"fish{n}Name")
                if not name:
                    continue
                fish.append({"name": name, "count": it.get(f"fish{n}Count"), "unit": it.get(f"fish{n}Unit") or "",
                             "size_min": it.get(f"fish{n}MinSize"), "size_max": it.get(f"fish{n}MaxSize"),
                             "place": it.get(f"fish{n}Place") or []})
            out.append({"date": it["date"].replace("/", "-"), "facility": YFP_NAMES.get(fac, fac),
                        "visitors": it.get("visitors"), "water": it.get("waterTemp"), "fish": fish,
                        "comment": clean(it.get("sentence") or "")[:400]})
        token = r.get("nextToken")
        if not token:
            break
        time.sleep(WAIT)
    return out


def fetch_uosoku(place, since, until, max_pages=8):
    """ウオスク（釣果まとめ）の釣り場検索。日付・魚種・釣り方・情報元・リンク。"""
    out = []
    for page in range(1, max_pages + 1):
        t = get(f"https://plus.uosoku.com/search?lo={urllib.parse.quote(place)}&page={page}")
        time.sleep(WAIT)
        blocks = re.split(r"<div class='srb'", t)[1:]
        if not blocks:
            break
        oldest = None
        for b in blocks:
            d = re.search(r"<span class='c_el'[^>]*>(\d{4}-\d{2}-\d{2})</span>", b)
            if not d:
                continue
            d = d.group(1)
            oldest = d if (oldest is None or d < oldest) else oldest
            if not (since <= d <= until):
                continue
            pts = re.search(r"関連ポイント[:：](.*?)</span>", b, re.S)
            if not pts or place not in clean(pts.group(1)):  # 検索結果に混じる別の釣り場を除く
                continue
            link = re.search(r"(?:data-href|href)='(https?://[^']+)'[^>]*>([^<]+)</a>", b)
            fish = re.search(r"関連魚種[:：]\s*([^<]*)</span>", b)
            how = re.search(r"釣り方[:：]\s*([^<]*)</span>", b)
            src = re.search(r"情報元[:：]\s*([^<]*)</span>", b)
            out.append({"date": d, "title": clean(link.group(2)) if link else "", "url": html.unescape(link.group(1)) if link else "",
                        "source": clean(src.group(1)) if src else "",
                        "fish": [{"name": f} for f in (fish.group(1).split() if fish else [])],
                        "method": clean(how.group(1)) if how else ""})
        if oldest and oldest < since:
            break
    return out


def release_sentences(body, limit=3):
    """「放流」を含む部分を、前後の文の区切り（句読点・絵文字）までで切り出す。"""
    def is_break(ch):
        o = ord(ch)
        return ch in "。！!？?\n♪☆★" or 0x2600 <= o <= 0x27BF or 0xFE00 <= o <= 0xFE0F or o >= 0x1F000  # 句読点と絵文字だけを区切りにする
    out = []
    for m in re.finditer("放流", body):
        a = m.start()
        while a > 0 and m.start() - a < 60 and not is_break(body[a - 1]):
            a -= 1
        b = m.end()
        while b < len(body) and b - m.end() < 80 and not is_break(body[b]):
            b += 1
        t = body[a:b].strip(" 　")
        if t and t not in out:
            out.append(t)
        if len(out) >= limit:
            break
    return out


UMC_BASE = "http://xn--nbk4em1stb5747d2j8b.com"  # 海釣りセンター.com（九十九里海釣りセンター）
UMC_FISH = ["マダイ", "シマアジ", "ショゴ", "ワカシ", "イナダ", "ワラサ", "ブリ", "カンパチ", "ヒラマサ", "ヒラメ", "カレイ", "イシガレイ",
            "イシダイ", "イシガキダイ", "ニザダイ", "クロダイ", "メジナ", "イサキ", "アジ", "サバ", "ソイ", "クロソイ", "アイナメ", "カサゴ",
            "ウマヅラ", "カワハギ", "スズキ", "サーモン", "ギンザケ", "トラウト", "イセエビ", "伊勢海老", "ハタ", "マハタ", "キジハタ", "カマス", "イワシ"]


def fetch_umc(since, until):
    """九十九里海釣りセンターの日ごとの釣果記事（魚種と天気・水温・コメント。匹数は無い）。"""
    lst = get(f"{UMC_BASE}/choca/")
    links = sorted(set(re.findall(r'href="(http://xn--nbk4em1stb5747d2j8b\.com/choca/(\d{4})/(\d{2})/(\d{2})/\d+/)"', lst)))
    out = []
    for href, y, m, d in links:
        day = f"{y}-{m}-{d}"
        if not (since <= day <= until):
            continue
        t = clean(re.sub(r"<br\s*/?>", " ", get(href)))
        time.sleep(WAIT)
        body = t.split("の釣果", 2)[-1]
        body = body.split("この釣果・ブログが良かったと思ったら")[0]
        names, rest = [], body
        for f in sorted(UMC_FISH, key=len, reverse=True):  # 長い名前から先に取る（シマアジの中のアジを拾わない）
            if f in rest:
                names.append("イセエビ" if f == "伊勢海老" else f)
                rest = rest.replace(f, "　")
        names.sort(key=lambda n: body.find(n) if n in body else 999)
        water = re.search(r"水温\s*([\d.]+)", body)
        release = release_sentences(body)  # 放流は好調の材料として拾う
        out.append({"date": day, "url": href, "fish": [{"name": n} for n in dict.fromkeys(names)],
                    "water": float(water.group(1)) if water else None, "comment": body[:400].strip(), "release": release})
    return out


# ---- 週末の海況予報（Open-Meteo。キー不要） ----
WDIR = ["北", "北東", "東", "南東", "南", "南西", "西", "北西"]


def moon_age(day):
    """その日の正午（JST）の月齢。基準: 2000-01-06 18:14 UTC の新月。"""
    t = dt.datetime(day.year, day.month, day.day, 3, 0)  # 12:00 JST = 03:00 UTC
    ref = dt.datetime(2000, 1, 6, 18, 14)
    return ((t - ref).total_seconds() / 86400) % 29.530588853


def tide_name(age):
    a = int(round(age)) % 30
    if a in (0, 1, 2, 14, 15, 16, 17, 29):
        return "大潮"
    if a in (7, 8, 9, 22, 23, 24):
        return "小潮"
    if a in (10, 25):
        return "長潮"
    if a in (11, 26):
        return "若潮"
    return "中潮"


def weekend_days(base):
    """基準日以降の最初の土日。"""
    sat = base + dt.timedelta(days=(5 - base.weekday()) % 7)
    if base.weekday() == 6:  # 日曜に実行したらその日だけ
        return [base]
    return [sat, sat + dt.timedelta(days=1)]


def fetch_forecast(base):
    pts = json.loads((ROOT / "config" / "forecast_points.json").read_text(encoding="utf-8"))
    days = weekend_days(base)
    d0, d1 = days[0].isoformat(), days[-1].isoformat()
    out = {"days": [d.isoformat() for d in days], "tide": {d.isoformat(): tide_name(moon_age(d)) for d in days},
           "moon_age": {d.isoformat(): round(moon_age(d), 1) for d in days}, "areas": {}, "points": pts}
    for name, (la, lo) in pts.items():
        try:
            m = json.loads(get(f"https://marine-api.open-meteo.com/v1/marine?latitude={la}&longitude={lo}"
                               f"&daily=wave_height_max,swell_wave_height_max,swell_wave_period_max"
                               f"&hourly=sea_level_height_msl&timezone=Asia%2FTokyo&start_date={d0}&end_date={d1}", tries=5, wait=10) or "{}")
            w = json.loads(get(f"https://api.open-meteo.com/v1/forecast?latitude={la}&longitude={lo}"
                               f"&daily=weather_code,wind_speed_10m_max,wind_gusts_10m_max,wind_direction_10m_dominant,precipitation_probability_max"
                               f"&wind_speed_unit=ms&timezone=Asia%2FTokyo&start_date={d0}&end_date={d1}", tries=5, wait=10) or "{}")
        except Exception as e:  # noqa: BLE001
            print(f"  ! 予報の取得失敗 {name}: {e}", file=sys.stderr)
            continue
        md, wd = m.get("daily", {}), w.get("daily", {})
        hrs = m.get("hourly", {})
        per = {}
        for i, d in enumerate(out["days"]):
            # 満潮・干潮（予報潮位の極大・極小）
            hl = []
            times, lv = hrs.get("time", []), hrs.get("sea_level_height_msl", [])
            for j in range(1, len(lv) - 1):
                if not times[j].startswith(d) or lv[j] is None or lv[j - 1] is None or lv[j + 1] is None:
                    continue
                if lv[j] >= lv[j - 1] and lv[j] > lv[j + 1]:
                    hl.append(("満", times[j][11:16]))
                elif lv[j] <= lv[j - 1] and lv[j] < lv[j + 1]:
                    hl.append(("干", times[j][11:16]))
            g = lambda arr: (arr[i] if arr and i < len(arr) else None)
            wdeg = g(wd.get("wind_direction_10m_dominant"))
            per[d] = {"wave": g(md.get("wave_height_max")), "swell": g(md.get("swell_wave_height_max")),
                      "period": g(md.get("swell_wave_period_max")), "wind": g(wd.get("wind_speed_10m_max")),
                      "gust": g(wd.get("wind_gusts_10m_max")),
                      "wdir": WDIR[int((wdeg + 22.5) % 360 // 45)] if wdeg is not None else "",
                      "code": g(wd.get("weather_code")), "rain": g(wd.get("precipitation_probability_max")), "tides": hl}
        out["areas"][name] = per
        time.sleep(0.3)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="基準日 YYYY-MM-DD（省略時は今日）")
    ap.add_argument("--days", type=int, default=35)
    ap.add_argument("--no-lastyear", action="store_true")
    ap.add_argument("--forecast-only", action="store_true", help="既存の raw に週末の海況予報だけを足す")
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
    if a.forecast_only:
        raw = json.loads(p.read_text(encoding="utf-8"))
        raw["forecast"] = fetch_forecast(base)
        p.write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
        print("forecast saved", file=sys.stderr)
        return
    have = {}
    if a.merge and p.exists():
        for g in json.loads(p.read_text(encoding="utf-8"))["groups"]:
            for s in g["ships"]:
                have[s["id"]] = s
    out = {"base_date": until, "since": since, "lastyear": [ly_since, ly_until], "groups": []}
    for f in cfg.get("facilities", []):
        print(f"[施設] {f['name']}", file=sys.stderr)
        if f["source"] == "yfp":
            items = [x for fac in f["codes"] for x in fetch_yfp(fac, since, until)]
            last = [x for fac in f["codes"] for x in fetch_yfp(fac, ly_since, ly_until)] if not a.no_lastyear else []
        elif f["source"] == "uosoku":
            items, last = fetch_uosoku(f["place"], since, until), []
        elif f["source"] == "umc":
            items, last = fetch_umc(since, until), []
        else:
            continue
        print(f"  今期{len(items)}件 前年{len(last)}件", file=sys.stderr)
        out.setdefault("facilities", []).append({**f, "items": items, "lastyear": last})
    for g in cfg["groups"]:
        print(f"[{g['name']}] {len(g['ships'])}軒", file=sys.stderr)
        ships = []
        for s in g["ships"]:
            if s["id"] in have:
                ships.append({**have[s["id"]], **s})
                continue
            if s.get("source") == "fv":
                cur = fetch_fv(s["fv_id"], s["id"], since, until)
                last = fetch_fv(s["fv_id"], s["id"], ly_since, ly_until, max_pages=12) if (cur and not a.no_lastyear) else []
                url = s.get("url") or f"https://www.fishing-v.jp/choka/choka_detail.php?s={s['fv_id']}"
            elif s.get("source") == "okaju":
                cur = fetch_okaju(s["page_url"], s["id"], since, until)
                last = []
                url = s.get("url") or s["page_url"]
            elif s.get("source") == "diary":
                cur = fetch_diary(s["diary_url"], s["id"], since, until)
                last = []
                url = s.get("url") or s["diary_url"]
            elif s.get("source") == "blog":
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

    try:
        out["forecast"] = fetch_forecast(base)
    except Exception as e:  # noqa: BLE001
        print(f"  ! 週末の海況予報を取得できませんでした: {e}", file=sys.stderr)
    out["fetch_stats"] = STATS
    total = STATS["ok"] + STATS["fail"]
    print(f"取得: 成功 {STATS['ok']} / 失敗 {STATS['fail']}", file=sys.stderr)
    if total and STATS["fail"] / total > 0.5:
        print("!!! 取得の半分以上が失敗しました。レポートは公開せず、メールで知らせてください。", file=sys.stderr)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved {p}", file=sys.stderr)


if __name__ == "__main__":
    main()
