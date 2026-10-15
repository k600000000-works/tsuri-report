"""釣りメモ（Google ドキュメントのテキスト）から本人の釣行を機械的に拾い、config/trips.json を作る。

毎回同じ結果になるよう、判断は Claude ではなくこのスクリプトで行う。
使い方: python scripts/trips_from_memo.py /tmp/memo.txt [--today YYYY-MM-DD]

拾い方:
- 「# 見出し」を区切りにする。「# 釣り物」より後の見出しは魚種、前の見出しは釣り場。
- 行の頭（記号や船宿名のあと12文字以内）に YYYY/M/D がある行を釣行とみなす。「・」で始まる行はメモなので拾わない。
- 魚種は ①その行に書いてある魚 ②直前の「■魚種」などの小見出し ③魚種の見出し ④釣り場の定番 の順で決める。
- 「隠」「秘」が行にあれば secret。未来の日付（予約）は拾わない。
"""
import datetime as dt
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 釣り場の見出し → (kind, ぼかした場所, 定番の魚)
PLACES = {
    "ボート釣り": ("ボート", "東京湾", ""),
    "他": ("ボート", "東京湾", ""),
    "東扇島": ("堤防", "川崎の釣り公園", ""),
    "九十九里海釣りセンター": ("釣り堀", "九十九里の釣り堀", "真鯛"),
    "鹿島魚釣園": ("施設", "鹿島の釣り施設", ""),
    "みうら海王": ("釣り堀", "三浦の釣り堀", "真鯛"),
    "大黒海つり施設": ("施設", "横浜の海釣り施設", ""),
    "本牧海つり施設": ("施設", "横浜の海釣り施設", ""),
    "テトラ": ("堤防", "堤防", ""),
    "釣り堀": ("釣り堀", "釣り堀", ""),
}
SKIP_SECTIONS = ("日帰り温泉", "釣り持ち物", "ウキ", "釣りものシーズン", "リールメモ", "ロッドメモ", "ボート基本", "釣り場")
# 魚種見出しのうち、魚の名前でないものの読み替え
FISH_ALIAS = {"タイラバ": "マダイ", "コマセカツオ": "カツオ", "LTウィリー": "ウィリー五目", "沖のウィリー五目": "ウィリー五目",
              "マダコ": "タコ", "イイダコ": "イイダコ", "真鯛": "マダイ", "石鯛": "イシダイ", "鯉": "コイ"}
EXTRA_FISH = ["真鯛", "マダイ", "カンパチ", "ショゴ", "イナダ", "ワラサ", "シマアジ", "サーモン", "銀鮭", "ヒラメ", "クロソイ", "コノシロ",
              "サヨリ", "マダコ", "タコ", "石鯛", "イシダイ", "カサゴ", "アジ", "サバ", "イワシ", "シリヤケイカ", "スミイカ", "鯉"]
DATE_RE = re.compile(r"(20[12]\d)\s*[/.年]\s*(\d{1,2})\s*[/.月]\s*(\d{1,2})")


def fish_name(s):
    return FISH_ALIAS.get(s, s)


def find_fish(text, known):
    """text に出てくる魚を、出てきた順に返す（シマアジの中のアジのような部分一致は除く）。"""
    hits, taken = [], []
    for k in known:  # 長い名前から
        for m in re.finditer(re.escape(k), text):
            if not any(a <= m.start() < b for a, b in taken):
                taken.append((m.start(), m.end()))
                hits.append((m.start(), k))
    return [k for _, k in sorted(hits)]


def main():
    src = Path(sys.argv[1])
    today = dt.date.today()
    if "--today" in sys.argv:
        today = dt.date.fromisoformat(sys.argv[sys.argv.index("--today") + 1])
    lines = unicodedata.normalize("NFKC", src.read_text(encoding="utf-8")).split("\n")

    # 魚種の見出しを集める（「# 釣り物」より後）
    heads = [(i, l[2:].strip(" *\\")) for i, l in enumerate(lines) if l.startswith("# ")]
    start = next((i for i, h in heads if h.startswith("釣り物")), len(lines))
    fish_heads = [h for i, h in heads if i > start and h not in PLACES]
    known = sorted({*fish_heads, *EXTRA_FISH} - {"他"}, key=len, reverse=True)

    trips, seen = [], set()
    section, is_fish_sec, sub = "", False, ""
    for i, raw in enumerate(lines):
        line = raw.strip()
        if raw.startswith("# "):
            section = raw[2:].strip(" *\\")
            is_fish_sec = i > start and section not in PLACES
            sub = ""
            continue
        if not line or any(section.startswith(s) for s in SKIP_SECTIONS) or section.startswith("釣り物"):
            continue
        # 「■アジ」「シリヤケイカ」のような小見出し
        bare = line.strip("■▼ ")
        if bare in known and len(bare) <= 8:
            sub = bare
            continue
        if line.startswith(("・", "→", "★", "http")):
            continue
        m = DATE_RE.search(line)
        if not m or m.start() > 12 or "(" in line[max(0, m.start() - 1):m.start()]:
            continue
        try:
            d = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        if d > today:
            continue  # 予約・誤記
        rest = line[m.end():].strip()
        prefix = line[:m.start()].strip("■▼ ")
        # 魚種: 行内（本人の釣果部分を優先）→ 小見出し → 魚種見出し → 釣り場の定番
        own = re.split(r"[,、]", rest.split("自分", 1)[1])[0] if "自分" in rest else ""
        # 同行者の釣果に出てくる魚は拾わない（「自分」があればその部分だけを見る）
        in_line = find_fish(own if "自分" in rest else rest, known)
        if is_fish_sec:
            fish = section
        else:
            fish = sub or (in_line[0] if in_line else "") or PLACES.get(section, ("", "", ""))[2]
        if not fish:
            continue
        kind, area, _ = PLACES.get(section, ("船", "船", ""))
        if section == "ワカサギ":
            kind, area = "氷上", "北海道"
        self_m = re.search(r"自分\s*(\d+)", rest) or re.search(r"(?:^|\s)(\d+)(?:\s|$|\(|（)", rest)
        default = PLACES.get(section, ("", "", ""))[2]
        if default and "自分" in rest:
            fish = default  # 釣り堀の「自分9+シマアジ」は 本命(真鯛)9尾＋シマアジ
        names = [fish_name(fish)] + [fish_name(k) for k in in_line if fish_name(k) != fish_name(fish)]
        for n in names:
            key = (d.isoformat(), n)
            if key in seen:
                continue
            seen.add(key)
            trips.append({"date": d.isoformat(), "fish": n, "kind": kind, "area": area,
                          "place": re.sub(r"^[^\w぀-ヿ一-鿿]+|^ð\d*", "", (prefix + " " + rest.split(" ")[0]).strip())[:30] if kind == "船" else section,
                          "self": self_m.group(1) if self_m and n == fish_name(fish) else "",
                          "secret": bool(re.search(r"[隠秘]", line)), "line": i + 1})
    trips.sort(key=lambda t: t["date"], reverse=True)
    out = ROOT / "config" / "trips.json"
    out.write_text(json.dumps({"trips": trips}, ensure_ascii=False, indent=1), encoding="utf-8")
    recent = [t for t in trips if (today - dt.date.fromisoformat(t["date"])).days <= 60 and not t["secret"]]
    print(f"saved {out}: {len(trips)}件（うち secret {sum(t['secret'] for t in trips)}件）")
    print("2か月以内:", "、".join(f"{t['date']} {t['fish']}" for t in recent) or "なし")


if __name__ == "__main__":
    main()
