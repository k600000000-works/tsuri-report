"""data/raw/<日付>.json を港×魚種で集計する。

1件の釣果の代表値 = (最少+最多)/2（その日の竿頭〜スソの真ん中）
船宿の値 = その週の代表値の平均
港の値   = 船宿の値の平均（出船の多い船宿に引っぱられないようにする）

出力:
  data/summary/<日付>.json   … 集計値（render.py が使う）
  data/digest/<日付>.md      … 判定用の要約（数字＋釣果コメント。Claude が読む）
"""
import datetime as dt
import json
import re
import statistics
import unicodedata
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIN_REPORTS = 2  # 週の報告数がこれ未満の魚種は「参考」扱い
WEEKS = 5        # 推移を見る週数
RECENT_DAYS = 60 # 「最近行った」とみなす日数（約2か月）

# 表記ゆれの統一
ALIASES = {
    "チヌ": "クロダイ", "グレ": "メジナ",
    "マアジ": "アジ", "LTアジ": "アジ", "ライトアジ": "アジ",
    "ショウサイフグ": "フグ", "トラフグ": "フグ",
    "キス": "シロギス",
    "マダコ": "タコ",
    "スルメイカ": "スルメイカ", "ヤリイカ": "ヤリイカ",
    "イナダ": "ワラサ・イナダ", "ワラサ": "ワラサ・イナダ", "ブリ": "ワラサ・イナダ",
    "ハナダイ": "マダイ",
    "アオリ": "アオリイカ",
    "ホンガツオ": "カツオ", "マルソウダ": "ソウダガツオ", "ヒラソウダ": "ソウダガツオ",
    "キハダマグロ": "キハダ", "キメジ": "キハダ",
    "スミイカ": "スミイカ", "コウイカ": "スミイカ",
    "ムギイカ": "スルメイカ", "スルメ": "スルメイカ", "カタクチイワシ": "イワシ", "ウルメイワシ": "イワシ", "マイワシ": "イワシ",
}


def counter(fish, unit):
    """釣りの慣習的な数え方に合わせる（重さ表記などはそのまま）。"""
    if unit not in ("匹", "尾", "本", "枚", "杯", ""):
        return unit
    for keys, u in ((("イカ", "タコ"), "杯"), (("マダイ", "ヒラメ", "カレイ", "カワハギ", "ウマヅラ", "アマダイ", "マゴチ"), "枚"),
                    (("タチウオ", "ワラサ", "イナダ", "ブリ", "カツオ", "キハダ", "サワラ", "シイラ", "カンパチ", "ヒラマサ"), "本")):
        if any(k in fish for k in keys):
            return u
    return "匹"


def norm(name):
    name = re.sub(r"[（(].*?[)）]", "", name).strip()
    return ALIASES.get(name, name)


WEIGHT_FISH = ("タコ",)  # 型（重さ）を重視する魚種。表に無ければコメントから読む


def parse_weight(text, near=None):
    """コメントから重さの幅(kg)を読む。near（魚種名）があれば、その直後に書かれたものを優先する。
    対応: 0.3～1.5kg / 400～500g / 4～500g級 / 2kg級 / 1.2キロ"""
    t = unicodedata.normalize("NFKC", text or "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:kg|キロ)(?:級)?の\s*(?:大)?(?:マ)?(?:ダコ|タコ|蛸)", t)  # 2.5kgの大ダコ
    if near and m:
        return float(m.group(1)), float(m.group(1))
    spans = [t]
    if near:
        mm = re.search(r"[タダ]コ|蛸", t) if near == "タコ" else None
        i = mm.start() if mm else t.find(near)
        others = ("マダイ", "真鯛", "鯛", "ヒラメ", "ワラサ", "ブリ", "カンパチ", "ヒラマサ", "サワラ", "アマダイ", "ハタ", "青物")
        spans = [t[i:i + 40]] if i >= 0 else []
        if not any(o in t for o in others):  # 別の魚の重さが混ざりうるときは、全文からは拾わない
            spans.append(t)
    for sp in spans:
        m = re.search(r"(\d+(?:\.\d+)?)\s*[～~\-]\s*(\d+(?:\.\d+)?)\s*(?:kg|キロ|k|K)", sp)
        if m:
            return float(m.group(1)), float(m.group(2))
        m = re.search(r"(\d{1})\s*[～~\-]\s*(\d)00\s*(?:g|グラム)", sp)  # 4～500g = 400～500g
        if m:
            return int(m.group(1)) / 10, int(m.group(2)) / 10
        m = re.search(r"(\d{2,4})\s*[～~\-]\s*(\d{2,4})\s*(?:g|グラム)", sp)
        if m:
            return int(m.group(1)) / 1000, int(m.group(2)) / 1000
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:kg|キロ)\s*(?:級|前後|クラス|オーバー|超)", sp)
        if m:
            return float(m.group(1)), float(m.group(1))
        m = re.search(r"(\d{3,4})\s*(?:g|グラム)\s*(?:級|前後|クラス|主体)", sp)
        if m:
            return int(m.group(1)) / 1000, int(m.group(1)) / 1000
    return None


def window(catches, lo, hi):
    return [c for c in catches if lo <= c["date"] <= hi]


def ship_stats(catches):
    """魚種 -> {'vals': [...代表値], 'top': 竿頭最大, 'unit', 'size_max', 'comments': [...]}"""
    d = defaultdict(lambda: {"vals": [], "los": [], "his": [], "wlo": [], "whi": [], "top": 0, "unit": "", "size_max": 0, "size_unit": "", "comments": [], "days": set()})
    for c in catches:
        for f in c["fish"]:
            k = norm(f["name"])
            m = re.search(r"(匹|本|枚|杯|尾|kg|ｋｇ|個)", f["unit"] or f["count"])
            f["unit"] = m.group(1) if m else ""
            e = d[k]
            if f["min"] is not None:
                e["vals"].append((f["min"] + f["max"]) / 2)
                e["los"].append(f["min"])
                e["his"].append(f["max"])
                e["top"] = max(e["top"], f["max"])
                e["unit"] = e["unit"] or f["unit"]
            if f.get("size_max"):
                su = "kg" if re.search(r"(kg|ｋｇ|キロ)", f["size"], re.I) else "cm" if "cm" in f["size"] or "ｃｍ" in f["size"] else ""
                if su and (not e["size_unit"] or e["size_unit"] == su):
                    e["size_unit"] = su
                    e["size_max"] = max(e["size_max"], f["size_max"])
            if any(w in k for w in WEIGHT_FISH):
                w = None
                if f.get("size") and re.search(r"(kg|ｋｇ|キロ)", f["size"], re.I):
                    w = parse_weight(f["size"])
                if not w:
                    w = parse_weight(c.get("comment", ""), near="タコ")
                if w and 0.05 <= w[0] <= w[1] <= 8:
                    e["wlo"].append(w[0])
                    e["whi"].append(w[1])
            e["days"].add(c["date"])
            if c["comment"]:
                e["comments"].append(f"{c['date'][5:]} {c['comment'][:120]}")
    return d


def ship_week(e):
    """船宿の週の値 = 便ごとの代表値の中央値（1日だけの大釣り・大外れに引っ張られない）。"""
    return statistics.median(e["vals"]) if e["vals"] else None


def group_value(per_ship, key="vals"):
    """エリアの値。船宿ごとに週の中央値を取り、5軒以上なら最高・最低の船宿を1軒ずつ除いて平均する。
    key: "vals"（スソと竿頭の中間）/ "los"（スソ）/ "his"（竿頭）"""
    vals = sorted(statistics.median(e[key]) for e in per_ship if e[key])
    if len(vals) >= 5:
        vals = vals[1:-1]
    elif len(vals) >= 3:  # 船中合計を1人分の欄に書いたような極端な値を除く
        med = statistics.median(vals)
        vals = [v for v in vals if v <= med * 5] or vals
    return round(statistics.mean(vals), 1) if vals else None


def steadiness(week_entries, all_entries):
    """今週の便のうち、5週間の標準（便ごと代表値の中央値）以上だった便の数。"""
    pool = [v for e in all_entries for v in e["vals"]]
    now = [v for e in week_entries for v in e["vals"]]
    if len(pool) < 4 or not now:
        return None, len(now)
    std = statistics.median(pool)
    return sum(v >= std for v in now), len(now)


def blur(base, d):
    """日付を、誰が見ても問題ない程度にぼかした言い方にする。"""
    days = (base - d).days
    if days <= 14:
        return "最近"
    if days <= 45:
        return "先月" if d.month != base.month else "今月"
    if days <= 300:
        return f"{d.month}月ごろ" if d.year == base.year else f"昨年の{d.month}月ごろ"
    years = base.year - d.year
    try:
        same_season = abs((d.replace(year=base.year) - base).days) <= 45
    except ValueError:
        same_season = False
    ago = "去年" if years == 1 else f"{years}年前"
    return f"{ago}の今ごろ" if same_season else f"{ago}の{d.month}月ごろ"


def load_trips(base):
    """config/trips.json（非公開）を読む。secret（隠・秘）は最初から除く。

    戻り値: (recent, season, last)
      recent … 4週間以内に行った魚種 -> True（狙い目から外す）
      season … 過去の年の同じ時期（前後3週間）の釣行
      last   … 魚種ごとの直近の釣行
    """
    p = ROOT / "config" / "trips.json"
    if not p.exists():
        return {}, [], {}
    trips = [t for t in json.loads(p.read_text(encoding="utf-8")).get("trips", []) if not t.get("secret") and t.get("fish")]
    recent, season, last = {}, [], {}
    for t in sorted(trips, key=lambda t: t["date"]):
        d = dt.date.fromisoformat(t["date"])
        if d > base:
            continue
        k = norm(t["fish"])
        item = {"fish": k, "when": blur(base, d), "where": t.get("area") or t.get("kind", ""), "kind": t.get("kind", ""), "self": t.get("self", "")}
        if (base - d).days <= RECENT_DAYS:
            recent[k] = True
        if d.year < base.year:
            try:
                same = abs((d.replace(year=base.year) - base).days) <= 21
            except ValueError:
                same = False
            if same:
                season.append(item)
        last[k] = item
    return recent, season, last


def agg_facility(f, weeks, trips):
    """陸っぱり・施設の集計。
    kind=count（横浜の海づり施設）: 魚種ごとの釣れた数を来場者数で割り、100人あたりで比べる。
    kind=days（東扇島・九十九里）: 数が無いので、その魚が報告された日数・件数で調子を見る。"""
    items = f.get("items", [])
    inwk = lambda it, w: w[0] <= it["date"] <= w[1]
    fish = defaultdict(lambda: {"wk_cnt": [0] * len(weeks), "days": [set() for _ in weeks], "smin": None, "smax": None,
                                "unit": "", "by": defaultdict(int), "posts": [], "n": [0] * len(weeks)})
    visitors = [0] * len(weeks)
    report_days = [set() for _ in weeks]
    seen = set()
    for it in items:
        for i, w in enumerate(weeks):
            if not inwk(it, w):
                continue
            report_days[i].add(it["date"])
            key = (it.get("facility"), it["date"])
            if it.get("visitors") and key not in seen:
                seen.add(key)
                visitors[i] += it["visitors"]
            for fx in it["fish"]:
                k = norm(fx["name"])
                e = fish[k]
                e["days"][i].add(it["date"])
                e["n"][i] += 1  # 投稿・記事の件数（1日に何件も出る魚を見落とさないため）
                if fx.get("count"):
                    e["wk_cnt"][i] += fx["count"]
                    if i == 0:
                        e["by"][it.get("facility") or ""] += fx["count"]
                if i == 0:
                    if fx.get("size_max"):
                        e["unit"] = fx.get("unit") or e["unit"]
                        e["smin"] = min(e["smin"], fx["size_min"]) if e["smin"] is not None else fx["size_min"]
                        e["smax"] = max(e["smax"], fx["size_max"]) if e["smax"] is not None else fx["size_max"]
                    if it.get("url"):
                        e["posts"].append({"date": it["date"], "title": it.get("title") or f"{it['date'][5:]}の釣果", "url": it["url"],
                                           "source": it.get("source", "")})
    # 前年同期（count のみ）
    ly_cnt, ly_vis, ly_seen = defaultdict(int), 0, set()
    for it in f.get("lastyear", []):
        key = (it.get("facility"), it["date"])
        if it.get("visitors") and key not in ly_seen:
            ly_seen.add(key)
            ly_vis += it["visitors"]
        for fx in it["fish"]:
            if fx.get("count"):
                ly_cnt[norm(fx["name"])] += fx["count"]
    rows = []
    for k, e in fish.items():
        nd0 = len(e["days"][0])
        if not nd0:
            continue
        row = {"fish": k, "days": nd0, "report_days": len(report_days[0]), "reports": e["n"][0],
               "reports_series": list(reversed(e["n"])),
               "days_series": list(reversed([len(d) for d in e["days"]])),
               "posts": sorted(e["posts"], key=lambda x: x["date"], reverse=True)[:8]}
        if f.get("kind") == "count":
            per = [round(c / v * 100, 1) if v else None for c, v in zip(e["wk_cnt"], visitors)]
            ly = round(ly_cnt[k] / ly_vis * 100, 1) if ly_vis and ly_cnt.get(k) else None
            ratio = lambda a, b: round(a / b - 1, 2) if (a and b and b >= 0.5) else None  # 基準が小さすぎる比較は出さない
            row.update({"total": e["wk_cnt"][0], "per100": per[0], "series": list(reversed(per)),
                        "wow": ratio(per[0], per[1] if len(per) > 1 else None),
                        "lastyear": ly, "yoy": ratio(per[0], ly),
                        "size_min": e["smin"], "size_max": e["smax"], "size_unit": e["unit"],
                        "by_facility": dict(sorted(e["by"].items(), key=lambda x: -x[1])),
                        "minor": e["wk_cnt"][0] < 5})
        else:
            row.update({"minor": nd0 < 2 and e["n"][0] < 3 and len(report_days[0]) > 2})
        rows.append(row)
    if f.get("kind") == "count":
        rows.sort(key=lambda r: (r["minor"], -(r["per100"] or 0)))
    else:
        rows.sort(key=lambda r: (r["minor"], -r["days"], -r["reports"]))
    comments = [f"{it['date'][5:]}{('・' + it['facility']) if it.get('facility') else ''} {it.get('comment') or it.get('title', '')}"[:200]
                for it in sorted(items, key=lambda x: x["date"], reverse=True) if inwk(it, weeks[0])][:12]
    releases = [{"date": it["date"], "text": t, "url": it.get("url", "")}
                for it in sorted(items, key=lambda x: x["date"], reverse=True)
                if weeks[min(1, len(weeks) - 1)][0] <= it["date"] <= weeks[0][1] for t in it.get("release", [])]  # 直近2週の放流
    return {"name": f["name"], "kind": f.get("kind"), "sub": f.get("sub", ""), "url": f.get("url", ""), "releases": releases,
            "visitors": visitors[0], "report_days": len(report_days[0]), "fish": rows, "comments": comments,
            "water": [it.get("water") for it in items if inwk(it, weeks[0]) and it.get("water")][:1]}


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else dt.date.today().isoformat()
    raw = json.loads((ROOT / "data" / "raw" / f"{date}.json").read_text(encoding="utf-8"))
    base = dt.date.fromisoformat(raw["base_date"])
    # weeks[0] が今週、weeks[1] が前週 … 古い方へ
    weeks = [((base - dt.timedelta(days=7 * i + 6)).isoformat(), (base - dt.timedelta(days=7 * i)).isoformat())
             for i in range(WEEKS)]
    weeks = [w for w in weeks if w[1] >= raw["since"]]
    ly_lo, ly_hi = raw["lastyear"]
    trips, season, last = load_trips(base)

    summary = {"base_date": raw["base_date"], "week": list(weeks[0]), "weeks": [list(w) for w in weeks],
               "lastyear": raw["lastyear"], "groups": []}
    digest = [f"# 判定用ダイジェスト {raw['base_date']}（今週 {weeks[0][0]}〜 / 推移は古い週→今週 / 前年 {ly_lo}〜{ly_hi}）\n"]
    st = raw.get("fetch_stats") or {}
    if st and (st.get("ok", 0) + st.get("fail", 0)) and st["fail"] / (st["ok"] + st["fail"]) > 0.5:
        digest.append(f"\n**警告: 取得の半分以上が失敗（成功 {st['ok']} / 失敗 {st['fail']}）。公開せず、メールで知らせること。**\n")
    fmt = lambda t: f"{t['when']}・{t['where']}で{t['fish']}" + (f"（{t['self']}）" if t["self"] else "")
    digest.append("\n## 本人の釣行（ぼかし済み。公開物に書くときもこの粒度まで。日付・船宿名・同行者は書かない）\n")
    digest.append("- 2か月以内に行った魚種（狙い目 picks から外し、外したことを excluded に書く）: "
                  + ("、".join(trips) or "なし") + "\n")
    digest.append("- 過去の同じ時期の釣行: " + ("、".join(fmt(t) for t in season) or "なし") + "\n")
    digest.append("- 魚種ごとの直近の釣行: " + "、".join(fmt(t) for t in last.values()) + "\n")

    for g in raw["groups"]:
        fish = defaultdict(lambda: {"wk": [[] for _ in weeks], "ly": [], "ships": [], "comments": []})
        sources = []
        for s in g["ships"]:
            per_week = [ship_stats(window(s["catches"], lo, hi)) for lo, hi in weeks]
            ly = ship_stats(s["lastyear"])
            now = per_week[0]
            if now:
                sources.append({"name": s["name"], "url": s["url"], "reports": len(window(s["catches"], *weeks[0]))})
            for i, st in enumerate(per_week):
                for k, e in st.items():
                    fish[k]["wk"][i].append(e)
            for k, e in now.items():
                fish[k]["ships"].append({
                    "name": s["name"], "url": s["url"],
                    "avg": round(ship_week(e), 1) if e["vals"] else None,
                    "top": e["top"] or None, "reports": len(e["days"]),
                    "lo": statistics.median(e["los"]) if e["los"] else None,
                    "hi": statistics.median(e["his"]) if e["his"] else None,
                })
                fish[k]["comments"] += [f"[{s['name']}] {c}" for c in e["comments"][:4]]
            for k, e in ly.items():
                fish[k]["ly"].append(e)

        rows = []
        for k, f in fish.items():
            nowl = f["wk"][0]
            if not nowl:
                continue
            series = [group_value(x) for x in f["wk"]]
            now_v, prev_v, ly_v = series[0], (series[1] if len(series) > 1 else None), group_value(f["ly"])
            if now_v is None:
                continue
            reports = sum(len(e["days"]) for e in nowl)
            good, total = steadiness(nowl, [e for wk in f["wk"] for e in wk])
            recent3 = [v for v in series[:3] if v is not None]
            avg3 = round(statistics.mean(recent3), 1) if recent3 else None
            rows.append({
                "fish": k, "avg": now_v, "unit": counter(k, next((e["unit"] for e in nowl if e["unit"]), "")),
                "top": max(e["top"] for e in nowl),
                "size_max": max(e["size_max"] for e in nowl) or None,
                "size_unit": next((e["size_unit"] for e in nowl if e["size_unit"]), ""),
                "prev": prev_v, "lastyear": ly_v,
                "series": list(reversed(series)),  # 古い週→今週
                "wow": round(now_v / prev_v - 1, 2) if prev_v else None,
                "yoy": round(now_v / ly_v - 1, 2) if ly_v else None,
                "avg3": avg3,
                "w_lo": round(statistics.median([v for e in nowl for v in e["wlo"]]), 2) if any(e["wlo"] for e in nowl) else None,
                "w_hi": round(statistics.median([v for e in nowl for v in e["whi"]]), 2) if any(e["whi"] for e in nowl) else None,
                "w_max": max([v for e in nowl for v in e["whi"]], default=None),
                "w_n": sum(len(e["whi"]) for e in nowl),
                "lo_typ": group_value(nowl, "los"),  # ふつうの日のスソ
                "hi_typ": group_value(nowl, "his"),  # ふつうの日の竿頭
                "steady_good": good, "steady_total": total,
                "yoy3": round(avg3 / ly_v - 1, 2) if (ly_v and avg3) else None,
                "ships": len(f["ships"]), "reports": reports,
                "ship_list": sorted(f["ships"], key=lambda x: -(x["avg"] or 0)),
                "minor": reports < MIN_REPORTS,
                "recent_trip": bool(trips.get(k)),
                "comments": f["comments"][:12],
            })
        rows.sort(key=lambda r: (r["minor"], -r["reports"]))
        summary["groups"].append({"name": g["name"], "fish": rows,
                                  "sources": sorted(sources, key=lambda x: -x["reports"])})

        digest.append(f"\n## {g['name']}（釣果のあった船宿 {len(sources)}軒）\n")
        for r in rows:
            if r["minor"]:
                continue
            pct = lambda x: "—" if x is None else f"{x:+.0%}"
            ser = " → ".join("—" if v is None else f"{v:g}" for v in r["series"])
            mark = " ※本人が最近釣行済み（picks から外す）" if r["recent_trip"] else ""
            digest.append(f"\n### {r['fish']}  平均{r['avg']}{r['unit']} 竿頭{r['top']:g} / 前週比{pct(r['wow'])} 前年比{pct(r['yoy'])} / {r['ships']}軒 {r['reports']}便{mark}\n")
            stab = f" / 安定度: 今週{r['steady_total']}便中{r['steady_good']}便が5週の標準以上" if r["steady_good"] is not None else ""
            digest.append(f"週ごとの推移（古→新）: {ser} / 直近3週平均 {r['avg3']}（前年比 {pct(r['yoy3'])}）{stab}\n")
            digest += [f"- {c}\n" for c in r["comments"]]

    summary["facilities"] = []
    digest.append("\n# 陸っぱり・施設\n")
    for f in raw.get("facilities", []):
        fa = agg_facility(f, weeks, trips)
        summary["facilities"].append(fa)
        digest.append(f"\n## {fa['name']}（{fa['sub']}・今週の報告 {fa['report_days']}日" + (f"・来場者計 {fa['visitors']}人" if fa['visitors'] else "") + "）\n")
        for r in fa["fish"]:
            if r["minor"]:
                continue
            mark = " ※本人が最近釣行済み（picks から外す）" if trips.get(r["fish"]) else ""
            if fa["kind"] == "count":
                pct = lambda x: "—" if x is None else f"{x:+.0%}"
                ser = " → ".join("—" if v is None else f"{v:g}" for v in r["series"])
                digest.append(f"- {r['fish']}: 100人あたり{r['per100']}匹（週計{r['total']}）/ 前週比{pct(r['wow'])} 前年比{pct(r['yoy'])} / 推移 {ser} / {r['days']}日{mark}\n")
            else:
                ser = " → ".join(str(v) for v in r["days_series"])
                rser = " → ".join(str(v) for v in r.get("reports_series", []))
                digest.append(f"- {r['fish']}: {r['days']}/{r['report_days']}日で報告・{r.get('reports', 0)}件 / 日数の推移 {ser} / 件数の推移 {rser}{mark}\n")
        if fa.get("releases"):
            digest.append("放流情報（直近2週。好調の材料として扱う）:\n" + "".join(f"  - {x['date'][5:]} {x['text']}\n" for x in fa["releases"]))
        digest.append("コメント・投稿:\n" + "".join(f"  - {c}\n" for c in fa["comments"]))

    # ターゲット（本人が狙いを定めた魚種）: 全エリア・全施設の状況を一覧にする
    tp = ROOT / "config" / "targets.json"
    targets = json.loads(tp.read_text(encoding="utf-8")).get("targets", []) if tp.exists() else []
    summary["targets"] = targets
    if targets:
        digest.append("\n# ターゲット（本人が狙いを定めた魚種。picks の targets に総評を書く）\n")
        for tname in targets:
            k = norm(tname)
            digest.append(f"\n## {k}\n")
            for g in summary["groups"]:
                for r in g["fish"]:
                    if r["fish"] == k:
                        pct = lambda x: "—" if x is None else f"{x:+.0%}"
                        wt = f" / 型 {r['w_lo']}〜{r['w_hi']}kg（最大{r['w_max']}kg、{r['w_n']}便分）" if r.get("w_hi") else " / 型の情報なし"
                        digest.append(f"- {g['name']}: {r['lo_typ']}〜{r['hi_typ']}{r['unit']}（目安{r['avg']}）/ 前週比{pct(r['wow'])} 3週前年比{pct(r['yoy3'])} / 安定度 {r['steady_good']}/{r['steady_total']} / {r['ships']}軒{r['reports']}便{wt}\n")
            for fa in summary["facilities"]:
                for r in fa["fish"]:
                    if r["fish"] == k:
                        if fa["kind"] == "count":
                            digest.append(f"- {fa['name']}: 100人あたり{r['per100']}匹（週計{r['total']}）\n")
                        else:
                            digest.append(f"- {fa['name']}: {r['days']}/{r['report_days']}日で報告\n")

    fc = raw.get("forecast")
    if fc:
        summary["forecast"] = fc
        digest.append("\n# 週末の海況予報（Open-Meteo。各エリアの沖合。判定・総評・ターゲットの総評に反映する）\n")
        for d in fc["days"]:
            digest.append(f"\n## {d}（{fc['tide'][d]}・月齢{fc['moon_age'][d]}）\n")
            for name, per in fc["areas"].items():
                x = per.get(d) or {}
                tides = " ".join(f"{a}{t}" for a, t in x.get("tides", []))
                digest.append(f"- {name}: 波{x.get('wave')}m（ウネリ{x.get('swell')}m・周期{x.get('period')}秒）/ 風{x.get('wdir')}{x.get('wind')}m/s（突風{x.get('gust')}）/ 天気コード{x.get('code')}・降水{x.get('rain')}% / {tides}\n")

    out = ROOT / "data" / "summary" / f"{date}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    dg = ROOT / "data" / "digest" / f"{date}.md"
    dg.parent.mkdir(parents=True, exist_ok=True)
    dg.write_text("".join(digest), encoding="utf-8")
    print(f"saved {out} / {dg}")


if __name__ == "__main__":
    main()
