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
    "wait": ("海況待ち", "wait", 2),
    "down": ("下降", "down", 3),
    "slow": ("低調", "down", 4),
}

# 地図: 中心(lat, lng), ズーム, 港の印
GEO = {
    "羽田": {"sub": "羽田・平和島・品川・川崎", "c": [35.565, 139.75], "z": 11,
           "m": [["羽田", 35.550, 139.752], ["平和島", 35.583, 139.742], ["品川", 35.600, 139.748], ["川崎", 35.533, 139.728]]},
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


def line_chart(r, weeks, hot=False):
    """タップで開く折れ線グラフ（週ごとの値・前年同期の水準）。weeks は古い週→今週の (開始日, 終了日)。"""
    series = r.get("series", [])
    pts = [(i, v) for i, v in enumerate(series) if v is not None]
    if len(pts) < 2:
        return ""
    W, H, L, R, T, B = 320, 150, 34, 58, 16, 26
    ly = r.get("lastyear")
    top = max([v for _, v in pts] + ([ly] if ly else [])) * 1.18 or 1
    x = lambda i: L + (W - L - R) * i / max(len(series) - 1, 1)
    y = lambda v: T + (H - T - B) * (1 - v / top)
    grid = "".join(f'<line x1="{L}" x2="{W - R}" y1="{y(top * k):.1f}" y2="{y(top * k):.1f}" class="lc-grid"/>'
                   f'<text x="{L - 6}" y="{y(top * k) + 3.5:.1f}" class="lc-ax" text-anchor="end">{num(top * k)}</text>'
                   for k in (0, 0.5, 1))
    labels = "".join(f'<text x="{x(i):.1f}" y="{H - 8}" class="lc-ax" text-anchor="middle">{dt.date.fromisoformat(w[0]).month}/{dt.date.fromisoformat(w[0]).day}〜</text>'
                     for i, w in enumerate(weeks))
    ref = ""
    if ly:
        ref = (f'<line x1="{L}" x2="{W - R}" y1="{y(ly):.1f}" y2="{y(ly):.1f}" class="lc-ref"/>'
               f'<text x="{W - R + 6}" y="{y(ly) + (14 if abs(y(ly) - y(series[-1] or 0)) < 12 else 3.5):.1f}" class="lc-reflab">前年同期 {num(ly)}</text>')
    path = "M" + " L".join(f"{x(i):.1f},{y(v):.1f}" for i, v in pts)
    imax = max(pts, key=lambda p: p[1])[0]
    marks, tags = [], []
    unit = E(r.get("unit", ""))
    for i, v in pts:
        last = i == len(series) - 1
        w0 = dt.date.fromisoformat(weeks[i][0])
        cap = f"{w0.month}/{w0.day}からの週: {num(v)}{unit}"
        marks.append(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="{5 if last else 4}" class="lc-pt{" lc-now" if last else ""}{" lc-hot" if last and hot else ""}" data-cap="{E(cap)}"/>'
                     f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="14" class="lc-hit" data-cap="{E(cap)}"/>')
        if last or i == imax:
            tags.append(f'<text x="{x(i):.1f}" y="{y(v) - 9:.1f}" class="lc-val" text-anchor="middle">{num(v)}</text>')
    return (f'<figure class="lc"><svg viewBox="0 0 {W} {H}" role="img" aria-label="{E(r["fish"])}の週ごとの推移">{grid}{ref}'
            f'<path d="{path}" class="lc-line"/>{"".join(marks)}{"".join(tags)}{labels}</svg>'
            f'<figcaption class="lc-cap">週ごとの1人あたり釣果（{unit}）。点をタップすると値を表示</figcaption></figure>')


def chips(n):
    out = []
    if n.get("since"):
        out.append(f'<span class="chip">{E(n["since"])}</span>')
    if n.get("pace"):
        cls = "chip chip-urgent" if "短期" in n["pace"] or "急" in n["pace"] else "chip"
        out.append(f'<span class="{cls}">{E(n["pace"])}</span>')
    return f'<div class="chips">{"".join(out)}</div>' if out else ""


def fish_rows(g, notes, weeks=()):
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
            f'<span class="s-num">目安 {num(s["avg"])}・竿頭 {num(s["top"])}<small>（{s["reports"]}便）</small></span><span class="s-go">›</span></a></li>'
            for s in r.get("ship_list", []))
        out.append(f"""
      <details class="row{' is-hot' if hot else ''}{' minor' if r['minor'] else ''}">
        <summary>
          <div class="r-icon">{icon(r['fish'])}</div>
          <div class="r-main">
            <div class="r-name">{E(r['fish'])}{badge}</div>
            <div class="r-trend">前週 {pct(r['wow'])}<span class="sep"></span>前年 {pct(r['yoy'])}</div>
          </div>
          <div class="r-num"><span class="r-lab">1人あたり目安</span><b>{num(r['avg'])}</b><small>{E(r['unit'])}</small><span class="r-top">竿頭 {num(r['top'])}{size}</span></div>
          <div class="r-spark">{spark(r.get('series', []), hot)}<span>{len(r.get('series', []))}週推移</span></div>
          {chips(n)}
          {f'<p class="r-note">{E(n["note"])}</p>' if n.get('note') else ''}
          <div class="r-more">{r['ships']}軒・{r['reports']}便{f"・標準以上 {r['steady_good']}/{r['steady_total']}便" if r.get('steady_good') is not None else ''}{'・参考値' if r['minor'] else ''}<span>船宿別の釣果 ▾</span></div>
        </summary>
        {line_chart(r, weeks, hot)}
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


OCTO = ('<svg viewBox="0 0 64 64" aria-hidden="true"><path d="M20 30 C16 12 26 4 32 4 C38 4 48 12 44 30 Z" class="o-head"/>'
        '<path d="M22 28 C16 38 8 36 6 46 M27 30 C24 42 20 48 18 58 M32 30 C32 44 30 52 32 60 M37 30 C40 42 44 48 46 58 '
        'M42 28 C48 38 56 36 58 46" class="o-arm"/><circle cx="27" cy="20" r="2.2" class="o-eye"/><circle cx="37" cy="20" r="2.2" class="o-eye"/></svg>')


def build(summary, picks, issue_no=1):
    base = dt.date.fromisoformat(summary["base_date"])
    wk = "月火水木金土日"[base.weekday()]
    notes = picks.get("notes", {})
    w0, w1 = (dt.date.fromisoformat(x) for x in summary["week"])
    period = f"{w0.month}/{w0.day}〜{w1.month}/{w1.day}"
    weeks_old_first = list(reversed(summary.get("weeks", [])))
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
    ex = picks.get("excluded", [])
    excluded = ("<div class=\"excluded\"><div class=\"ex-title\">好調ですが、今回は候補から外したもの</div><ul>"
                + "".join(f'<li><a href="#g-{E(x["group"])}"><b>{E(x["group"])}の{E(x["fish"])}</b></a>　{E(x.get("text", ""))}</li>' for x in ex)
                + "</ul></div>") if ex else ""
    lg = picks.get("log", [])
    log = ('<div class="sec-title">釣行メモ</div><ul class="log">'
           + "".join(f'<li>{E(x)}</li>' for x in lg) + "</ul>") if lg else ""
    overview = json.dumps([[g["name"], *GEO[g["name"]]["c"]] for g in summary["groups"] if g["name"] in GEO], ensure_ascii=False)
    slides.append(f"""
  <section class="slide cover" id="top">
    <div class="wrap">
      <header class="mast">
        <div class="mast-rule"><span></span><i class="mast-emblem">{OCTO}</i><span></span></div>
        <h1 class="mast-title">たこ部屋週報</h1>
        <div class="mast-sub">TAKOBEYA WEEKLY<b>—</b>関東船釣り釣果</div>
        <div class="mast-double"></div>
        <div class="mast-issue"><span>第{issue_no}号</span><span>{base.year}年{base.month}月{base.day}日（{wk}）</span><span>集計 {period}</span></div>
      </header>
      <div class="sec-title">全エリア総評</div>
      <p class="overall">{E(picks.get('headline', '今週の総評はありません。'))}</p>
      <div class="sec-title">今週の狙い目</div>
      <div class="picks">{''.join(cards)}</div>
      {excluded}
      {log}
      <div class="sec-title">エリア</div>
      <div class="map map-overview" data-overview='{E(overview)}'></div>
      <nav class="toc">{toc}</nav>
      <a class="to-fish" href="#by-fish">魚種別に、好調な港を見る <span>›</span></a>
      <a class="to-howto" href="#howto">数値の見方・算出方法 ›</a>
      <p class="hint">横にスワイプすると、魚種別・エリア別のページに進みます</p>
    </div>
    <div class="mast-ghost" aria-hidden="true">{OCTO}</div>
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
      <div class="sec-title">魚種別の釣果 <small><a href="#howto" class="howto-link">数値の見方 ›</a></small></div>
      <div class="rows">{fish_rows(g, n, weeks_old_first)}</div>
      <p class="legend"><a href="#howto" class="howto-link">数値の見方・算出方法 ›</a><br>大きな数字は「1人あたり目安」。①便ごとに、スソ（最少）と竿頭（最多）の真ん中を出す（例: 20〜115匹 → 67.5匹）②船宿ごとに、その週の便の中央値を取る ③船宿間で平均する（5軒以上なら最高・最低の1軒ずつを除く）。1日だけの大釣りや不調に左右されにくい値です。「標準以上」は、今週の便のうち、ここ5週の標準を上回った便の数。棒グラフは週ごとの推移（右端が今週）。</p>
      <details class="sources"><summary>出典の釣船屋（{len(g['sources'])}軒）</summary><ul class="ships">{src or '<li>なし</li>'}</ul></details>
    </div>
  </section>""")

    slides.append(HOWTO)
    return (TEMPLATE.replace("{{TITLE}}", f"たこ部屋週報 第{issue_no}号（{base.month}/{base.day}）")
            .replace("{{SLIDES}}", "".join(slides)).replace("{{FISH_CSS}}", FISH_CSS))


HOWTO = """
  <section class="slide page" id="howto">
    <header class="band"><div class="band-in"><a class="back" href="#top">‹ 表紙</a><h2>数値の見方</h2><p>このレポートの数字の出し方と、表示の意味です。</p></div></header>
    <div class="wrap howto">
      <div class="sec-title">1人あたり目安</div>
      <p>エリアごと・魚種ごとの大きな数字です。その週、そのエリアで「ふつうの日に、ふつうの人が釣れた数」の目安を表します。次の3段階で出しています。</p>
      <ol>
        <li><b>便ごとの値</b>：船宿が公表する「スソ（最少）〜竿頭（最多）」の真ん中を取ります。<br><span class="eg">例: 20〜115匹 → (20＋115)÷2 ＝ 67.5匹</span></li>
        <li><b>船宿ごとの週の値</b>：その船宿の、その週の便の値の<b>中央値</b>を取ります。1日だけの大釣りや不調に左右されにくくするためです。</li>
        <li><b>エリアの値</b>：船宿ごとの値を船宿間で平均します。5軒以上あるときは、最も高い船宿と最も低い船宿を1軒ずつ除きます。船中の合計を1人分の欄に書いたような極端な値も除きます。</li>
      </ol>
      <p class="note">竿頭は突出しやすいため、スソと竿頭の真ん中は、実際の「船中の平均的な人」より少し高めに出る傾向があります。あくまで比較のための目安としてご覧ください。</p>

      <div class="sec-title">そのほかの表示</div>
      <dl>
        <dt>竿頭</dt><dd>その週にエリア内で報告された最多の数（参考値）。判定には使っていません。</dd>
        <dt>前週</dt><dd>1人あたり目安の、前の週との比較。</dd>
        <dt>前年</dt><dd>前年の同じ時期（前後1週間）の1人あたり目安との比較。</dd>
        <dt>標準以上 ○/○便</dt><dd>今週の便のうち、その魚のここ5週の標準（便ごとの値の中央値）を上回った便の数。多いほど、日によるムラが少なく安定しています。</dd>
        <dt>棒グラフ・折れ線</dt><dd>週ごとの1人あたり目安の推移（右端が今週）。点線は前年同期の水準です。</dd>
        <dt>○軒・○便</dt><dd>今週その魚の釣果を報告した船宿の数と、便の数。2便未満のものは「参考値」として薄く表示しています。</dd>
      </dl>

      <div class="sec-title">状態の見方</div>
      <dl class="status-dl">
        <dt><span class="badge hot">狙い目</span></dt><dd>複数の船宿・複数の日で好調が裏付けられ、今週とくに勧められるもの。</dd>
        <dt><span class="badge up">上向き</span></dt><dd>調子が上がってきているもの。</dd>
        <dt><span class="badge steady">安定</span></dt><dd>例年並み・平常の釣果。</dd>
        <dt><span class="badge wait">海況待ち</span></dt><dd>地力はあるものの、今週はウネリや潮で数が落ちたもの。海が落ち着けば戻る見込み。</dd>
        <dt><span class="badge down">下降</span></dt><dd>2週以上続けて下がっている、またはシーズン終盤のもの。</dd>
      </dl>
      <p>状態は、数字だけでなく、各船宿の釣果コメント・直近3週の傾向・前年との比較を合わせて判断しています。</p>

      <div class="sec-title">データについて</div>
      <p>各船宿が<a href="https://www.chowari.jp/" target="_blank" rel="noopener">釣割</a>に掲載している釣果を、毎週集計しています。直近5週分と、前年の同じ時期の分を使います。各エリアのページの「出典の釣船屋」から、元の釣果ページを確認できます。</p>
    </div>
  </section>"""


TEMPLATE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{{TITLE}}</title>
<meta property="og:title" content="{{TITLE}}">
<meta property="og:description" content="関東の船釣り、港別・魚種別の釣果まとめ。毎週金曜更新">
<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">
<link rel="icon" type="image/png" sizes="32x32" href="icons/icon-32.png">
<link rel="icon" type="image/png" sizes="192x192" href="icons/icon-192.png">
<meta name="apple-mobile-web-app-title" content="たこ部屋週報">
<meta name="application-name" content="たこ部屋週報">
<meta name="theme-color" content="#0c2238">
<meta property="og:image" content="https://k600000000-works.github.io/tsuri-report/icons/icon-512.png">
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
.mast{text-align:center;padding-top:6px;position:relative;z-index:1}
.mast-rule{display:flex;align-items:center;gap:12px;color:#c9a96a}
.mast-rule span{flex:1;height:1px;background:linear-gradient(90deg,transparent,#c9a96a)}
.mast-rule span:last-child{background:linear-gradient(90deg,#c9a96a,transparent)}
.mast-emblem{width:42px;height:42px;border:1.5px solid #c9a96a;border-radius:50%;display:flex;align-items:center;justify-content:center}
.mast-emblem svg{width:28px;height:28px}
.mast-emblem .o-head{fill:rgba(240,122,100,.28);stroke:#f07a64;stroke-width:3;stroke-linejoin:round}.mast-emblem .o-arm{fill:none;stroke:#f07a64;stroke-width:3;stroke-linecap:round}.mast-emblem .o-eye{fill:#f07a64}
.mast-title{font-family:"Noto Serif JP",serif;font-weight:700;font-size:44px;letter-spacing:.14em;margin:12px 0 2px;padding-left:.14em;line-height:1.15;
  color:#f6ecd6;text-shadow:0 2px 0 rgba(0,0,0,.25)}
.mast-sub{font-size:11px;letter-spacing:.32em;color:#c9a96a}.mast-sub b{font-weight:400;margin:0 .6em;letter-spacing:0}
.mast-double{height:5px;border-top:1px solid rgba(233,213,168,.55);border-bottom:1px solid rgba(233,213,168,.55);margin:14px 0 8px}
.mast-issue{display:flex;justify-content:space-between;gap:8px;font-size:12px;color:#cfe0ea;flex-wrap:wrap}
.mast-issue span:first-child{font-family:"Noto Serif JP",serif;font-weight:700;color:#f6ecd6}
.mast-ghost{position:absolute;top:-10px;right:-40px;width:240px;height:240px;opacity:.07;pointer-events:none}
.mast-ghost svg{width:100%;height:100%}.mast-ghost .o-head{fill:#ff7a63}.mast-ghost .o-arm{fill:none;stroke:#ff7a63;stroke-width:4;stroke-linecap:round}.mast-ghost .o-eye{fill:var(--navy)}
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
.excluded{margin-top:12px;font-size:13px;color:#cfe0ea;background:rgba(255,255,255,.05);border:1px dashed rgba(255,255,255,.22);border-radius:12px;padding:10px 14px}
.ex-title{font-size:12px;color:#8fc3e3;margin-bottom:4px}
.excluded ul,.log{margin:0;padding-left:1.1em}.excluded li{margin:3px 0}.excluded a{color:#fff}
.log{font-size:14px;line-height:1.75;color:#dfeaf1}.log li{margin:4px 0}
.toc{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}
.toc a{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.16);border-radius:12px;padding:10px 12px;text-decoration:none;display:flex;flex-direction:column}
.toc a b{font-size:15px}.toc a span{font-size:12px;color:#9fc0d4}
.to-fish{display:flex;justify-content:space-between;align-items:center;margin-top:12px;padding:14px 16px;border-radius:12px;background:#eef4f8;color:var(--navy);font-weight:700;text-decoration:none}
.to-fish span{font-size:22px;line-height:1}
.to-howto{display:block;text-align:center;margin-top:12px;font-size:13px;color:#8fc3e3}
.howto-link{color:var(--sea);font-weight:700;text-decoration:none}
.howto p,.howto li,.howto dd{font-size:14.5px;line-height:1.8}
.howto ol{padding-left:1.3em}.howto li{margin:6px 0}
.howto .eg{display:inline-block;margin-top:2px;font-size:13px;color:var(--sub);background:var(--foam);padding:1px 8px;border-radius:6px}
.howto .note{font-size:13px;color:var(--sub);background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.howto dl{margin:0}.howto dt{font-weight:700;margin-top:10px}.howto dd{margin:2px 0 0}
.howto .status-dl dt{margin-top:12px}
.howto a{color:var(--sea)}
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
.r-lab{display:block;font-size:10px;color:var(--sub);line-height:1.2}
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
.lc{margin:4px 14px 6px;padding:10px 4px 2px;border-top:1px solid var(--line)}
.lc svg{width:100%;height:auto;display:block;overflow:visible}
.lc-grid{stroke:var(--line);stroke-width:1}
.lc-ax{font-size:10px;fill:var(--sub)}
.lc-ref{stroke:var(--down);stroke-width:1.5;stroke-dasharray:4 4}
.lc-reflab{font-size:10px;fill:var(--sub)}
.lc-line{fill:none;stroke:var(--sea);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.lc-pt{fill:var(--sea);stroke:var(--card);stroke-width:2}
.lc-now{fill:var(--sea)}.lc-hot{fill:var(--buoy)}
.lc-hit{fill:transparent;cursor:pointer}
.lc-val{font-size:11px;font-weight:700;fill:var(--ink)}
.lc-cap{font-size:11.5px;color:var(--sub);text-align:center;margin-top:2px;min-height:1.5em}
.row.is-hot .lc-pt{stroke:var(--buoy-bg)}
.ships{list-style:none;margin:0;padding:0 8px 8px}
.ships li a{display:flex;align-items:center;gap:8px;padding:10px 8px;border-top:1px solid var(--line);text-decoration:none}
.s-name{font-weight:700;color:var(--sea);flex:1}
.s-num{font-size:12.5px;color:var(--sub)}.s-num small{font-size:11px}
.s-go{font-size:18px;color:var(--sub)}
.badge{font-size:11px;font-weight:700;padding:1px 8px;border-radius:999px;color:#fff;letter-spacing:.04em;font-family:"Noto Sans JP",sans-serif}
.badge.hot{background:var(--buoy)}.badge.up{background:var(--up)}.badge.steady{background:var(--steady)}.badge.down{background:var(--down)}.badge.wait{background:#5b7f99}
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
<div class="foot" id="dots"><a href="archive/">バックナンバー</a></div>
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

  document.addEventListener('click',function(e){var c=e.target.closest('[data-cap]');if(!c)return;
    var f=c.closest('.lc');f.querySelector('.lc-cap').textContent=c.dataset.cap;
    f.querySelectorAll('.lc-pt').forEach(function(p){p.setAttribute('r',p.classList.contains('lc-now')?5:4);});
    var p=c.classList.contains('lc-pt')?c:c.previousElementSibling;if(p)p.setAttribute('r',6.5);});
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
    arc_dir = ROOT / "archive"
    issue_no = len({p.stem for p in arc_dir.glob("20*.html") if p.stem < date} | {date})
    page = build(summary, picks, issue_no)
    (ROOT / "index.html").write_text(page, encoding="utf-8")
    arc = ROOT / "archive"
    arc.mkdir(exist_ok=True)
    (arc / f"{date}.html").write_text(page.replace('href="archive/"', 'href="./"').replace('href="icons/', 'href="../icons/'), encoding="utf-8")
    items = sorted((p.stem for p in arc.glob("20*.html")), reverse=True)
    lis = "".join(f'<li><a href="{d}.html">{d.replace("-", "/")} 号</a></li>' for d in items)
    (arc / "index.html").write_text(
        '<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>たこ部屋週報 バックナンバー</title><link rel="apple-touch-icon" href="../icons/apple-touch-icon.png"><link rel="icon" href="../icons/icon-32.png"><style>body{font-family:"Noto Sans JP",system-ui,sans-serif;max-width:640px;margin:0 auto;padding:24px 16px;'
        'background:#f5f2ea;color:#1b2530}@media(prefers-color-scheme:dark){body{background:#0f1a24;color:#e6ecf0}a{color:#8fc3e3}}'
        'h1{font-family:serif}li{margin:10px 0;font-size:17px}</style></head><body><h1>たこ部屋週報 バックナンバー</h1><p><a href="../">最新号へ</a></p>'
        f'<ul>{lis}</ul></body></html>', encoding="utf-8")
    print("rendered index.html")


if __name__ == "__main__":
    main()
