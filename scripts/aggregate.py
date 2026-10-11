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
    "ムギイカ": "スルメイカ",
}


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
    return round(statistics.mean(vals), 1) if vals else None


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else dt.date.today().isoformat()
    raw = json.loads((ROOT / "data" / "raw" / f"{date}.json").read_text(encoding="utf-8"))
    base = dt.date.fromisoformat(raw["base_date"])
    w_lo = (base - dt.timedelta(days=6)).isoformat()
    p_lo = (base - dt.timedelta(days=13)).isoformat()
    p_hi = (base - dt.timedelta(days=7)).isoformat()
    ly_lo, ly_hi = raw["lastyear"]

    summary = {"base_date": raw["base_date"], "week": [w_lo, raw["base_date"]], "prev": [p_lo, p_hi],
               "lastyear": raw["lastyear"], "groups": []}
    digest = [f"# 判定用ダイジェスト {raw['base_date']}（今週 {w_lo}〜 / 前週 {p_lo}〜{p_hi} / 前年 {ly_lo}〜{ly_hi}）\n"]

    for g in raw["groups"]:
        fish = defaultdict(lambda: {"now": [], "prev": [], "ly": [], "ships": [], "comments": []})
        sources = []
        for s in g["ships"]:
            now = ship_stats(window(s["catches"], w_lo, raw["base_date"]))
            prev = ship_stats(window(s["catches"], p_lo, p_hi))
            ly = ship_stats(s["lastyear"])
            if now:
                sources.append({"name": s["name"], "url": s["url"], "reports": len(window(s["catches"], w_lo, raw["base_date"]))})
            for k, e in now.items():
                fish[k]["now"].append(e)
                fish[k]["ships"].append(s["name"])
                fish[k]["comments"] += [f"[{s['name']}] {c}" for c in e["comments"][:4]]
            for k, e in prev.items():
                fish[k]["prev"].append(e)
            for k, e in ly.items():
                fish[k]["ly"].append(e)

        rows = []
        for k, f in fish.items():
            if not f["now"]:
                continue
            reports = sum(len(e["days"]) for e in f["now"])
            now_v, prev_v, ly_v = group_value(f["now"]), group_value(f["prev"]), group_value(f["ly"])
            if now_v is None:
                continue
            unit = next((e["unit"] for e in f["now"] if e["unit"]), "")
            rows.append({
                "fish": k, "avg": now_v, "unit": unit,
                "top": max(e["top"] for e in f["now"]),
                "size_max": max(e["size_max"] for e in f["now"]) or None,
                "size_unit": next((e["size_unit"] for e in f["now"] if e["size_unit"]), ""),
                "prev": prev_v, "lastyear": ly_v,
                "wow": round(now_v / prev_v - 1, 2) if prev_v else None,
                "yoy": round(now_v / ly_v - 1, 2) if ly_v else None,
                "ships": len(f["ships"]), "reports": reports,
                "minor": reports < MIN_REPORTS,
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
            digest.append(f"\n### {r['fish']}  平均{r['avg']}{r['unit']} 竿頭{r['top']:g} / 前週比{pct(r['wow'])} 前年比{pct(r['yoy'])} / {r['ships']}軒 {r['reports']}便\n")
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
