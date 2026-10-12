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
    "横浜": {"sub": "新山下・本牧・根岸", "c": [35.425, 139.66], "z": 12,
           "m": [["新山下", 35.437, 139.655], ["本牧", 35.414, 139.676], ["根岸", 35.405, 139.632]]},
    "金沢八景": {"sub": "柴・金沢漁港・金沢八景", "c": [35.345, 139.635], "z": 13,
             "m": [["柴", 35.360, 139.641], ["金沢漁港", 35.350, 139.643], ["金沢八景", 35.335, 139.628]]},
    "走水": {"sub": "走水港", "c": [35.255, 139.73], "z": 12,
           "m": [["走水港", 35.258, 139.735]]},
    "東京湾口": {"sub": "新安浦・大津・鴨居・浦賀・久里浜・金田・松輪・剣崎", "c": [35.20, 139.70], "z": 10,
             "m": [["新安浦", 35.283, 139.665], ["大津", 35.262, 139.705], ["鴨居", 35.245, 139.745], ["久里浜", 35.226, 139.713], ["金田", 35.170, 139.685], ["松輪・剣崎", 35.143, 139.676]]},
    "内房": {"sub": "富津・上総湊・竹岡・金谷", "c": [35.235, 139.84], "z": 10,
           "m": [["富津", 35.302, 139.818], ["上総湊", 35.230, 139.846], ["竹岡", 35.200, 139.832], ["金谷", 35.165, 139.825]]},
    "館山": {"sub": "船形・館山・洲崎・川名・伊戸・相浜・布良", "c": [34.96, 139.80], "z": 10,
           "m": [["船形", 35.030, 139.835], ["館山", 34.990, 139.855], ["洲崎", 34.975, 139.760], ["伊戸", 34.945, 139.785], ["相浜・布良", 34.915, 139.840]]},
    "葉山あぶずり": {"sub": "葉山鐙摺港", "c": [35.272, 139.578], "z": 13,
               "m": [["鐙摺港", 35.2735, 139.5775]]},
    "相模湾東側": {"sub": "長井・佐島・芦名・秋谷・葉山芝崎・小坪", "c": [35.245, 139.60], "z": 10,
              "m": [["長井", 35.197, 139.611], ["佐島", 35.219, 139.612], ["秋谷", 35.240, 139.603], ["芝崎", 35.262, 139.574], ["小坪", 35.300, 139.566]]},
    "那珂湊・大洗": {"sub": "那珂湊・大洗", "c": [36.325, 140.59], "z": 11,
               "m": [["那珂湊", 36.337, 140.598], ["大洗", 36.307, 140.574]]},
    "鹿島": {"sub": "鹿嶋旧港・鹿嶋新港・深芝", "c": [35.925, 140.70], "z": 11,
           "m": [["鹿島港", 35.928, 140.697]]},
}


FGEO = {
    "横浜の海釣り施設": {"c": [35.43, 139.66], "z": 11, "m": [["大黒", 35.462, 139.683], ["本牧", 35.416, 139.678], ["磯子", 35.397, 139.633]]},
    "東扇島西公園": {"c": [35.495, 139.748], "z": 13, "m": [["東扇島西公園", 35.4955, 139.7475]]},
    "九十九里海釣りセンター": {"c": [35.537, 140.447], "z": 12, "m": [["九十九里海釣りセンター", 35.5375, 140.4465]]},
}


def pct(x):
    if x is None:
        return '<span class="na">—</span>'
    cls = "pos" if x >= 0.15 else "neg" if x <= -0.15 else "flat"
    arrow = "▲" if x >= 0.15 else "▼" if x <= -0.15 else "―"
    return f'<span class="{cls}">{arrow}{abs(x):.0%}</span>'


def num(v):
    return "—" if v is None else (f"{v:g}" if v < 10 else f"{v:.0f}")


def wt(r):
    """型（重さ）の表示。例: 型 0.4〜2.3kg（最大2.8）"""
    if not r.get("w_hi"):
        return ""
    lo, hi, mx = r["w_lo"], r["w_hi"], r.get("w_max")
    f = lambda v: f"{v:.1f}".rstrip("0").rstrip(".")
    return f'型 {f(lo)}〜{f(hi)}kg' + (f'（最大{f(mx)}）' if mx and mx > hi else "")


def cnt(v):
    """幅の表示用。小さい数は小数1桁、それ以外は整数。"""
    if v is None:
        return "—"
    return f"{v:.1f}".rstrip("0").rstrip(".") if v < 3 else f"{round(v):d}"


def rng(lo, hi, unit, big=True):
    if hi is None:
        return "—"
    if big:
        return f'<span class="lo">{cnt(lo)}〜</span><b>{cnt(hi)}</b><small>{E(unit)}</small>'
    return f"{cnt(lo)}〜{cnt(hi)}{E(unit)}"


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
            f'<figcaption class="lc-cap">週ごとの目安（1人あたり・{unit}）の推移。点をタップすると値を表示</figcaption></figure>')


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
            f'<span class="s-num">{rng(s.get("lo"), s.get("hi"), r["unit"], big=False)}・目安 {num(s["avg"])}<small>（{s["reports"]}便）</small></span><span class="s-go">›</span></a></li>'
            for s in r.get("ship_list", []))
        out.append(f"""
      <details class="row{' is-hot' if hot else ''}{' minor' if r['minor'] else ''}" id="f-{E(g['name'])}-{E(r['fish'])}">
        <summary>
          <div class="r-icon">{icon(r['fish'])}</div>
          <div class="r-main">
            <div class="r-name">{E(r['fish'])}{badge}</div>
            <div class="r-trend">前週 {pct(r['wow'])}<span class="sep"></span>前年 {pct(r['yoy'])}</div>
          </div>
          <div class="r-num"><span class="r-lab">スソ〜竿頭</span>{rng(r.get('lo_typ'), r.get('hi_typ'), r['unit'])}<span class="r-mid">目安 <b>{num(r['avg'])}</b></span><span class="r-top">週最高 {num(r['top'])}{size}</span>{f'<span class="r-wt">{wt(r)}</span>' if wt(r) else ''}</div>
          <div class="r-spark">{spark(r.get('series', []), hot)}<span>{len(r.get('series', []))}週推移</span></div>
          {chips(n)}
          {f'<p class="r-note">{E(n["note"])}</p>' if n.get('note') else ''}
          <div class="r-more">{r['ships']}軒・{r['reports']}便{f"・標準以上 {r['steady_good']}/{r['steady_total']}便" if r.get('steady_good') is not None else ''}{'・参考値' if r['minor'] else ''}<span>船宿別の釣果 ▾</span></div>
        </summary>
        {line_chart(r, weeks, hot)}
        <ul class="ships">{ships}</ul>
      </details>""")
    return "".join(out) or '<p class="empty">今週は釣果の報告がありませんでした。</p>'


def facility_rows(fa, notes, weeks=()):
    fn = notes.get("fish", {})
    rows = sorted(fa["fish"], key=lambda r: (r["minor"], STATUS.get(fn.get(r["fish"], {}).get("status"), ("", "", 2))[2]))
    out = []
    for r in rows:
        if r["minor"] and fa["kind"] != "count":
            continue
        n = fn.get(r["fish"], {})
        st = STATUS.get(n.get("status", ""))
        hot = n.get("status") == "hot"
        badge = f'<span class="badge {st[1]}">{st[0]}</span>' if st else ""
        if fa["kind"] == "count":
            size = f'{cnt(r["size_min"])}〜{cnt(r["size_max"])}{E(r["size_unit"])}' if r.get("size_max") else ""
            num_html = (f'<span class="r-lab">来場者100人あたり</span><b>{num(r["per100"])}</b><small>匹</small>'
                        f'<span class="r-mid">週計 <b>{r["total"]:,}</b>匹</span><span class="r-top">{size}</span>')
            trend = f'前週 {pct(r.get("wow"))}<span class="sep"></span>前年 {pct(r.get("yoy"))}'
            sp = spark(r.get("series", []), hot)
            chart = line_chart({**r, "avg": r["per100"], "unit": "匹/100人"}, weeks, hot)
            detail = "".join(f'<li><span class="s-name s-plain">{E(k)}</span><span class="s-num">{v:,}匹</span></li>' for k, v in r.get("by_facility", {}).items())
            meta = f'{r["days"]}日で釣果{"・参考値" if r["minor"] else ""}'
        else:
            num_html = f'<span class="r-lab">今週あがった日</span><b>{r["days"]}</b><small>/{r["report_days"]}日</small>'
            trend = "週ごとの日数の推移"
            sp = spark(r.get("days_series", []), hot)
            chart = ""
            detail = "".join(f'<li><a href="{E(x["url"])}" target="_blank" rel="noopener"><span class="s-name">{E(x["title"][:28])}</span>'
                             f'<span class="s-num">{x["date"][5:].replace("-", "/")}{("・" + E(x["source"][:12])) if x.get("source") else ""}</span><span class="s-go">›</span></a></li>'
                             for x in r.get("posts", []))
            meta = f'{r["days"]}日で報告'
        out.append(f"""
      <details class="row{' is-hot' if hot else ''}{' minor' if r['minor'] else ''}" id="f-{E(fa['name'])}-{E(r['fish'])}">
        <summary>
          <div class="r-icon">{icon(r['fish'])}</div>
          <div class="r-main"><div class="r-name">{E(r['fish'])}{badge}</div><div class="r-trend">{trend}</div></div>
          <div class="r-num">{num_html}</div>
          <div class="r-spark">{sp}<span>{len(r.get('series') or r.get('days_series') or [])}週推移</span></div>
          {chips(n)}
          {f'<p class="r-note">{E(n["note"])}</p>' if n.get('note') else ''}
          <div class="r-more">{meta}<span>{'施設ごとの内訳' if fa['kind'] == 'count' else '元の釣果・投稿'} ▾</span></div>
        </summary>
        {chart}
        <ul class="ships">{detail or '<li class="s-plain">—</li>'}</ul>
      </details>""")
    return "".join(out) or '<p class="empty">今週は釣果の報告がありませんでした。</p>'


def release_box(fa):
    rel = fa.get("releases") or []
    if not rel:
        return ""
    lis = "".join(f'<li><b>{x["date"][5:].replace("-", "/")}</b>{E(x["text"])}</li>' for x in rel[:6])
    return f'<div class="release"><div class="release-t">放流情報（直近2週）</div><ul>{lis}</ul></div>'


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


def find_row(summary, group, fish):
    """picks の group/fish に対応する集計行を返す。(kind, row)。kind は "ship" / "count" / "days"。"""
    for g in summary.get("groups", []):
        if g["name"] == group:
            for r in g["fish"]:
                if r["fish"] == fish:
                    return "ship", r
    for fa in summary.get("facilities", []):
        if fa["name"] == group:
            for r in fa["fish"]:
                if r["fish"] == fish:
                    return fa["kind"], r
    return None, None


def pick_stats(summary, group, fish, hot=True):
    kind, r = find_row(summary, group, fish)
    if not r:
        return ""
    if kind == "ship":
        big = rng(r.get("lo_typ"), r.get("hi_typ"), r["unit"])
        sub = f'目安 <b>{num(r["avg"])}</b>{E(r["unit"])}・週最高 {num(r["top"])}' + (f'<br><b class="ps-wt">{wt(r)}</b>' if wt(r) else "")
        trend = f'前週 {pct(r.get("wow"))}<span class="sep"></span>前年 {pct(r.get("yoy"))}'
        lab = "スソ〜竿頭"
        series = r.get("series", [])
        extra = f'標準以上 {r["steady_good"]}/{r["steady_total"]}便' if r.get("steady_good") is not None else ""
    elif kind == "count":
        big = f'<b>{num(r["per100"])}</b><small>匹</small>'
        sub = f'週計 <b>{r["total"]:,}</b>匹'
        trend = f'前週 {pct(r.get("wow"))}<span class="sep"></span>前年 {pct(r.get("yoy"))}'
        lab = "来場者100人あたり"
        series = r.get("series", [])
        extra = f'{r["days"]}日で釣果'
    else:
        big = f'<b>{r["days"]}</b><small>/{r["report_days"]}日</small>'
        sub = "今週あがった日"
        trend = ""
        lab = "あがった日"
        series = r.get("days_series", [])
        extra = ""
    return (f'<div class="pick-stats"><div class="ps-num"><span class="ps-lab">{lab}</span>{big}</div>'
            f'<div class="ps-side"><div class="ps-sub">{sub}</div>'
            f'{f"<div class=ps-trend>{trend}</div>" if trend else ""}'
            f'<div class="ps-spark">{spark(series, hot)}<span>{E(extra)}</span></div></div></div>')


def target_box(summary, picks, notes):
    out = []
    for tname in summary.get("targets", []):
        items = []
        for g in summary.get("groups", []):
            for r in g["fish"]:
                if r["fish"] == tname:
                    items.append(("ship", g["name"], r))
        for fa in summary.get("facilities", []):
            for r in fa["fish"]:
                if r["fish"] == tname:
                    items.append((fa["kind"], fa["name"], r))
        def rank(it):
            st = notes.get(it[1], {}).get("fish", {}).get(tname, {}).get("status")
            val = it[2].get("hi_typ") or it[2].get("per100") or it[2].get("days") or 0
            return (it[2].get("minor", False), STATUS.get(st, ("", "", 2))[2], -val)
        lis = []
        for kind, gname, r in sorted(items, key=rank):
            st = STATUS.get(notes.get(gname, {}).get("fish", {}).get(tname, {}).get("status", ""))
            badge = f'<span class="badge {st[1]}">{st[0]}</span>' if st else ""
            if kind == "ship":
                num_html = f'{rng(r.get("lo_typ"), r.get("hi_typ"), r["unit"])}<span class="tg-mid">目安 {num(r["avg"])}</span>'
                trend = f'前週 {pct(r.get("wow"))}<span class="sep"></span>前年 {pct(r.get("yoy"))}'
                ser = r.get("series", [])
            elif kind == "count":
                num_html = f'<b>{num(r["per100"])}</b><small>匹/100人</small>'
                trend = f'前週 {pct(r.get("wow"))}'
                ser = r.get("series", [])
            else:
                num_html = f'<b>{r["days"]}</b><small>/{r["report_days"]}日</small>'
                trend = "あがった日"
                ser = r.get("days_series", [])
            lis.append(f'<a class="tg-row{" minor" if r.get("minor") else ""}" href="#f-{E(gname)}-{E(tname)}">'
                       f'<div class="tg-where">{E(gname)}{badge}<div class="tg-trend">{trend}</div></div>'
                       f'<div class="tg-spark">{spark(ser)}</div><div class="tg-num">{num_html}</div><span class="tg-go">›</span>'
                       + (f'<div class="tg-wtline">{wt(r) or "型 情報なし"}</div>' if kind == "ship" else "") + '</a>')
        note = picks.get("targets", {}).get(tname, {})
        note = note.get("summary") if isinstance(note, dict) else note
        out.append(f"""
      <section class="target">
        <div class="tg-head"><div class="tg-icon">{icon(tname)}</div><div><div class="tg-kicker">TARGET</div><h2>ターゲット：{E(tname)}</h2></div></div>
        {f'<p class="tg-note">{E(note)}</p>' if note else ''}
        <div class="tg-list">{''.join(lis) or '<p class="empty">今週は報告がありませんでした。</p>'}</div>
      </section>""")
    return "".join(out)


WX = {0: "晴れ", 1: "晴れ", 2: "晴れ時々曇り", 3: "曇り", 45: "霧", 48: "霧", 51: "小雨", 53: "雨", 55: "雨", 61: "雨", 63: "雨", 65: "大雨",
      80: "にわか雨", 81: "にわか雨", 82: "強いにわか雨", 95: "雷雨", 96: "雷雨", 99: "雷雨"}
WX_ICON = {"晴れ": "☀", "晴れ時々曇り": "⛅", "曇り": "☁", "霧": "🌫", "小雨": "🌦", "雨": "☔", "大雨": "☔", "にわか雨": "🌦", "強いにわか雨": "☔", "雷雨": "⛈"}


def sea_rank(x):
    """出船しやすさの目安。波と風から。"""
    w, v = x.get("wave") or 0, x.get("wind") or 0
    if w >= 1.5 or v >= 10:
        return "bad", "厳しい"
    if w >= 1.0 or v >= 7:
        return "mid", "注意"
    return "good", "良好"


FC_ALIAS = {"横浜の海釣り施設": "横浜", "東扇島西公園": "羽田", "九十九里海釣りセンター": "九十九里"}


def fc_days_head(fc):
    wk = "月火水木金土日"
    return "".join(f'<div class="fc-day">{dt.date.fromisoformat(d).month}/{dt.date.fromisoformat(d).day}（{wk[dt.date.fromisoformat(d).weekday()]}）<span>{fc["tide"][d]}</span></div>' for d in fc["days"])


def fc_link(fc, name):
    """その地点の時間帯別予報（Windy）。"""
    pt = (fc.get("points") or {}).get(name) or (fc.get("points") or {}).get(FC_ALIAS.get(name, ""))
    if not pt:
        return ""
    la, lo = pt
    return f"https://www.windy.com/{la:.3f}/{lo:.3f}?waves,{la:.3f},{lo:.3f},10"


def fc_cells(fc, name):
    per = fc["areas"].get(name) or fc["areas"].get(FC_ALIAS.get(name, ""), {})
    link = fc_link(fc, name)
    cells = []
    for d in fc["days"]:
        x = per.get(d) or {}
        if x.get("wind") is None:
            cells.append('<div class="fc-cell">—</div>')
            continue
        cls, lab = sea_rank(x)
        wx = WX.get(x.get("code"), "")
        hm = lambda t: t.lstrip("0") if not t.startswith("00") else "0" + t[2:]
        hi_t = "・".join(hm(t) for a, t in x.get("tides", []) if a == "満")
        lo_t = "・".join(hm(t) for a, t in x.get("tides", []) if a == "干")
        tides = (f"満 {hi_t}" if hi_t else "") + (" / " if hi_t and lo_t else "") + (f"干 {lo_t}" if lo_t else "")
        period = f'<small>（周期{x["period"]:.0f}秒）</small>' if x.get("period") else ""
        wave = x.get("wave") if x.get("wave") is not None else "—"
        cells.append(f'<a class="fc-cell {cls}" href="{E(link)}" target="_blank" rel="noopener"><div class="fc-top"><span class="fc-wx">{WX_ICON.get(wx, "")} {wx}</span><span class="fc-rank">{lab}</span></div>'
                     f'<div class="fc-l">波 <b>{wave}</b>m{period}</div>'
                     f'<div class="fc-l">風 {E(x.get("wdir", ""))} <b>{x["wind"]:.0f}</b>m/s<small>（突風{x["gust"]:.0f}）</small></div>'
                     f'<div class="fc-l fc-tide">{tides}</div><div class="fc-rain">降水 {x.get("rain", "—")}%<span class="fc-more">時間別 ›</span></div></a>')
    return "".join(cells)


FC_SRC = '<p class="fc-src">予報: Open-Meteo（各エリアの沖合の地点）。潮回りは月齢から、満潮・干潮は予報潮位から計算した目安です。各日の欄をタップすると、その地点の時間帯別の予報（Windy・外部サイト）が開きます。出船の可否は必ず船宿にご確認ください。</p>'


def forecast_link(summary):
    fc = summary.get("forecast")
    if not fc or not fc.get("areas"):
        return ""
    wk = "月火水木金土日"
    ds = "・".join(f'{dt.date.fromisoformat(d).month}/{dt.date.fromisoformat(d).day}{wk[dt.date.fromisoformat(d).weekday()]}' for d in fc["days"])
    return f'<a class="to-fc" href="#forecast"><span class="to-fc-t">🌊 週末の海況</span><span class="to-fc-d">{ds}・風／潮／波高／天気</span><span class="to-fc-go">›</span></a>'


def forecast_slide(summary, picks):
    fc = summary.get("forecast")
    if not fc or not fc.get("areas"):
        return ""
    rows = "".join(f'<div class="fc-row"><div class="fc-name">{E(name)}</div>{fc_cells(fc, name)}</div>' for name in fc["areas"])
    note = picks.get("forecast_note")
    return f"""
  <section class="slide page" id="forecast">
    <header class="band"><div class="band-in"><div class="navrow"><a class="back js-back" href="#top">‹ 戻る</a><a class="back" href="#top">TOP</a></div><h2>週末の海況</h2><p>各エリアの沖合の、風・潮・波高・天気の予報です。</p></div></header>
    <div class="wrap fc-page">
      {f'<div class="sec-title">要点</div><p class="g-summary">{E(note)}</p>' if note else ''}
      <div class="fc-head">{'<div></div>'}{fc_days_head(fc)}</div>
      <div class="fc-rows">{rows}</div>
      {FC_SRC}
    </div>
  </section>"""


def area_forecast(summary, name):
    fc = summary.get("forecast")
    if not fc or not fc.get("areas"):
        return ""
    if name not in fc["areas"] and FC_ALIAS.get(name) not in fc["areas"]:
        return ""
    return (f'<div class="sec-title">週末の海況 <small><a href="#forecast" class="howto-link">全エリア ›</a></small></div>'
            f'<div class="fc-area"><div class="fc-head fc-head2">{fc_days_head(fc)}</div><div class="fc-row fc-row2">{fc_cells(fc, name)}</div></div>')


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
        <a class="pick" href="#f-{E(p['group'])}-{E(p['fish'])}">
          <div class="pick-icon">{icon(p['fish'])}</div>
          <div class="pick-body">
            <div class="pick-where">{E(p['group'])}</div>
            <div class="pick-fish">{E(p['fish'])}</div>
            <p class="pick-why">{E(p.get('reason', ''))}</p>
            {chips(n)}
          </div>
          {pick_stats(summary, p['group'], p['fish'])}
          <div class="pick-go">港の詳細 <span>›</span></div>
        </a>""")
    if not cards:
        cards.append('<p class="empty">今週は、とくに推せる釣り物はありませんでした。</p>')
    toc = "".join(
        f'<a href="#g-{E(g["name"])}"><i class="num-pin">{i}</i><b>{E(g["name"])}</b><span>{len([r for r in g["fish"] if not r["minor"]])}魚種 ›</span></a>'
        for i, g in enumerate(summary["groups"], 1))
    ex = picks.get("excluded", [])
    excluded = ("<div class=\"excluded\"><div class=\"ex-title\">好調ですが、今回は候補から外したもの</div><ul>"
                + "".join(f'<li><a href="#f-{E(x["group"])}-{E(x["fish"])}"><b>{E(x["group"])}の{E(x["fish"])}</b></a>　{E(x.get("text", ""))}</li>' for x in ex)
                + "</ul></div>") if ex else ""
    lg = picks.get("log", [])
    log = ('<div class="sec-title">釣行メモ</div><ul class="log">'
           + "".join(f'<li>{E(x)}</li>' for x in lg) + "</ul>") if lg else ""
    toc_shore = "".join(f'<a href="#g-{E(fa["name"])}"><b>{E(fa["name"])}</b><span>{E(fa["sub"])} ›</span></a>' for fa in summary.get("facilities", []))
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
      <nav class="quick"><a href="#by-fish"><b>魚種別</b><span>好調な港を探す ›</span></a><a href="#areas"><b>エリア別</b><span>港ごとに見る ↓</span></a><a href="#howto"><b>数値の見方</b><span>算出方法 ›</span></a></nav>
      {target_box(summary, picks, notes)}
      <div class="sec-title">全エリア総評</div>
      <p class="overall">{E(picks.get('headline', '今週の総評はありません。'))}</p>
      {forecast_link(summary)}
      <div class="sec-title">今週の狙い目</div>
      <div class="picks">{''.join(cards)}</div>
      {excluded}
      {log}
      <div class="sec-title" id="areas">エリア</div>
      <div class="map map-overview" data-overview='{E(overview)}'></div>
      <nav class="toc">{toc}</nav>
      <div class="sec-title">陸っぱり・施設</div>
      <nav class="toc toc-shore">{toc_shore}</nav>
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
            f'<a class="fp{" fp-hot" if s == "hot" else ""}" href="#f-{E(gname)}-{E(fish)}"><span class="fp-port">{E(gname)}</span>'
            f'<span class="fp-num">{rng(r.get("lo_typ"), r.get("hi_typ"), r["unit"], big=False)}</span>{badge(s)}<span class="fp-go">›</span></a>'
            for gname, r, s in lst)
        fish_cards.append(f'<div class="fcard"><div class="fcard-head"><div class="r-icon">{icon(fish)}</div><h3>{E(fish)}</h3></div>{items}</div>')
    slides.append(f"""
  <section class="slide page" id="by-fish">
    <header class="band"><div class="band-in"><div class="navrow"><a class="back js-back" href="#top">‹ 戻る</a><a class="back" href="#top">TOP</a></div><h2>魚種別</h2><p>魚種ごとに、どの港の調子が良いかを並べています。港名をタップすると、そのエリアのページに移ります。</p></div></header>
    <div class="wrap"><div class="fcards">{''.join(fish_cards)}</div></div>
  </section>""")

    slides.append(forecast_slide(summary, picks))

    # ---- エリア ----
    for g in summary["groups"]:
        n = notes.get(g["name"], {})
        geo = GEO.get(g["name"], {})
        src = "".join(f'<li><a href="{E(s["url"])}" target="_blank" rel="noopener"><span class="s-name">{E(s["name"])}</span><span class="s-num">{s["reports"]}件</span><span class="s-go">›</span></a></li>'
                      for s in g["sources"])
        mapdata = json.dumps({"c": geo.get("c"), "z": geo.get("z"), "m": geo.get("m", [])}, ensure_ascii=False)
        slides.append(f"""
  <section class="slide page" id="g-{E(g['name'])}">
    <header class="band"><div class="band-in"><div class="navrow"><a class="back js-back" href="#top">‹ 戻る</a><a class="back" href="#top">TOP</a></div><h2>{E(g['name'])}</h2><p>{E(geo.get('sub', ''))}</p></div>
      <div class="map" data-map='{E(mapdata)}'></div></header>
    <div class="wrap">
      {area_forecast(summary, g['name'])}
      {f'<div class="sec-title">概況</div><p class="g-summary">{E(n["summary"])}</p>' if n.get("summary") else ''}
      <div class="sec-title">魚種別の釣果 <small><a href="#howto" class="howto-link">数値の見方 ›</a></small></div>
      <div class="rows">{fish_rows(g, n, weeks_old_first)}</div>
      <p class="legend"><a href="#howto" class="howto-link">数値の見方・算出方法 ›</a><br>大きな数字は「ふつうの日の竿頭」、左の小さな数字は「ふつうの日のスソ」（船宿ごとの週の中央値を船宿間で平均）。「目安」はスソと竿頭の真ん中から出した1人あたりの目安。1日だけの大釣りや不調に左右されにくい値です。「標準以上」は、今週の便のうち、ここ5週の標準を上回った便の数。棒グラフは週ごとの推移（右端が今週）。</p>
      <details class="sources"><summary>出典の釣船屋（{len(g['sources'])}軒）</summary><ul class="ships">{src or '<li>なし</li>'}</ul></details>
    </div>
  </section>""")

    for fa in summary.get("facilities", []):
        n = notes.get(fa["name"], {})
        geo = FGEO.get(fa["name"], {})
        mapdata = json.dumps({"c": geo.get("c"), "z": geo.get("z"), "m": geo.get("m", [])}, ensure_ascii=False)
        legend = ("大きな数字は、施設が公表する魚種ごとの釣れた数（施設全体の合計）を、その週の来場者数で割って100人あたりにしたもの。混む週末も空いた平日も同じ物差しで比べられます。"
                  if fa["kind"] == "count" else
                  "この釣り場は数の公表がないため、その魚が報告された日数（今週の報告日のうち何日か）で調子を表しています。状態はコメントや投稿の内容も合わせて判断しています。")
        slides.append(f"""
  <section class="slide page" id="g-{E(fa['name'])}">
    <header class="band band-shore"><div class="band-in"><div class="navrow"><a class="back js-back" href="#top">‹ 戻る</a><a class="back" href="#top">TOP</a></div>
      <div class="kind">陸っぱり・施設</div><h2>{E(fa['name'])}</h2><p>{E(fa['sub'])}{f"・今週の来場者 {fa['visitors']:,}人" if fa.get('visitors') else ''}</p></div>
      <div class="map" data-map='{E(mapdata)}'></div></header>
    <div class="wrap">
      {area_forecast(summary, fa['name'])}
      {f'<div class="sec-title">概況</div><p class="g-summary">{E(n["summary"])}</p>' if n.get("summary") else ''}
      {release_box(fa)}
      <div class="sec-title">魚種別の釣果 <small><a href="#howto" class="howto-link">数値の見方 ›</a></small></div>
      <div class="rows">{facility_rows(fa, n, weeks_old_first)}</div>
      <p class="legend">{legend}</p>
      <details class="sources"><summary>出典</summary><ul class="ships"><li><a href="{E(fa['url'])}" target="_blank" rel="noopener"><span class="s-name">{E(fa['name'])}の釣果情報</span><span class="s-go">›</span></a></li></ul></details>
    </div>
  </section>""")
    slides.append(HOWTO)
    return (TEMPLATE.replace("{{TITLE}}", f"たこ部屋週報 第{issue_no}号（{base.month}/{base.day}）")
            .replace("{{SLIDES}}", "".join(slides)).replace("{{FISH_CSS}}", FISH_CSS))


HOWTO = """
  <section class="slide page" id="howto">
    <header class="band"><div class="band-in"><div class="navrow"><a class="back js-back" href="#top">‹ 戻る</a><a class="back" href="#top">TOP</a></div><h2>数値の見方</h2><p>このレポートの数字の出し方と、表示の意味です。</p></div></header>
    <div class="wrap howto">
      <div class="sec-title">スソ〜竿頭（大きな数字）</div>
      <p>各魚種の大きな数字は「<b>ふつうの日の竿頭</b>」、その左の小さな数字は「<b>ふつうの日のスソ</b>」です。船宿が公表する「○〜○匹」の書き方に合わせています。</p>
      <ol>
        <li>船宿ごとに、その週の便の竿頭（最多）とスソ（最少）それぞれの<b>中央値</b>を取ります。</li>
        <li>それを船宿間で平均します（5軒以上なら最も高い船宿・低い船宿を1軒ずつ除く）。</li>
      </ol>
      <p>1日だけの大釣りに引っ張られないよう中央値を使っているので、その週にいちばん多く釣れた数は「週最高」として別に小さく表示しています。</p>
      <div class="sec-title">目安（1人あたり）</div>
      <p>エリアごと・魚種ごとの大きな数字です。その週、そのエリアで「ふつうの日に、ふつうの人が釣れた数」の目安を表します。次の3段階で出しています。</p>
      <ol>
        <li><b>便ごとの値</b>：船宿が公表する「スソ（最少）〜竿頭（最多）」の真ん中を取ります。<br><span class="eg">例: 20〜115匹 → (20＋115)÷2 ＝ 67.5匹</span></li>
        <li><b>船宿ごとの週の値</b>：その船宿の、その週の便の値の<b>中央値</b>を取ります。1日だけの大釣りや不調に左右されにくくするためです。</li>
        <li><b>エリアの値</b>：船宿ごとの値を船宿間で平均します。5軒以上あるときは、最も高い船宿と最も低い船宿を1軒ずつ除きます。船中の合計を1人分の欄に書いたような極端な値も除きます。</li>
      </ol>
      <p class="note">竿頭は突出しやすいため、スソと竿頭の真ん中は、実際の「船中の平均的な人」より少し高めに出る傾向があります。あくまで比較のための目安としてご覧ください。</p>

      <div class="sec-title">そのほかの表示</div>
      <dl>
        <dt>型（タコ）</dt><dd>タコは数だけでなく重さが大事なので、各便の重さの幅（表の欄、なければ船長コメントの「0.3〜1.5kg」「400〜500g級」などの記述）を集め、その中央値を「型 0.4〜2.3kg」のように出しています。かっこ内はその週の最大。重さの記述がない船宿は含まれません。</dd>
        <dt>週最高</dt><dd>その週にエリア内で報告された最多の数（参考値）。判定には使っていません。</dd>
        <dt>前週</dt><dd>1人あたり目安の、前の週との比較。</dd>
        <dt>前年</dt><dd>前年の同じ時期（前後1週間）の1人あたり目安との比較。</dd>
        <dt>標準以上 ○/○便</dt><dd>今週の便のうち、その魚のここ5週の標準（便ごとの値の中央値）を上回った便の数。多いほど、日によるムラが少なく安定しています。</dd>
        <dt>棒グラフ・折れ線</dt><dd>週ごとの1人あたり目安の推移（右端が今週）。点線は前年同期の水準です。</dd>
        <dt>○軒・○便</dt><dd>今週その魚の釣果を報告した船宿の数と、便の数。2便未満のものは「参考値」として薄く表示しています。</dd>
      </dl>

      <div class="sec-title">陸っぱり・施設の数字</div>
      <dl>
        <dt>来場者100人あたり（横浜の海釣り施設）</dt><dd>施設が毎日公表する魚種ごとの釣れた数（施設全体の合計）を、その週の来場者数の合計で割り、100人あたりにしたもの。混む週末も空いた平日も同じ物差しで比べられます。大黒・磯子・本牧の3施設を合わせています。</dd>
        <dt>今週あがった日（東扇島西公園・九十九里海釣りセンター）</dt><dd>数の公表がない釣り場では、その魚が報告された日数で調子を表しています。東扇島西公園は釣果まとめサイト（ウオスク）に集まる釣具店や釣り人の投稿、九十九里海釣りセンターは施設の毎日の釣果記事が元です。</dd>
      </dl>

      <div class="sec-title">週末の海況</div>
      <p>その週末（土・日）の、各エリアの沖合の予報です（Open-Meteo）。波高は最大の波の高さ、周期はウネリの周期、風は最大風速と突風です。潮回りは月齢から、満潮・干潮は予報潮位から計算した目安です。<br>出船しやすさの色は、波1m以上か風7m/s以上で「注意」、波1.5m以上か風10m/s以上で「厳しい」としています。出船の可否は船宿が判断します。</p>

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
      <p>船は、各船宿が<a href="https://www.chowari.jp/" target="_blank" rel="noopener">釣割</a>に掲載している釣果と、一部船宿の公式サイトの釣果を、毎週集計しています。陸っぱり・施設は、横浜フィッシングピアーズ・ウオスク・九十九里海釣りセンターの公開情報が元です。直近5週分と、前年の同じ時期の分を使います。各エリアのページの「出典の釣船屋」から、元の釣果ページを確認できます。</p>
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
<link rel="apple-touch-icon" sizes="180x180" href="https://k600000000-works.github.io/tsuri-report/icons/apple-touch-icon.png?v=2">
<link rel="icon" type="image/png" sizes="32x32" href="https://k600000000-works.github.io/tsuri-report/icons/icon-32.png?v=2">
<link rel="icon" type="image/png" sizes="192x192" href="https://k600000000-works.github.io/tsuri-report/icons/icon-192.png?v=2">
<link rel="icon" type="image/png" sizes="180x180" href="https://k600000000-works.github.io/tsuri-report/icons/apple-touch-icon.png?v=2">
<link rel="apple-touch-icon-precomposed" sizes="180x180" href="https://k600000000-works.github.io/tsuri-report/icons/apple-touch-icon.png?v=2">
<link rel="manifest" href="https://k600000000-works.github.io/tsuri-report/manifest.webmanifest">
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
.to-fc{display:grid;grid-template-columns:1fr auto;align-items:center;gap:2px 10px;margin-top:16px;padding:12px 16px;border-radius:12px;
  background:rgba(255,255,255,.08);border:1px solid rgba(143,195,227,.45);text-decoration:none;color:#eef4f8}
.to-fc-t{font-weight:700;font-size:15px}.to-fc-d{grid-column:1;font-size:12px;color:#a9c6d8}.to-fc-go{grid-row:1/3;grid-column:2;font-size:22px;color:#8fc3e3}
.fc-page .fc-name,.fc-area .fc-name{color:var(--ink)}
.fc-page .fc-day,.fc-area .fc-day{color:var(--ink)}.fc-page .fc-day span,.fc-area .fc-day span{color:var(--sea)}
.fc-page .fc-cell,.fc-area .fc-cell{background:var(--card);border:1px solid var(--line);border-left-width:4px;color:var(--ink)}
.fc-page .fc-cell.good,.fc-area .fc-cell.good{border-left-color:var(--up)}.fc-page .fc-cell.mid,.fc-area .fc-cell.mid{border-left-color:#d9a21b}
.fc-page .fc-cell.bad,.fc-area .fc-cell.bad{border-left-color:var(--buoy);background:var(--buoy-bg)}
.fc-page .fc-rank,.fc-area .fc-rank{background:var(--foam)}
.fc-page .fc-cell.good .fc-rank,.fc-area .fc-cell.good .fc-rank{color:var(--up)}.fc-page .fc-cell.mid .fc-rank,.fc-area .fc-cell.mid .fc-rank{color:#a57a00}
.fc-page .fc-cell.bad .fc-rank,.fc-area .fc-cell.bad .fc-rank{color:var(--buoy)}
.fc-page .fc-l small,.fc-area .fc-l small,.fc-page .fc-tide,.fc-area .fc-tide,.fc-page .fc-rain,.fc-area .fc-rain{color:var(--sub)}
.fc-page .fc-src{color:var(--sub)}
.fc-head2,.fc-row2{grid-template-columns:repeat(2,minmax(0,1fr))!important}
.forecast{margin-top:4px}
.fc-note{margin:0 0 8px;font-size:14px;line-height:1.75;color:#eef4f8}
.fc-head,.fc-row{display:grid;grid-template-columns:62px repeat(2,minmax(0,1fr));gap:6px;align-items:stretch}
.fc-day{text-align:center;font-size:12.5px;font-weight:700;color:#f6ecd6}.fc-day span{display:block;font-size:11px;font-weight:400;color:#c9a96a}
.fc-rows{display:grid;gap:6px;margin-top:6px}
.fc-name{font-size:12.5px;font-weight:700;color:#eef4f8;display:flex;align-items:center;line-height:1.3}
.fc-cell{border-radius:10px;padding:6px 8px;font-size:11.5px;color:#eef4f8;background:rgba(255,255,255,.07);border-left:4px solid #6f8797}
.fc-cell.good{border-left-color:#5cc08a}.fc-cell.mid{border-left-color:#e6b84a}.fc-cell.bad{border-left-color:#f07a64;background:rgba(240,122,100,.14)}
.fc-top{display:flex;justify-content:space-between;align-items:center;gap:4px}
.fc-wx{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.fc-rank{font-size:10.5px;font-weight:700;padding:0 6px;border-radius:999px;background:rgba(255,255,255,.12);white-space:nowrap}
.fc-cell.good .fc-rank{color:#8fe0b0}.fc-cell.mid .fc-rank{color:#f2cf75}.fc-cell.bad .fc-rank{color:#ffb3a3}
.fc-l{margin-top:2px;white-space:nowrap}.fc-l b{font-size:14px;font-family:"Noto Serif JP",serif}.fc-l small{font-size:10px;color:#a9c6d8}
.fc-tide{color:#c9dbe6;font-size:10.5px;white-space:normal;line-height:1.4}.fc-rain{font-size:10.5px;color:#a9c6d8}
.fc-src{font-size:10.5px;color:#8fb0c4;margin:6px 0 0}
a.fc-cell{display:block;text-decoration:none}
.fc-more{float:right;font-weight:700;color:var(--sea)}
.target{margin-top:18px;background:linear-gradient(160deg,rgba(240,122,100,.16),rgba(255,255,255,.06));border:1.5px solid rgba(240,122,100,.6);border-radius:16px;padding:12px 12px 6px}
.tg-head{display:flex;align-items:center;gap:10px}
.tg-icon{width:64px;height:34px}
.tg-kicker{font-size:10px;letter-spacing:.3em;color:#f3a593}
.target h2{margin:0;font-size:21px;color:#fbe9dc}
.tg-note{margin:8px 2px 6px;font-size:14px;line-height:1.75;color:#eef4f8}
.tg-list{display:grid;gap:6px;margin-top:6px}
.tg-row{display:grid;grid-template-columns:minmax(0,1fr) auto auto 12px;align-items:center;gap:8px;padding:9px 10px;border-radius:12px;background:rgba(255,255,255,.07);text-decoration:none;color:#eef4f8}
.tg-row.minor{opacity:.6}
.tg-where{font-weight:700;font-size:14px;display:flex;flex-wrap:wrap;align-items:center;gap:5px}
.tg-trend{width:100%;font-weight:400;font-size:11.5px;color:#a9c6d8;display:flex;align-items:center}
.tg-trend .pos{color:#8fe0b0}.tg-trend .neg{color:#b0bcc4}
.tg-num{text-align:right;line-height:1.1}.tg-num b{font-family:"Noto Serif JP",serif;font-size:22px;color:#fff}.tg-num small{font-size:11px}
.tg-num .lo{font-size:12px;color:#a9c6d8}.tg-mid{display:block;font-size:11px;color:#a9c6d8}
.tg-spark .spark .b{fill:rgba(255,255,255,.3)}.tg-spark .spark .b-now{fill:#f07a64}
.tg-go{color:#a9c6d8;font-size:18px}
.tg-wtline{grid-column:1/-1;font-size:12.5px;font-weight:700;color:#ffd2c4;border-top:1px dashed rgba(255,255,255,.15);padding-top:4px;margin-top:2px}
.r-wt{display:block;font-size:12px;font-weight:700;color:var(--buoy);white-space:nowrap}
.ps-wt{font-size:13px!important;color:var(--buoy)!important;font-family:"Noto Sans JP",sans-serif!important}
.pick-stats{grid-column:1/-1;display:flex;align-items:center;gap:14px;margin:4px 0 2px;padding:8px 10px;background:#f6f1e7;border-radius:10px}
.ps-num{flex:none;line-height:1.1}
.ps-lab{display:block;font-size:10px;color:#6b7680;margin-bottom:2px}
.ps-num b{font-family:"Noto Serif JP",serif;font-size:30px;color:#1b2530}
.ps-num small{font-size:13px;margin-left:1px}
.ps-num .lo{font-size:14px;color:#6b7680;font-family:"Noto Serif JP",serif}
.ps-side{flex:1;min-width:0;font-size:12px;color:#36424d}
.ps-sub b{font-size:15px;font-family:"Noto Serif JP",serif;color:#1b2530}
.ps-trend{display:flex;align-items:center;flex-wrap:wrap;margin-top:2px}
.ps-spark{display:flex;align-items:flex-end;gap:6px;margin-top:4px}.ps-spark span{font-size:10.5px;color:#6b7680}
.pick-stats .spark .b{fill:#c9d5de}.pick-stats .spark .b-now{fill:var(--buoy)}
.pick-go{grid-column:1/-1;border-top:1px solid #eee5d6;margin-top:6px;padding:9px 0 11px;font-size:13px;font-weight:700;color:var(--sea);display:flex;justify-content:flex-end;align-items:center;gap:6px}
.pick-go span{font-size:20px;line-height:1}
.pick:active{transform:scale(.99)}
.excluded{margin-top:12px;font-size:13px;color:#cfe0ea;background:rgba(255,255,255,.05);border:1px dashed rgba(255,255,255,.22);border-radius:12px;padding:10px 14px}
.ex-title{font-size:12px;color:#8fc3e3;margin-bottom:4px}
.excluded ul,.log{margin:0;padding-left:1.1em}.excluded li{margin:3px 0}.excluded a{color:#fff}
.log{font-size:14px;line-height:1.75;color:#dfeaf1}.log li{margin:4px 0}
.toc{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}
.toc a{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.16);border-radius:12px;padding:10px 12px;text-decoration:none;display:flex;flex-direction:column}
.toc a b{font-size:15px}
.toc-shore a{padding-left:12px!important}.toc-shore a b{font-size:13.5px}
.release{margin-top:16px;background:var(--buoy-bg);border:2px solid var(--buoy);border-radius:14px;padding:10px 14px}
.release-t{font-weight:700;color:var(--buoy);font-size:14px;margin-bottom:4px}
.release ul{margin:0;padding-left:0;list-style:none}.release li{font-size:13.5px;line-height:1.65;margin:5px 0}
.release li b{display:inline-block;min-width:3.2em;color:var(--buoy);margin-right:4px}
.band-shore{background:linear-gradient(160deg,#1d4a5e,#123044)}
.kind{font-size:11px;letter-spacing:.2em;color:#9fd3c7;margin-top:6px}
.s-plain{color:var(--ink)!important;font-weight:700}
.ships li:not(:has(a)){display:flex;justify-content:space-between;padding:10px 8px;border-top:1px solid var(--line)}.toc a span{font-size:12px;color:#9fc0d4}
.to-fish{display:flex;justify-content:space-between;align-items:center;margin-top:12px;padding:14px 16px;border-radius:12px;background:#eef4f8;color:var(--navy);font-weight:700;text-decoration:none}
.to-fish span{font-size:22px;line-height:1}
.quick{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:16px 0 4px}
.quick a{display:flex;flex-direction:column;align-items:center;gap:2px;padding:10px 4px;border-radius:12px;text-decoration:none;
  background:rgba(255,255,255,.08);border:1px solid rgba(233,213,168,.35)}
.quick b{font-size:14px;color:#f6ecd6}.quick span{font-size:10.5px;color:#9fc0d4}
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
.waves{display:block;width:100%;height:40px;margin-top:8px;fill:var(--paper);opacity:.10}

/* 中ページ */
.band{background:linear-gradient(160deg,var(--navy2),var(--navy));color:#eef4f8;position:relative}
.band-in{max-width:640px;margin:0 auto;padding:16px 16px 14px}
.band h2{font-size:28px;margin:4px 0 2px}
.band p{margin:0;font-size:13px;color:#a9c6d8}
.back{font-size:13px;color:#8fc3e3;text-decoration:none;padding:4px 0}
.navrow{display:flex;justify-content:space-between}
.map{height:150px;background:#cfdde6}
.band .map{max-width:640px;margin:0 auto;border-top:1px solid rgba(255,255,255,.15)}
.map-overview{height:240px;border-radius:14px;overflow:hidden}
.map{position:relative;cursor:zoom-in}
.map::after{content:"タップで拡大";position:absolute;right:6px;top:6px;z-index:500;font-size:10.5px;background:rgba(12,34,56,.78);color:#fff;padding:2px 8px;border-radius:999px;pointer-events:none}
.map-modal{position:fixed;inset:0;z-index:3000;background:var(--navy);display:flex;flex-direction:column}
.map-modal[hidden]{display:none}
.mm-bar{display:flex;justify-content:space-between;align-items:center;padding:calc(10px + env(safe-area-inset-top)) 14px 10px;color:#f6ecd6}
.mm-bar b{font-family:"Noto Serif JP",serif;font-size:18px}
.mm-bar button{background:none;border:1px solid rgba(233,213,168,.5);color:#f6ecd6;width:36px;height:36px;border-radius:50%;font-size:20px;line-height:1}
#mmMap{flex:1}
.mm-hint{margin:0;padding:8px 14px calc(8px + env(safe-area-inset-bottom));font-size:12px;color:#9fc0d4;text-align:center}
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
.row.flash{animation:flash 1.8s ease-out 1}
@keyframes flash{0%,25%{box-shadow:0 0 0 3px var(--buoy)}100%{box-shadow:0 0 0 0 transparent}}
.r-icon{width:52px;height:28px;align-self:center;grid-row:span 2}
.r-name{font-weight:700;font-size:17px;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.r-trend{font-size:12px;color:var(--sub);display:flex;align-items:center;white-space:nowrap}
.sep{width:1px;height:10px;background:var(--line);margin:0 8px}
.r-num{text-align:right;grid-row:span 2;align-self:center}
.r-num b{font-size:24px;font-family:"Noto Serif JP",serif}.r-num small{font-size:12px;margin-left:1px}
.r-lab{display:block;font-size:10px;color:var(--sub);line-height:1.2}
.r-num .lo{font-size:13px;color:var(--sub);font-family:"Noto Serif JP",serif}
.r-mid{display:block;font-size:12px;color:var(--ink);line-height:1.3}.r-mid b{font-size:15px;font-family:"Noto Serif JP",serif}
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
<div class="map-modal" id="mapModal" hidden><div class="mm-bar"><b id="mmTitle"></b><button type="button" id="mmClose" aria-label="閉じる">×</button></div><div id="mmMap"></div><p class="mm-hint">2本指で拡大・移動できます</p></div>
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
  // ページ移動: アニメーションなしで切り替え、履歴を残す（ブラウザの「戻る」で直前のページへ）
  function jump(id){var t=document.getElementById(id);if(!t)return false;
    if(!t.classList.contains('slide')){var sl=t.closest('.slide');jump(sl.id);
      if(t.tagName==='DETAILS'){t.open=true;t.classList.remove('flash');void t.offsetWidth;t.classList.add('flash');}
      sl.scrollTop=t.offsetTop-(t.tagName==='DETAILS'?70:12);return true;}
    deck.style.scrollSnapType='none';deck.style.scrollBehavior='auto';deck.scrollLeft=t.offsetLeft;
    requestAnimationFrame(function(){requestAnimationFrame(function(){deck.style.scrollSnapType='';deck.style.scrollBehavior='';});});
    return true;}
  function curId(){var i=Math.round(deck.scrollLeft/deck.clientWidth);return slides[i]?slides[i].id:'top';}
  history.replaceState({id:curId()},'',location.hash||'#top');
  document.addEventListener('click',function(e){var a=e.target.closest('a[href^="#"]');if(!a)return;
    if(a.classList.contains('js-back')){e.preventDefault();if(history.state&&history.state.from){history.back();}else{jump('top');history.pushState({id:'top'},'','#top');}return;}
    var id=decodeURIComponent(a.getAttribute('href').slice(1));var t=document.getElementById(id);if(!t)return;e.preventDefault();
    var here=curId();
    if(t.classList.contains('slide')){t.scrollTop=0;}
    if(jump(id))history.pushState({id:id,from:here},'','#'+id);});
  window.addEventListener('popstate',function(e){var id=(e.state&&e.state.id)||decodeURIComponent((location.hash||'#top').slice(1));jump(id);});
  // スワイプで移ったときは、履歴は増やさず現在地だけ更新する
  var swipeT;deck.addEventListener('scroll',function(){clearTimeout(swipeT);swipeT=setTimeout(function(){var id=curId();
    var st=history.state&&document.getElementById(history.state.id);var sid=st?(st.classList.contains('slide')?st.id:st.closest('.slide').id):null;
    if(sid!==id)history.replaceState({id:id,from:history.state&&history.state.from},'','#'+id);},250);},{passive:true});
  if(location.hash){jump(decodeURIComponent(location.hash.slice(1)));}
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
  var modal=document.getElementById('mapModal'),big=null;
  var LEFT={'横浜':1,'金沢八景':1,'葉山あぶずり':1,'相模湾東側':1};
  function openBig(title,draw){document.getElementById('mmTitle').textContent=title;modal.hidden=false;
    if(big){big.remove();big=null;}
    big=L.map('mmMap',{zoomControl:true,tap:false});L.tileLayer(tiles,{attribution:attr,maxZoom:18}).addTo(big);draw(big);
    setTimeout(function(){big.invalidateSize();},50);history.pushState({id:curId(),modal:1},'',location.hash);}
  function closeBig(){if(modal.hidden)return;modal.hidden=true;if(big){big.remove();big=null;}}
  document.getElementById('mmClose').addEventListener('click',function(){if(history.state&&history.state.modal)history.back();else closeBig();});
  window.addEventListener('popstate',function(){closeBig();});
  document.querySelectorAll('.map[data-map]').forEach(function(el){var d=JSON.parse(el.dataset.map);if(!d.c)return;
    var m=L.map(el,still).setView(d.c,d.z);L.tileLayer(tiles,{attribution:attr,maxZoom:18}).addTo(m);
    d.m.forEach(function(p){pin(m,p[1],p[2],p[0]);});
    el.addEventListener('click',function(){var title=el.closest('.slide').querySelector('h2').textContent;
      openBig(title,function(bm){bm.setView(d.c,d.z+1);d.m.forEach(function(p){pin(bm,p[1],p[2],p[0]);});});});});
  document.querySelectorAll('.map[data-overview]').forEach(function(el){var d=JSON.parse(el.dataset.overview);
    var m=L.map(el,still);L.tileLayer(tiles,{attribution:attr,maxZoom:18}).addTo(m);
    var b=[];d.forEach(function(p,i){b.push([p[1],p[2]]);
      L.marker([p[1],p[2]],{icon:L.divIcon({className:'num-pin',html:String(i+1),iconSize:[22,22]})}).addTo(m)
       .on('click',function(){var here=curId();if(jump('g-'+p[0]))history.pushState({id:'g-'+p[0],from:here},'','#g-'+p[0]);});});
    m.fitBounds(b,{padding:[22,22]});
    el.addEventListener('click',function(e){if(e.target.closest('.num-pin'))return;
      openBig('エリア',function(bm){var bb=[];d.forEach(function(p,i){bb.push([p[1],p[2]]);
        L.marker([p[1],p[2]],{icon:L.divIcon({className:'num-pin',html:String(i+1),iconSize:[22,22]})}).addTo(bm)
          .bindTooltip(p[0],{permanent:true,direction:LEFT[p[0]]?'left':'right',offset:[LEFT[p[0]]?-10:10,0],className:'map-label'})
          .on('click',function(){var here=curId();history.back();setTimeout(function(){if(jump('g-'+p[0]))history.pushState({id:'g-'+p[0],from:here},'','#g-'+p[0]);},60);});});
        bm.fitBounds(bb,{padding:[40,40]});});});});
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
    (arc / f"{date}.html").write_text(page.replace('href="archive/"', 'href="./"'), encoding="utf-8")
    items = sorted((p.stem for p in arc.glob("20*.html")), reverse=True)
    lis = "".join(f'<li><a href="{d}.html">{d.replace("-", "/")} 号</a></li>' for d in items)
    (arc / "index.html").write_text(
        '<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>たこ部屋週報 バックナンバー</title><link rel="apple-touch-icon" href="../icons/apple-touch-icon.png?v=2"><link rel="icon" href="../icons/icon-32.png?v=2"><style>body{font-family:"Noto Sans JP",system-ui,sans-serif;max-width:640px;margin:0 auto;padding:24px 16px;'
        'background:#f5f2ea;color:#1b2530}@media(prefers-color-scheme:dark){body{background:#0f1a24;color:#e6ecf0}a{color:#8fc3e3}}'
        'h1{font-family:serif}li{margin:10px 0;font-size:17px}</style></head><body><h1>たこ部屋週報 バックナンバー</h1><p><a href="../">最新号へ</a></p>'
        f'<ul>{lis}</ul></body></html>', encoding="utf-8")
    print("rendered index.html")


if __name__ == "__main__":
    main()
