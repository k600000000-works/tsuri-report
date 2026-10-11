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

ROOT = Path(__file__).resolve().parent.parent
E = html.escape

STATUS = {  # status -> (ラベル, CSSクラス)
    "hot": ("行くべき", "hot"),
    "up": ("上向き", "up"),
    "steady": ("安定", "steady"),
    "down": ("下降", "down"),
    "slow": ("低調", "down"),
}


def pct(x):
    if x is None:
        return '<span class="na">—</span>'
    cls = "pos" if x >= 0.15 else "neg" if x <= -0.15 else "flat"
    arrow = "↑" if x >= 0.15 else "↓" if x <= -0.15 else "→"
    return f'<span class="{cls}">{arrow}{abs(x):.0%}</span>'


def num(v):
    return "—" if v is None else (f"{v:g}" if v < 10 else f"{v:.0f}")


def fish_rows(g, notes):
    out = []
    fn = notes.get("fish", {})
    rank = {"hot": 0, "up": 1, "steady": 2, "down": 3, "slow": 4}
    for r in sorted(g["fish"], key=lambda r: (r["minor"], rank.get(fn.get(r["fish"], {}).get("status"), 2))):
        n = fn.get(r["fish"], {})
        st = STATUS.get(n.get("status", ""))
        badge = f'<span class="badge {st[1]}">{st[0]}</span>' if st else ""
        cls = "row" + (" is-hot" if n.get("status") == "hot" else "") + (" minor" if r["minor"] else "")
        note = f'<div class="note">{E(n["note"])}</div>' if n.get("note") else ""
        size = f' <span class="size">最大{r["size_max"]:g}{r.get("size_unit", "")}</span>' if r.get("size_max") and r.get("size_unit") else ""
        out.append(f"""
      <div class="{cls}">
        <div class="f-name">{E(r['fish'])}{badge}</div>
        <div class="f-num"><b>{num(r['avg'])}</b><small>{E(r['unit'])}</small><span class="top">竿頭 {num(r['top'])}{size}</span></div>
        <div class="f-trend"><span>前週 {pct(r['wow'])}</span><span>前年 {pct(r['yoy'])}</span></div>
        <div class="f-meta">{r['ships']}軒・{r['reports']}便{'・参考値' if r['minor'] else ''}</div>
        {note}
      </div>""")
    return "".join(out) or '<p class="empty">今週は釣果の報告がありませんでした</p>'


def build(summary, picks):
    base = dt.date.fromisoformat(summary["base_date"])
    wk = "月火水木金土日"[base.weekday()]
    notes = picks.get("notes", {})
    slides = []

    # 表紙
    cards = []
    for p in picks.get("picks", []):
        cards.append(f"""
      <a class="pick" href="#g-{E(p['group'])}">
        <div class="pick-where">{E(p['group'])}</div>
        <div class="pick-fish">{E(p['fish'])}</div>
        <div class="pick-why">{E(p.get('reason', ''))}</div>
      </a>""")
    if not cards:
        cards.append('<p class="empty">今週の「行くべき」判定はまだありません</p>')
    toc = "".join(
        f'<a href="#g-{E(g["name"])}">{E(g["name"])}<span>{len([r for r in g["fish"] if not r["minor"]])}魚種</span></a>'
        for g in summary["groups"])
    slides.append(f"""
  <section class="slide cover" id="top">
    <div class="eyebrow">船釣り 週間釣果レポート</div>
    <h1>{base.month}月{base.day}日（{wk}）号</h1>
    <p class="period">集計: {summary['week'][0][5:].replace('-', '/')}〜{summary['week'][1][5:].replace('-', '/')} の釣果</p>
    {f'<p class="headline">{E(picks["headline"])}</p>' if picks.get("headline") else ''}
    <h2 class="sec">🔥 今週行くべき</h2>
    <div class="picks">{''.join(cards)}</div>
    <h2 class="sec">港</h2>
    <nav class="toc">{toc}</nav>
    <p class="hint">→ 横にスワイプで港ごとのページ</p>
  </section>""")

    for g in summary["groups"]:
        n = notes.get(g["name"], {})
        src = "".join(f'<li><a href="{E(s["url"])}" target="_blank" rel="noopener">{E(s["name"])}</a><span>{s["reports"]}件</span></li>'
                      for s in g["sources"])
        slides.append(f"""
  <section class="slide" id="g-{E(g['name'])}">
    <header class="g-head"><h2>{E(g['name'])}</h2><a class="back" href="#top">表紙へ</a></header>
    {f'<p class="g-summary">{E(n["summary"])}</p>' if n.get("summary") else ''}
    <div class="legend">数字＝1人あたりの釣果（各船宿の竿頭〜スソの中間を船宿ごとに平均し、さらに船宿間で平均）</div>
    <div class="rows">{fish_rows(g, n)}</div>
    <details class="sources"><summary>出典の釣船屋（{len(g['sources'])}軒）</summary><ul>{src or '<li>なし</li>'}</ul></details>
  </section>""")

    return TEMPLATE.replace("{{TITLE}}", f"釣果レポート {base.month}/{base.day}").replace("{{SLIDES}}", "".join(slides)).replace(
        "{{UPDATED}}", summary["base_date"])


TEMPLATE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<meta property="og:title" content="{{TITLE}}">
<meta property="og:description" content="関東の港別・魚種別の船釣り釣果まとめ（毎週金曜更新）">
<style>
:root{--bg:#f4f1ea;--card:#fffdf8;--ink:#1d2321;--sub:#5d6662;--line:#e3ddd0;--accent:#0f6b5c;
--hot:#d9480f;--hot-bg:#fff0e6;--up:#2b8a3e;--down:#868e96;--steady:#1c7ed6;}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#121615;--card:#1b2120;--ink:#e9ece9;--sub:#9aa5a0;--line:#2c3432;
--accent:#4fc3a9;--hot:#ff8a4c;--hot-bg:#3a2216;--up:#69db7c;--down:#868e96;--steady:#74c0fc;}}
:root[data-theme="dark"]{--bg:#121615;--card:#1b2120;--ink:#e9ece9;--sub:#9aa5a0;--line:#2c3432;--accent:#4fc3a9;--hot:#ff8a4c;--hot-bg:#3a2216;--up:#69db7c;--down:#868e96;--steady:#74c0fc;}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:var(--bg);color:var(--ink);
font-family:"Hiragino Sans","Noto Sans JP","Yu Gothic UI",system-ui,sans-serif;-webkit-text-size-adjust:100%}
.deck{display:flex;height:100%;overflow-x:auto;scroll-snap-type:x mandatory;scroll-behavior:smooth}
.slide{flex:0 0 100%;max-width:100%;height:100%;overflow-y:auto;scroll-snap-align:start;padding:20px 16px 72px}
.slide>*{max-width:640px;margin-left:auto;margin-right:auto}
.eyebrow{font-size:13px;color:var(--accent);font-weight:700;letter-spacing:.08em}
h1{font-size:28px;margin:6px auto 2px}
.period{color:var(--sub);font-size:13px;margin-top:0}
.headline{font-size:16px;line-height:1.6;background:var(--card);border-left:4px solid var(--accent);padding:10px 12px;border-radius:6px}
.sec{font-size:15px;margin:22px auto 10px;color:var(--sub)}
.picks{display:grid;gap:10px}
.pick{display:block;text-decoration:none;color:inherit;background:var(--hot-bg);border:2px solid var(--hot);border-radius:14px;padding:14px 16px}
.pick-where{font-size:12px;color:var(--hot);font-weight:700}
.pick-fish{font-size:24px;font-weight:800;margin:2px 0 4px}
.pick-why{font-size:14px;line-height:1.55}
.toc{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.toc a{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;text-decoration:none;color:inherit;font-weight:700;font-size:14px;display:flex;justify-content:space-between;align-items:center}
.toc a span{font-weight:400;font-size:12px;color:var(--sub)}
.hint{color:var(--sub);font-size:12px;text-align:center;margin-top:18px}
.g-head{display:flex;justify-content:space-between;align-items:baseline}
.g-head h2{font-size:24px;margin:0}
.back{font-size:13px;color:var(--accent)}
.g-summary{font-size:15px;line-height:1.6;margin:8px auto}
.legend{font-size:11px;color:var(--sub);margin:6px auto 10px}
.rows{display:grid;gap:8px}
.row{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 12px;display:grid;grid-template-columns:1fr auto;gap:2px 10px}
.row.is-hot{border:2px solid var(--hot);background:var(--hot-bg)}
.row.minor{opacity:.6}
.f-name{font-weight:800;font-size:17px;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.f-num{text-align:right;grid-row:span 2}
.f-num b{font-size:24px}.f-num small{font-size:12px;margin-left:1px}
.top{display:block;font-size:11px;color:var(--sub)}
.size{font-size:11px}
.f-trend{font-size:13px;display:flex;gap:10px}
.f-meta{font-size:11px;color:var(--sub)}
.note{grid-column:1/-1;font-size:13px;line-height:1.5;margin-top:4px;color:var(--ink)}
.pos{color:var(--up);font-weight:700}.neg{color:var(--down);font-weight:700}.flat{color:var(--sub)}.na{color:var(--sub)}
.badge{font-size:11px;font-weight:700;padding:2px 7px;border-radius:999px;color:#fff}
.badge.hot{background:var(--hot)}.badge.up{background:var(--up)}.badge.steady{background:var(--steady)}.badge.down{background:var(--down)}
.sources{margin-top:16px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;font-size:14px}
.sources summary{cursor:pointer;font-weight:700}
.sources ul{list-style:none;padding:0;margin:8px 0 0;display:grid;gap:6px}
.sources li{display:flex;justify-content:space-between}
.sources a{color:var(--accent)}
.sources span{color:var(--sub);font-size:12px}
.empty{color:var(--sub)}
.foot{position:fixed;bottom:0;left:0;right:0;display:flex;justify-content:center;gap:6px;padding:10px;background:linear-gradient(transparent,var(--bg) 40%)}
.dot{width:8px;height:8px;border-radius:50%;background:var(--line)}.dot.on{background:var(--accent)}
.foot a{position:absolute;right:16px;bottom:8px;font-size:11px;color:var(--sub)}
</style>
</head>
<body>
<main class="deck" id="deck">{{SLIDES}}
</main>
<div class="foot" id="dots"><a href="archive/">過去のレポート</a></div>
<script>
(function(){
  var deck=document.getElementById('deck'),slides=[].slice.call(deck.children),dots=document.getElementById('dots');
  slides.forEach(function(_,i){var d=document.createElement('span');d.className='dot';dots.insertBefore(d,dots.lastChild);});
  var ds=dots.querySelectorAll('.dot');
  function upd(){var i=Math.round(deck.scrollLeft/deck.clientWidth);ds.forEach(function(d,j){d.classList.toggle('on',i===j);});}
  deck.addEventListener('scroll',upd,{passive:true});upd();
  document.addEventListener('keydown',function(e){if(e.key==='ArrowRight')deck.scrollBy({left:deck.clientWidth});if(e.key==='ArrowLeft')deck.scrollBy({left:-deck.clientWidth});});
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
    lis = "".join(f'<li><a href="{d}.html">{d}</a></li>' for d in items)
    (arc / "index.html").write_text(
        '<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>過去の釣果レポート</title><style>body{font-family:system-ui,sans-serif;max-width:640px;margin:0 auto;padding:20px 16px;'
        'background:#f4f1ea;color:#1d2321}@media(prefers-color-scheme:dark){body{background:#121615;color:#e9ece9}a{color:#4fc3a9}}'
        'li{margin:8px 0;font-size:17px}</style></head><body><h1>過去の釣果レポート</h1><p><a href="../">最新号へ</a></p>'
        f'<ul>{lis}</ul></body></html>', encoding="utf-8")
    print("rendered index.html")


if __name__ == "__main__":
    main()
