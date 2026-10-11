"""魚種イラスト（オリジナルのSVG線画）。左向き・viewBox 0 0 120 60。

色は CSS 変数で決める: --fish-body（塗り）/ --fish-line（線）/ --fish-accent（模様）
"""

EYE = '<circle cx="{x}" cy="{y}" r="2.6" class="eye"/>'


def fusiform(ht, hb, nose=8, base=92, tip=113, fork=0.9, notch=103):
    """紡錘形の魚の胴体。ht/hb は背側・腹側のふくらみ。"""
    return (f"M{nose},30 C{nose + 14},{30 - ht} {base - 34},{30 - ht} {base},{30 - ht * 0.28} "
            f"L{tip},{30 - ht * fork} L{notch},30 L{tip},{30 + hb * fork} L{base},{30 + hb * 0.28} "
            f"C{base - 34},{30 + hb} {nose + 14},{30 + hb} {nose},30 Z")


def svg(inner):
    return f'<svg viewBox="0 0 120 60" class="fish" aria-hidden="true">{inner}</svg>'


ICONS = {
    "アジ": svg(
        f'<path d="M44,18 L52,10 L58,17 Z M64,18 L80,15 L84,21 Z M60,42 L76,44 L80,39 Z" class="fin"/>'
        f'<path d="{fusiform(13, 11)}" class="body"/>'
        '<path d="M30,27 C50,25 66,30 92,30" class="mark" stroke-dasharray="2 2.2"/>'
        '<path d="M24,22 C27,27 27,33 24,38" class="line"/>' + EYE.format(x=17, y=27)),
    "マダイ": svg(
        '<path d="M30,12 L36,4 L44,6 L52,4 L60,6 L68,6 L76,10 L84,16 L60,14 Z" class="fin"/>'
        f'<path d="M8,32 C14,12 50,6 92,22 L112,12 L105,30 L112,48 L92,38 C60,52 22,52 8,32 Z" class="body"/>'
        '<g class="dot"><circle cx="40" cy="22" r="1.4"/><circle cx="52" cy="20" r="1.4"/><circle cx="64" cy="22" r="1.4"/>'
        '<circle cx="46" cy="30" r="1.4"/><circle cx="58" cy="29" r="1.4"/><circle cx="72" cy="27" r="1.4"/></g>'
        '<path d="M26,20 C30,27 30,36 25,43" class="line"/>' + EYE.format(x=19, y=26)),
    "イサキ": svg(
        '<path d="M38,17 L46,8 L60,9 L72,14 L80,19 Z" class="fin"/>'
        f'<path d="{fusiform(14, 11)}" class="body"/>'
        '<path d="M30,23 C55,19 75,22 92,26 M30,31 C55,29 75,30 92,31 M32,37 C55,38 75,36 90,35" class="mark"/>'
        '<path d="M24,22 C27,27 27,34 24,39" class="line"/>' + EYE.format(x=17, y=27)),
    "ワラサ・イナダ": svg(
        '<path d="M46,19 L54,13 L60,18 Z M64,19 L84,17 L88,22 Z M62,41 L80,43 L84,38 Z" class="fin"/>'
        f'<path d="{fusiform(11, 10, nose=5, base=94, tip=116, fork=1.4, notch=104)}" class="body"/>'
        '<path d="M14,29 C40,27 70,28 98,29" class="accent"/>' + EYE.format(x=15, y=27)),
    "カツオ": svg(
        '<path d="M38,17 L46,9 L54,16 Z M60,17 L70,13 L74,18 Z" class="fin"/>'
        f'<path d="{fusiform(15, 14, base=94, tip=116, fork=1.5, notch=104)}" class="body"/>'
        '<path d="M40,36 L84,33 M38,40 L80,37 M40,43.5 L74,41" class="mark"/>'
        '<path d="M26,20 C30,27 30,35 26,41" class="line"/>' + EYE.format(x=18, y=27)),
    "キハダ": svg(
        '<path d="M48,17 L66,0 L64,16 Z M54,42 L72,60 L70,42 Z" class="fin"/>'
        f'<path d="{fusiform(14, 13, base=94, tip=116, fork=1.6, notch=104)}" class="body"/>'
        '<path d="M80,24 l3,0 m3,1 l3,0 M80,36 l3,0 m3,-1 l3,0" class="accent"/>'
        '<path d="M26,20 C30,27 30,35 26,41" class="line"/>' + EYE.format(x=18, y=27)),
    "シロギス": svg(
        '<path d="M40,23 L50,16 L58,22 Z M62,23 L82,21 L84,25 Z" class="fin"/>'
        f'<path d="{fusiform(8, 7, nose=4, base=94, tip=114, fork=1.3, notch=105)}" class="body"/>'
        '<path d="M22,30 C50,29 75,30 94,30" class="mark" stroke-dasharray="1.5 2"/>' + EYE.format(x=14, y=28.5)),
    "アマダイ": svg(
        '<path d="M34,17 L40,11 L88,16 L90,21 Z" class="fin"/>'
        '<path d="M10,22 C12,14 24,14 34,17 C60,18 80,22 94,26 L112,18 L110,30 L112,42 L94,34 C70,42 40,44 20,42 C12,40 8,32 10,22 Z" class="body"/>'
        '<path d="M14,22 L22,22" class="accent"/><path d="M28,18 C31,26 31,34 27,41" class="line"/>' + EYE.format(x=19, y=25)),
    "カワハギ": svg(
        '<path d="M36,14 L40,2 L42,14 Z" class="fin"/>'
        '<path d="M8,30 C10,24 22,14 40,12 C60,12 80,18 92,26 L110,18 L110,42 L92,34 C80,42 60,48 40,48 C22,46 10,36 8,30 Z" class="body"/>'
        '<path d="M56,14 L88,22 L86,25 Z M56,46 L88,38 L86,35 Z" class="fin"/>'
        '<path d="M8,30 L4,30" class="line"/>' + EYE.format(x=24, y=24)),
    "フグ": svg(
        '<path d="M74,16 L84,10 L84,20 Z M74,44 L84,50 L84,40 Z" class="fin"/>'
        '<path d="M10,32 C10,14 30,8 52,9 C76,10 90,20 92,28 L108,20 L106,30 L108,40 L92,34 C88,44 72,52 50,52 C28,52 10,46 10,32 Z" class="body"/>'
        '<g class="dot"><circle cx="40" cy="20" r="1.6"/><circle cx="52" cy="17" r="1.6"/><circle cx="64" cy="20" r="1.6"/>'
        '<circle cx="46" cy="27" r="1.6"/><circle cx="58" cy="26" r="1.6"/><circle cx="72" cy="26" r="1.6"/></g>'
        '<path d="M30,40 C45,44 65,44 80,38" class="accent"/>' + EYE.format(x=26, y=24)),
    "ヒラメ": svg(
        '<path d="M14,30 C18,10 50,4 84,14 C94,18 98,24 100,30 C98,36 94,42 84,46 C50,56 18,50 14,30 Z" class="fin" stroke-dasharray="1.6 1.6"/>'
        '<path d="M20,30 C24,16 50,10 80,18 C88,22 92,26 93,30 C92,34 88,38 80,42 C50,50 24,44 20,30 Z" class="body"/>'
        '<path d="M93,30 L112,22 L110,30 L112,38 Z" class="body"/>'
        '<g class="dot"><circle cx="50" cy="26" r="1.5"/><circle cx="62" cy="34" r="1.5"/><circle cx="72" cy="25" r="1.5"/></g>'
        + EYE.format(x=30, y=22) + EYE.format(x=36, y=19)),
    "タチウオ": svg(
        '<path d="M14,27 C40,20 70,40 116,22" class="fin-line"/>'
        '<path d="M4,31 L14,28 C40,21 70,41 116,23 L117,25 C70,46 40,28 14,34 Z" class="body"/>'
        '<path d="M4,31 L12,31" class="line"/>' + EYE.format(x=14, y=30)),
    "タコ": svg(
        '<path d="M40,30 C34,10 48,2 60,2 C72,2 86,10 80,30 Z" class="body"/>'
        '<path d="M44,28 C38,40 26,40 22,50 M50,30 C46,44 40,50 38,58 M56,30 C56,44 52,52 54,58 '
        'M62,30 C64,44 66,50 72,56 M68,30 C74,42 84,44 90,52 M74,28 C84,36 96,34 100,42 M42,28 C30,32 18,30 12,38 M78,28 C86,28 96,24 104,28" class="arm"/>'
        + EYE.format(x=52, y=22) + EYE.format(x=68, y=22)),
    "イカ": svg(
        '<path d="M80,30 L112,14 L108,30 L112,46 Z" class="fin"/>'
        '<path d="M40,30 C44,22 60,20 104,26 C108,28 108,32 104,34 C60,40 44,38 40,30 Z" class="body"/>'
        '<path d="M42,27 C30,24 18,24 6,20 M42,29 C28,28 16,30 4,30 M42,31 C30,32 18,36 6,40 M42,33 C34,36 24,42 14,46 M42,26 C34,22 26,16 16,12" class="arm"/>'
        + EYE.format(x=44, y=28)),
    "アオリイカ": svg(
        '<path d="M44,22 C60,8 100,10 112,30 C100,50 60,52 44,38 Z" class="fin"/>'
        '<path d="M44,30 C46,22 62,20 104,26 C108,28 108,32 104,34 C62,40 46,38 44,30 Z" class="body"/>'
        '<path d="M46,27 C34,24 20,24 8,20 M46,29 C32,28 18,30 6,30 M46,31 C34,32 20,36 8,40 M46,33 C38,36 28,42 18,46" class="arm"/>'
        '<g class="dot"><circle cx="66" cy="28" r="1.2"/><circle cx="78" cy="31" r="1.2"/><circle cx="90" cy="28" r="1.2"/></g>'
        + EYE.format(x=48, y=28)),
}

FALLBACK = svg(
    '<path d="M42,17 L52,9 L64,12 L76,17 Z" class="fin"/>'
    f'<path d="{fusiform(13, 11)}" class="body"/>'
    '<path d="M24,22 C27,27 27,33 24,38" class="line"/>' + EYE.format(x=17, y=27))

KEYS = [  # 部分一致の優先順
    ("アオリ", "アオリイカ"), ("イカ", "イカ"), ("タコ", "タコ"), ("タチウオ", "タチウオ"),
    ("アジ", "アジ"), ("マダイ", "マダイ"), ("ハナダイ", "マダイ"), ("イサキ", "イサキ"),
    ("ワラサ", "ワラサ・イナダ"), ("イナダ", "ワラサ・イナダ"), ("ブリ", "ワラサ・イナダ"), ("ヒラマサ", "ワラサ・イナダ"),
    ("サワラ", "ワラサ・イナダ"), ("シイラ", "ワラサ・イナダ"), ("カンパチ", "ワラサ・イナダ"),
    ("カツオ", "カツオ"), ("ソウダ", "カツオ"), ("キハダ", "キハダ"), ("マグロ", "キハダ"),
    ("キス", "シロギス"), ("アマダイ", "アマダイ"), ("カワハギ", "カワハギ"), ("ウマヅラ", "カワハギ"),
    ("フグ", "フグ"), ("ヒラメ", "ヒラメ"), ("カレイ", "ヒラメ"), ("マゴチ", "ヒラメ"),
]


# 魚種ごとの配色: (背の色, 腹の色, ヒレ, 模様)
COLORS = {
    "アジ": ("#6d8c66", "#eef0e4", "#cdb867", "#c39b2c"),
    "マダイ": ("#d9574f", "#f8d3ca", "#e98a80", "#3d9ad6"),
    "イサキ": ("#6c7556", "#e2e0cc", "#8f9670", "#4e5640"),
    "ワラサ・イナダ": ("#2c6a8c", "#e8eff3", "#7fa5ba", "#e6bd2e"),
    "カツオ": ("#1e3c66", "#e1e8f0", "#4b6890", "#2b4468"),
    "キハダ": ("#21416c", "#e3eaf1", "#f0c11a", "#f0c11a"),
    "シロギス": ("#e2d8b8", "#fbf8ef", "#eadfb9", "#b8a77a"),
    "アマダイ": ("#e57d71", "#fadad0", "#f0a79c", "#fff3cf"),
    "カワハギ": ("#b19f70", "#ece2c3", "#a08752", "#7a6638"),
    "フグ": ("#6e6c4c", "#f6f2e6", "#8d8a62", "#3a3828"),
    "ヒラメ": ("#8c7454", "#b8a07c", "#a88e66", "#5a462e"),
    "タチウオ": ("#bcc8d3", "#f4f7fa", "#c9d3dc", "#8899a8"),
    "タコ": ("#b24e38", "#dc7c60", "#b24e38", "#7a2e1e"),
    "イカ": ("#efd9c8", "#f9ece2", "#ead0bd", "#b07a5a"),
    "アオリイカ": ("#cdb59c", "#f0e4d6", "#e2d2bf", "#8a5a3a"),
    "_": ("#7f9bb0", "#e7eef3", "#a9bfcd", "#d9480f"),
}


def _paint(key, markup):
    top, bottom, fin, accent = COLORS[key]
    gid = "fg-" + str(list(COLORS).index(key))
    defs = (f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0.15" stop-color="{top}"/><stop offset="0.85" stop-color="{bottom}"/></linearGradient></defs>')
    style = f'--fish-body:url(#{gid});--fish-fin:{fin};--fish-accent:{accent}'
    return markup.replace('class="fish"', f'class="fish" style="{style}"', 1).replace('aria-hidden="true">', 'aria-hidden="true">' + defs, 1)


ICONS = {k: _paint(k, v) for k, v in ICONS.items()}
FALLBACK = _paint("_", FALLBACK)


def icon(name):
    for k, v in KEYS:
        if k in name:
            return ICONS[v]
    return FALLBACK


FISH_CSS = """
.fish{display:block;width:100%;height:100%;overflow:visible}
.fish .body{fill:var(--fish-body);stroke:var(--fish-line);stroke-width:1.6;stroke-linejoin:round}
.fish .fin{fill:var(--fish-fin);stroke:var(--fish-line);stroke-width:1.2;stroke-linejoin:round}
.fish .fin-line{fill:none;stroke:var(--fish-line);stroke-width:1;opacity:.6}
.fish .line,.fish .mark{fill:none;stroke:var(--fish-line);stroke-width:1.1;opacity:.55;stroke-linecap:round}
.fish .accent{fill:none;stroke:var(--fish-accent);stroke-width:2.2;stroke-linecap:round}
.fish .arm{fill:none;stroke:var(--fish-accent);stroke-width:2.2;stroke-linecap:round}
.fish .dot{fill:var(--fish-accent)}
.fish .eye{fill:var(--fish-line)}
"""
