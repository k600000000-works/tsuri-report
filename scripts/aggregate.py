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
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIN_REPORTS = 2  # 週の報告数がこれ未満の魚種は「参考」扱い
WEEKS = 5        # 推移を見る週数
RECENT_DAYS = 28 # 「最近行った」とみなす日数

# 表記ゆれの統一
ALIASES = {
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
    "ムギイカ": "スルメイカ", "スルメ": "スルメイカ",
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


def window(catches, lo, hi):
    return [c for c in catches if lo <= c["date"] <= hi]


def ship_stats(catches):
    """魚種 -> {'vals': [...代表値], 'top': 竿頭最大, 'unit', 'size_max', 'comments': [...]}"""
    d = defaultdict(lambda: {"vals": [], "top": 0, "unit": "", "size_max": 0, "size_unit": "", "comments": [], "days": set()})
    for c in catches:
        for f in c["fish"]:
            k = norm(f["name"])
            m = re.search(r"(匹|本|枚|杯|尾|kg|ｋｇ|個)", f["unit"] or f["count"])
            f["unit"] = m.group(1) if m else ""
            e = d[k]
            if f["min"] is not None:
                e["vals"].append((f["min"] + f["max"]) / 2)
                e["top"] = max(e["top"], f["max"])
                e["unit"] = e["unit"] or f["unit"]
            if f.get("size_max"):
                su = "kg" if re.search(r"(kg|ｋｇ|キロ)", f["size"], re.I) else "cm" if "cm" in f["size"] or "ｃｍ" in f["size"] else ""
                if su and (not e["size_unit"] or e["size_unit"] == su):
                    e["size_unit"] = su
                    e["size_max"] = max(e["size_max"], f["size_max"])
            e["days"].add(c["date"])
            if c["comment"]:
                e["comments"].append(f"{c['date'][5:]} {c['comment'][:120]}")
    return d


def group_value(per_ship):
    vals = [statistics.mean(e["vals"]) for e in per_ship if e["vals"]]
    if len(vals) >= 3:  # 船中合計を1人分の欄に書いたような極端な値を除く
        med = statistics.median(vals)
        vals = [v for v in vals if v <= med * 5] or vals
    return round(statistics.mean(vals), 1) if vals else None


def load_trips(base):
    """config/trips.json から、基準日の4週間以内に行った魚種を返す。"""
    p = ROOT / "config" / "trips.json"
    if not p.exists():
        return {}
    lo = (base - dt.timedelta(days=RECENT_DAYS)).isoformat()
    out = {}
    for t in json.loads(p.read_text(encoding="utf-8")).get("trips", []):
        if lo <= t["date"] <= base.isoformat():
            k = norm(t["fish"])
            if t["date"] > out.get(k, ""):
                out[k] = t["date"]
    return out


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else dt.date.today().isoformat()
    raw = json.loads((ROOT / "data" / "raw" / f"{date}.json").read_text(encoding="utf-8"))
    base = dt.date.fromisoformat(raw["base_date"])
    # weeks[0] が今週、weeks[1] が前週 … 古い方へ
    weeks = [((base - dt.timedelta(days=7 * i + 6)).isoformat(), (base - dt.timedelta(days=7 * i)).isoformat())
             for i in range(WEEKS)]
    weeks = [w for w in weeks if w[1] >= raw["since"]]
    ly_lo, ly_hi = raw["lastyear"]
    trips = load_trips(base)

    summary = {"base_date": raw["base_date"], "week": list(weeks[0]), "weeks": [list(w) for w in weeks],
               "lastyear": raw["lastyear"], "recent_trips": trips, "groups": []}
    digest = [f"# 判定用ダイジェスト {raw['base_date']}（今週 {weeks[0][0]}〜 / 推移は古い週→今週 / 前年 {ly_lo}〜{ly_hi}）\n"]
    if trips:
        digest.append("\n**本人が4週間以内に行った魚種（狙い目 picks から外す・公開物には書かない）**: "
                      + "、".join(f"{k}（{v}）" for k, v in trips.items()) + "\n")

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
                    "avg": round(statistics.mean(e["vals"]), 1) if e["vals"] else None,
                    "top": e["top"] or None, "reports": len(e["days"]),
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
            rows.append({
                "fish": k, "avg": now_v, "unit": counter(k, next((e["unit"] for e in nowl if e["unit"]), "")),
                "top": max(e["top"] for e in nowl),
                "size_max": max(e["size_max"] for e in nowl) or None,
                "size_unit": next((e["size_unit"] for e in nowl if e["size_unit"]), ""),
                "prev": prev_v, "lastyear": ly_v,
                "series": list(reversed(series)),  # 古い週→今週
                "wow": round(now_v / prev_v - 1, 2) if prev_v else None,
                "yoy": round(now_v / ly_v - 1, 2) if ly_v else None,
                "ships": len(f["ships"]), "reports": reports,
                "ship_list": sorted(f["ships"], key=lambda x: -(x["avg"] or 0)),
                "minor": reports < MIN_REPORTS,
                "recent_trip": trips.get(k),
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
            mark = f" ※本人が{r['recent_trip']}に釣行済み" if r["recent_trip"] else ""
            digest.append(f"\n### {r['fish']}  平均{r['avg']}{r['unit']} 竿頭{r['top']:g} / 前週比{pct(r['wow'])} 前年比{pct(r['yoy'])} / {r['ships']}軒 {r['reports']}便{mark}\n")
            digest.append(f"週ごとの推移（古→新）: {ser}\n")
            digest += [f"- {c}\n" for c in r["comments"]]

    out = ROOT / "data" / "summary" / f"{date}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    dg = ROOT / "data" / "digest" / f"{date}.md"
    dg.parent.mkdir(parents=True, exist_ok=True)
    dg.write_text("".join(digest), encoding="utf-8")
    print(f"saved {out} / {dg}")


if __name__ == "__main__":
    main()
