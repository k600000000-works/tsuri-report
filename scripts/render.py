"""集計（data/summary）と Claude の判定（data/picks）からスライドHTMLを作る。

  python scripts/render.py 2026-10-16

出力: index.html（最新）と archive/<日付>.html、archive/index.html（過去分一覧）
picks が無い場合は数字だけで表示する（判定バッジなし）。
"""
import datetime as dt
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fish_icons import FISH_CSS, icon  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
E = html.escape

STATUS = {  # status -> (ラベル, CSSクラス, 並び順)
    "hot": ("狙い目", "hot", 0),
    "up": ("上向き", "up", 1),
    "steady": ("安定", "steady", 2),
    "down": ("下降", "down", 3),
    "slow": ("低調", "down", 4),
}

# 地図: 中心(lat, lng), ズーム, 港の印
GEO = {
    "横浜・金沢八景": {"sub": "本牧・新山下・根岸・金沢八景", "c": [35.385, 139.655], "z": 11,
                 "m": [["本牧", 35.414, 139.676], ["新山下", 35.437, 139.655], ["金沢八景", 35.335, 139.628]]},
    "東京湾口": {"sub": "走水・鴨居・久里浜・金田・松輪・剣崎", "c": [35.20, 139.70], "z": 10,
             "m": [["走水", 35.258, 139.735], ["久里浜", 35.226, 139.713], ["金田", 35.170, 139.685], ["松輪・剣崎", 35.143, 139.676]]},
    "内房": {"sub": "富津・上総湊・竹岡・金谷", "c": [35.235, 139.84], "z": 10,
           "m": [["富津", 35.302, 139.818], ["上総湊", 35.230, 139.846], ["竹岡", 35.200, 139.832], ["金谷", 35.165, 139.825]]},
    "相模湾東側": {"sub": "長井・佐島・秋谷・葉山・小坪", "c": [35.245, 139.60], "z": 10,
              "m": [["長井", 35.197, 139.611], ["佐島", 35.219, 139.612], ["葉山", 35.270, 139.580], ["小坪", 35.300, 139.566]]},
    "那珂湊・大洗": {"sub": "那珂湊・大洗", "c": [36.325, 140.59], "z": 11,
               "m": [["那珂湊", 36.337, 140.598], ["大洗", 36.307, 140.574]]},
    "鹿島": {"sub": "鹿嶋旧港・鹿嶋新港・深芝", "c": [35.925, 140.70], "z": 11,
           "m": [["鹿島港", 35.928, 140.697]]},
}


def pct(x):
    if x is None:
        return '<span class="na">—</span>'
    cls = "pos" if x >= 0.15 else "neg" if x <= -0.15 else "flat"
    arrow = "▲" if x >= 0.15 else "▼" if x <= -0.15 else "―"
    return f'<span class="{cls}">{arrow}{abs(x):.0%}</span>'


def num(v):
    return "—" if v is None else (f"{v:g}" if v < 10 else f"{v:.0f}")


def spark(series, hot=False):
    vals = [v for v in series if v is not None]
    if not vals:
        return ""
    mx = max(vals) or 1
    w, gap = 9, 4
    bars = []
    for i, v in enumerate(series):
        h = 2 if v is None else max(3, round(26 * v / mx))
        last = i == len(series) - 1
        cls = "b-now" + (" b-hot" if hot else "") if last else ("b-na" if v is None else "b")
        bars.append(f'<rect x="{i * (w + gap)}" y="{28 - h}" width="{w}" height="{h}" rx="1.5" class="{cls}"/>')
    width = len(series) * (w + gap) - gap
    return (f'<svg class="spark" viewBox="0 0 {width} 28" width="{width}" height="28" '
            f'aria-label="直近{len(series)}週の推移">{"".join(bars)}</svg>')


def chips(n):
    out = []
    if n.get("since"):
        out.append(f'<span class="chip">{E(n["since"])}</span>')
    if n.get("pace"):
        cls = "chip chip-urgent" if "短期" in n["pace"] or "急" in n["pace"] else "chip"
        out.append(f'<span class="{cls}">{E(n["pace"])}</span>')
    return f'<div class="chips">{"".join(out)}</div>' if out else ""


def fish_rows(g, notes):
    fn = notes.get("fish", {})
    rows = sorted(g["fish"], key=lambda r: (r["minor"], STATUS.get(fn.get(r["fish"], {}).get("status"), ("", "", 2))[2], -r["reports"]))
    out = []
    for r in rows:
        n = fn.get(r["fish"], {})
        st = STATUS.get(n.get("status", ""))
        hot = n.get("status") == "hot"
        badge = f'<span class="badge {st[1]}">{st[0]}</span>' if st else ""
        size = f'・最大{r["size_max"]:g}{r["size_unit"]}' if r.get("size_max") and r.get("size_unit") else ""
        ships = "".join(
            f'<li><a href="{E(s["url"])}" target="_blank" rel="noopener"><span class="s-name">{E(s["name"])}</span>'
            f'<span class="s-num">平均 {num(s["avg"])}・竿頭 {num(s["top"])}<small>（{s["reports"]}便）</small></span><span class="s-go">›</span></a></li>'
            for s in r.get("ship_list", []))
        out.append(f"""
      <details class="row{' is-hot' if hot else ''}{' minor' if r['minor'] else ''}">
        <summary>
          <div class="r-icon">{icon(r['fish'])}</div>
          <div class="r-main">
            <div class="r-name">{E(r['fish'])}{badge}</div>
            <div class="r-trend">前週 {pct(r['wow'])}<span class="sep"></span>前年 {pct(r['yoy'])}</div>
          </div>
          <div class="r-num"><b>{num(r['avg'])}</b><small>{E(r['unit'])}</small><span class="r-top">竿頭 {num(r['top'])}{size}</span></div>
          <div class="r-spark">{spark(r.get('series', []), hot)}<span>{len(r.get('series', []))}週推移</span></div>
          {chips(n)}
          {f'<p class="r-note">{E(n["note"])}</p>' if n.get('note') else ''}
          <div class="r-more">{r['ships']}軒・{r['reports']}便{'・参考値' if r['minor'] else ''}<span>船宿別の釣果 ▾</span></div>
        </summary>
        <ul class="ships">{ships}</ul>
      </details>""")
    return "".join(out) or '<p class="empty">今週は釣果の報告がありませんでした。</p>'


def by_fish(summary, notes):
    """魚種 -> [(港, row, status)]。参考値は除く。"""
    d = {}
    for g in summary["groups"]:
        fn = notes.get(g["name"], {}).get("fish", {})
        for r in g["fish"]:
            if r["minor"]:
                continue
            d.setdefault(r["fish"], []).append((g["name"], r, fn.get(r["fish"], {}).get("status")))
    def score(item):
        k, lst = item
        best = min(STATUS.get(s, ("", "", 2))[2] for _, _, s in lst)
        return (best, -sum(r["reports"] for _, r, _ in lst))
    return sorted(d.items(), key=score)


def build(summary, picks):
    base = dt.date.fromisoformat(summary["base_date"])
    wk = "月火水木金土日"[base.weekday()]
    notes = picks.get("notes", {})
    w0, w1 = (dt.date.fromisoformat(x) for x in summary["week"])
    period = f"{w0.month}/{w0.day}〜{w1.month}/{w1.day}"
    slides = []

    # ---- 表紙 ----
    cards = []
    for p in picks.get("picks", []):
        n = notes.get(p["group"], {}).get("fish", {}).get(p["fish"], {})
        cards.append(f"""
        <a class="pick" href="#g-{E(p['group'])}">
          <div class="pick-icon">{icon(p['fish'])}</div>
          <div class="pick-body">
            <div class="pick-where">{E(p['group'])}</div>
            <div class="pick-fish">{E(p['fish'])}</div>
            <p class="pick-why">{E(p.get('reason', ''))}</p>
            {chips(n)}
          </div>
          <div class="pick-go">港の詳細 <span>›</span></div>
        </a>""")
    if not cards:
        cards.append('<p class="empty">今週は、とくに推せる釣り物はありませんでした。</p>')
    toc = "".join(
        f'<a href="#g-{E(g["name"])}"><i class="num-pin">{i}</i><b>{E(g["name"])}</b><span>{len([r for r in g["fish"] if not r["minor"]])}魚種 ›</span></a>'
        for i, g in enumerate(summary["groups"], 1))
    overview = json.dumps([[g["name"], *GEO[g["name"]]["c"]] for g in summary["groups"] if g["name"] in GEO], ensure_ascii=False)
    slides.append(f"""
  <section class="slide cover" id="top">
    <div class="wrap">
      <div class="eyebrow">KANTO BOAT FISHING · WEEKLY</div>
      <h1>週間釣果レポート</h1>
      <p class="issue">{base.year}年{base.month}月{base.day}日（{wk}）号<span>集計期間 {period}</span></p>
      <div class="sec-title">全エリア総評</div>
      <p class="overall">{E(picks.get('headline', '今週の総評はありません。'))}</p>
      <div class="sec-title">今週の狙い目</div>
      <div class="picks">{''.join(cards)}</div>
      <div class="sec-title">エリア</div>
      <div class="map map-overview" data-overview='{E(overview)}'></div>
      <nav class="toc">{toc}</nav>
      <a class="to-fish" href="#by-fish">魚種別に、好調な港を見る <span>›</span></a>
      <p class="hint">横にスワイプすると、魚種別・エリア別のページに進みます</p>
    </div>
    <svg class="waves" viewBox="0 0 1200 60" preserveAspectRatio="none" aria-hidden="true"><path d="M0,30 C150,0 300,60 450,30 C600,0 750,60 900,30 C1050,0 1200,50 1200,30 L1200,60 L0,60 Z"/></svg>
  </section>""")

    # ---- 魚種別 ----
    fish_cards = []
    for fish, lst in by_fish(summary, notes):
        lst = sorted(lst, key=lambda x: (STATUS.get(x[2], ("", "", 2))[2], -x[1]["reports"]))
        def badge(s):
            return f'<span class="badge {STATUS[s][1]}">{STATUS[s][0]}</span>' if s in STATUS else ""
        items = "".join(
            f'<a class="fp{" fp-hot" if s == "hot" else ""}" href="#g-{E(gname)}"><span class="fp-port">{E(gname)}</span>'
            f'<span class="fp-num">{num(r["avg"])}{E(r["unit"])}</span>{badge(s)}<span class="fp-go">›</span></a>'
            for gname, r, s in lst)
        fish_cards.append(f'<div class="fcard"><div class="fcard-head"><div class="r-icon">{icon(fish)}</div><h3>{E(fish)}</h3></div>{items}</div>')
    slides.append(f"""
  <section class="slide page" id="by-fish">
    <header class="band"><div class="band-in"><a class="back" href="#top">‹ 表紙</a><h2>魚種別</h2><p>魚種ごとに、どの港の調子が良いかを並べています。港名をタップすると、そのエリアのページに移ります。</p></div></header>
    <div class="wrap"><div class="fcards">{''.join(fish_cards)}</div></div>
  </section>""")

    # ---- エリア ----
    for g in summary["groups"]:
        n = notes.get(g["name"], {})
        geo = GEO.get(g["name"], {})
        src = "".join(f'<li><a href="{E(s["url"])}" target="_blank" rel="noopener"><span class="s-name">{E(s["name"])}</span><span class="s-num">{s["reports"]}件</span><span class="s-go">›</span></a></li>'
                      for s in g["sources"])
        mapdata = json.dumps({"c": geo.get("c"), "z": geo.get("z"), "m": geo.get("m", [])}, ensure_ascii=False)
        slides.append(f"""
  <section class="slide page" id="g-{E(g['name'])}">
    <header class="band"><div class="band-in"><a class="back" href="#top">‹ 表紙</a><h2>{E(g['name'])}</h2><p>{E(geo.get('sub', ''))}</p></div>
      <div class="map" data-map='{E(mapdata)}'></div></header>
    <div class="wrap">
      {f'<div class="sec-title">概況</div><p class="g-summary">{E(n["summary"])}</p>' if n.get("summary") else ''}
      <div class="sec-title">魚種別の釣果 <small>タップで船宿ごとの釣果へ</small></div>
      <div class="rows">{fish_rows(g, n)}</div>
      <p class="legend">数値は1人あたりの釣果の目安。船宿ごとに「竿頭とスソの中間」を週平均し、それを船宿間で平均しています。棒グラフは直近の週ごとの推移（右端が今週）。</p>
      <details class="sources"><summary>出典の釣船屋（{len(g['sources'])}軒）</summary><ul class="ships">{src or '<li>なし</li>'}</ul></details>
    </div>
  </section>""")

    return (TEMPLATE.replace("{{TITLE}}", f"週間釣果レポート {base.month}/{base.day}号")
            .replace("{{SLIDES}}", "".join(slides)).replace("{{FISH_CSS}}", FISH_CSS))


TEMPLATE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{{TITLE}}</title>
<meta property="og:title" content="{{TITLE}}">
<meta property="og:description" content="関東の船釣り、港別・魚種別の釣果まとめ（毎週金曜更新）">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&family=Noto+Serif+JP:wght@600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
:root{
  --navy:#0c2238;--navy2:#123a5a;--sea:#1d5f86;--foam:#dfeaf0;
  --paper:#f5f2ea;--card:#fffdf7;--ink:#1b2530;--sub:#5e6b75;--line:#e2dccf;
  --buoy:#d9531e;--buoy-bg:#fdf0e8;--up:#2e7d4f;--down:#8a949c;--steady:#2f6fa3;
  --fish-line:#1d3347;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#0f1a24;--card:#162533;--ink:#e6ecf0;--sub:#9aabb8;--line:#25384a;--buoy:#ff7a45;--buoy-bg:#3a2418;
  --up:#6fcf97;--down:#8a949c;--steady:#74b4e6;--fish-line:#0c1a26;}}
:root[data-theme="dark"]{--paper:#0f1a24;--card:#162533;--ink:#e6ecf0;--sub:#9aabb8;--line:#25384a;--buoy:#ff7a45;--buoy-bg:#3a2418;--up:#6fcf97;--steady:#74b4e6;--fish-line:#0c1a26;}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:var(--paper);color:var(--ink);
  font-family:"Noto Sans JP","Hiragino Sans","Yu Gothic UI",system-ui,sans-serif;-webkit-text-size-adjust:100%;line-height:1.6}
a{color:inherit}
.deck{display:flex;height:100%;overflow-x:auto;scroll-snap-type:x mandatory;scroll-behavior:smooth;overscroll-behavior-x:contain}
.slide{flex:0 0 100%;max-width:100%;height:100%;overflow-y:auto;scroll-snap-align:start;position:relative;padding-bottom:64px}
.wrap{max-width:640px;margin:0 auto;padding:0 16px}
h1,h2,h3,.pick-fish{font-family:"Noto Serif JP",serif;letter-spacing:.02em}
.sec-title{font-size:13px;font-weight:700;letter-spacing:.12em;color:var(--sea);margin:26px 0 10px;display:flex;align-items:center;gap:8px}
.sec-title::before{content:"";width:18px;height:2px;background:currentColor}
.sec-title small{font-weight:400;letter-spacing:0;color:var(--sub);margin-left:auto}

/* 表紙 */
.cover{background:radial-gradient(120% 70% at 80% 0%,#1f5a82 0%,var(--navy2) 35%,var(--navy) 75%);color:#eef4f8}
.cover .wrap{padding-top:28px;padding-bottom:40px}
.cover .sec-title{color:#8fc3e3}
.eyebrow{font-size:11px;letter-spacing:.28em;color:#8fc3e3}
.cover h1{font-size:34px;margin:6px 0 4px;line-height:1.25}
.issue{margin:0;font-size:14px;color:#cfe0ea}.issue span{display:block;font-size:12px;color:#8fb0c4}
.overall{margin:0;font-size:16px;line-height:1.8;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.14);border-radius:14px;padding:14px 16px}
.picks{display:grid;gap:12px}
.pick{display:grid;grid-template-columns:76px 1fr;gap:4px 12px;text-decoration:none;background:#fffdf7;color:#1b2530;border-radius:16px;padding:14px 14px 0;border-left:6px solid var(--buoy);box-shadow:0 6px 18px rgba(0,0,0,.25)}
.pick-icon{width:76px;height:40px;margin-top:22px}
.pick-where{font-size:12px;font-weight:700;color:var(--buoy);letter-spacing:.06em}
.pick-fish{font-size:24px;font-weight:700;line-height:1.3}
.pick-why{margin:4px 0 6px;font-size:14px;line-height:1.65;color:#36424d}
.pick-go{grid-column:1/-1;border-top:1px solid #eee5d6;margin-top:6px;padding:9px 0 11px;font-size:13px;font-weight:700;color:var(--sea);display:flex;justify-content:flex-end;align-items:center;gap:6px}
.pick-go span{font-size:20px;line-height:1}
.pick:active{transform:scale(.99)}
.toc{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}
.toc a{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.16);border-radius:12px;padding:10px 12px;text-decoration:none;display:flex;flex-direction:column}
.toc a b{font-size:15px}.toc a span{font-size:12px;color:#9fc0d4}
.to-fish{display:flex;justify-content:space-between;align-items:center;margin-top:12px;padding:14px 16px;border-radius:12px;background:#eef4f8;color:var(--navy);font-weight:700;text-decoration:none}
.to-fish span{font-size:22px;line-height:1}
.hint{text-align:center;font-size:12px;color:#8fb0c4;margin-top:18px}
.waves{position:absolute;left:0;right:0;bottom:0;width:100%;height:40px;fill:var(--paper);opacity:.10}

/* 中ページ */
.band{background:linear-gradient(160deg,var(--navy2),var(--navy));color:#eef4f8;position:relative}
.band-in{max-width:640px;margin:0 auto;padding:16px 16px 14px}
.band h2{font-size:28px;margin:4px 0 2px}
.band p{margin:0;font-size:13px;color:#a9c6d8}
.back{font-size:13px;color:#8fc3e3;text-decoration:none}
.map{height:150px;background:#cfdde6}
.band .map{max-width:640px;margin:0 auto;border-top:1px solid rgba(255,255,255,.15)}
.map-overview{height:240px;border-radius:14px;overflow:hidden}
.map-label{background:var(--navy);color:#fff;border:none;border-radius:6px;padding:2px 7px;font-size:12px;font-weight:700;box-shadow:none}
.map-label::before{display:none}
.num-pin{display:flex!important;align-items:center;justify-content:center;width:22px;height:22px;border-radius:50%;background:var(--buoy);color:#fff;
  font:700 12px/1 "Noto Sans JP",sans-serif;font-style:normal;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.35)}
.toc a{position:relative;padding-left:40px!important}.toc .num-pin{position:absolute;left:10px;top:50%;transform:translateY(-50%)}
.g-summary{margin:0;font-size:15px;line-height:1.8}
.rows{display:grid;gap:10px}
.row{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.row>summary{list-style:none;cursor:pointer;display:grid;grid-template-columns:52px minmax(0,1fr) auto;gap:2px 10px;padding:12px 14px 8px}
.row>summary::-webkit-details-marker{display:none}
.row.is-hot{border:2px solid var(--buoy);background:var(--buoy-bg)}
.row.minor{opacity:.65}
.r-icon{width:52px;height:28px;align-self:center;grid-row:span 2}
.r-name{font-weight:700;font-size:17px;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.r-trend{font-size:12px;color:var(--sub);display:flex;align-items:center;white-space:nowrap}
.sep{width:1px;height:10px;background:var(--line);margin:0 8px}
.r-num{text-align:right;grid-row:span 2;align-self:center}
.r-num b{font-size:24px;font-family:"Noto Serif JP",serif}.r-num small{font-size:12px;margin-left:1px}
.r-top{display:block;font-size:11px;color:var(--sub);white-space:nowrap}
.r-spark{grid-column:1/-1;display:flex;align-items:flex-end;gap:8px;margin-top:6px}
.r-spark span{font-size:11px;color:var(--sub)}
.spark .b{fill:#b7c8d4}.spark .b-na{fill:var(--line)}.spark .b-now{fill:var(--sea)}.spark .b-hot{fill:var(--buoy)}
.chips{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.chip{font-size:12px;padding:2px 9px;border-radius:999px;background:var(--foam);color:var(--navy2)}
.chip-urgent{background:var(--buoy);color:#fff}
.pick .chips{grid-column:2}
.r-note{grid-column:1/-1;margin:6px 0 0;font-size:13.5px;line-height:1.65}
.r-more{grid-column:1/-1;display:flex;justify-content:space-between;font-size:11.5px;color:var(--sub);border-top:1px dashed var(--line);margin-top:8px;padding-top:7px}
.r-more span{color:var(--sea);font-weight:700}
.row[open] .r-more span{visibility:hidden}
.ships{list-style:none;margin:0;padding:0 8px 8px}
.ships li a{display:flex;align-items:center;gap:8px;padding:10px 8px;border-top:1px solid var(--line);text-decoration:none}
.s-name{font-weight:700;color:var(--sea);flex:1}
.s-num{font-size:12.5px;color:var(--sub)}.s-num small{font-size:11px}
.s-go{font-size:18px;color:var(--sub)}
.badge{font-size:11px;font-weight:700;padding:1px 8px;border-radius:999px;color:#fff;letter-spacing:.04em;font-family:"Noto Sans JP",sans-serif}
.badge.hot{background:var(--buoy)}.badge.up{background:var(--up)}.badge.steady{background:var(--steady)}.badge.down{background:var(--down)}
.pos{color:var(--up);font-weight:700}.neg{color:var(--down);font-weight:700}.flat{color:var(--sub)}.na{color:var(--sub)}
.legend{font-size:11.5px;color:var(--sub);margin:14px 2px}
.sources{margin-top:6px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 12px;font-size:14px}
.sources summary{cursor:pointer;font-weight:700}
.empty{color:var(--sub)}
.fcards{display:grid;gap:10px;margin-top:16px}
.fcard{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:10px 12px}
.fcard-head{display:flex;align-items:center;gap:10px;margin-bottom:4px}
.fcard-head .r-icon{grid-row:auto;width:56px;height:30px}
.fcard h3{margin:0;font-size:18px}
.fp{display:flex;align-items:center;gap:8px;padding:8px 4px;border-top:1px solid var(--line);text-decoration:none}
.fp-port{flex:1;font-weight:700}.fp-num{font-size:13px;color:var(--sub)}.fp-go{color:var(--sub);font-size:18px}
.fp-hot .fp-port{color:var(--buoy)}

.foot{position:fixed;bottom:0;left:0;right:0;display:flex;justify-content:center;align-items:center;gap:6px;padding:12px 12px calc(12px + env(safe-area-inset-bottom));pointer-events:none}
.foot .dot{width:7px;height:7px;border-radius:50%;background:rgba(120,140,155,.45);pointer-events:auto}.foot .dot.on{background:var(--buoy);width:18px;border-radius:4px}
.foot a{position:absolute;right:14px;font-size:11px;color:var(--sub);pointer-events:auto;background:var(--paper);padding:2px 8px;border-radius:999px}
{{FISH_CSS}}
</style>
</head>
<body>
<main class="deck" id="deck">{{SLIDES}}
</main>
<div class="foot" id="dots"><a href="archive/">過去の号</a></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
(function(){
  var deck=document.getElementById('deck'),slides=[].slice.call(deck.children),dots=document.getElementById('dots');
  slides.forEach(function(){var d=document.createElement('span');d.className='dot';dots.insertBefore(d,dots.lastChild);});
  var ds=dots.querySelectorAll('.dot');
  function upd(){var i=Math.round(deck.scrollLeft/deck.clientWidth);ds.forEach(function(d,j){d.classList.toggle('on',i===j);});}
  deck.addEventListener('scroll',upd,{passive:true});upd();
  document.addEventListener('keydown',function(e){if(e.key==='ArrowRight')deck.scrollBy({left:deck.clientWidth});if(e.key==='ArrowLeft')deck.scrollBy({left:-deck.clientWidth});});
  // ページ内リンク: 横スクロールで移動して縦位置を先頭へ
  document.addEventListener('click',function(e){var a=e.target.closest('a[href^="#"]');if(!a)return;var t=document.getElementById(decodeURIComponent(a.getAttribute('href').slice(1)));if(!t)return;
    e.preventDefault();t.scrollTop=0;deck.scrollTo({left:t.offsetLeft});history.replaceState(null,'',a.getAttribute('href'));});
  if(location.hash){var t=document.getElementById(decodeURIComponent(location.hash.slice(1)));if(t){deck.style.scrollBehavior='auto';deck.scrollLeft=t.offsetLeft;deck.style.scrollBehavior='';}}

  if(!window.L)return;
  var tiles='https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png',
      attr='<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank" rel="noopener">国土地理院</a>';
  var still={dragging:false,zoomControl:false,scrollWheelZoom:false,touchZoom:false,doubleClickZoom:false,boxZoom:false,keyboard:false,tap:false};
  function pin(m,lat,lng,label){L.circleMarker([lat,lng],{radius:6,color:'#fff',weight:2,fillColor:'#d9531e',fillOpacity:1}).addTo(m)
    .bindTooltip(label,{permanent:true,direction:'right',offset:[6,0],className:'map-label'});}
  document.querySelectorAll('.map[data-map]').forEach(function(el){var d=JSON.parse(el.dataset.map);if(!d.c)return;
    var m=L.map(el,still).setView(d.c,d.z);L.tileLayer(tiles,{attribution:attr,maxZoom:18}).addTo(m);
    d.m.forEach(function(p){pin(m,p[1],p[2],p[0]);});});
  document.querySelectorAll('.map[data-overview]').forEach(function(el){var d=JSON.parse(el.dataset.overview);
    var m=L.map(el,still);L.tileLayer(tiles,{attribution:attr,maxZoom:18}).addTo(m);
    var b=[];d.forEach(function(p,i){b.push([p[1],p[2]]);
      L.marker([p[1],p[2]],{icon:L.divIcon({className:'num-pin',html:String(i+1),iconSize:[22,22]})}).addTo(m)
       .on('click',function(){var t=document.getElementById('g-'+p[0]);if(t){t.scrollTop=0;deck.scrollTo({left:t.offsetLeft});}});});
    m.fitBounds(b,{padding:[22,22]});});
})();
</script>
</body>
</html>
"""


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else dt.date.today().isoformat()
    summary = json.loads((ROOT / "data" / "summary" / f"{date}.json").read_text(encoding="utf-8"))
    pp = ROOT / "data" / "picks" / f"{date}.json"
    picks = json.loads(pp.read_text(encoding="utf-8")) if pp.exists() else {}
    page = build(summary, picks)
    (ROOT / "index.html").write_text(page, encoding="utf-8")
    arc = ROOT / "archive"
    arc.mkdir(exist_ok=True)
    (arc / f"{date}.html").write_text(page.replace('href="archive/"', 'href="./"'), encoding="utf-8")
    items = sorted((p.stem for p in arc.glob("20*.html")), reverse=True)
    lis = "".join(f'<li><a href="{d}.html">{d.replace("-", "/")} 号</a></li>' for d in items)
    (arc / "index.html").write_text(
        '<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>過去の号</title><style>body{font-family:"Noto Sans JP",system-ui,sans-serif;max-width:640px;margin:0 auto;padding:24px 16px;'
        'background:#f5f2ea;color:#1b2530}@media(prefers-color-scheme:dark){body{background:#0f1a24;color:#e6ecf0}a{color:#8fc3e3}}'
        'h1{font-family:serif}li{margin:10px 0;font-size:17px}</style></head><body><h1>週間釣果レポート 過去の号</h1><p><a href="../">最新号へ</a></p>'
        f'<ul>{lis}</ul></body></html>', encoding="utf-8")
    print("rendered index.html")


if __name__ == "__main__":
    main()
