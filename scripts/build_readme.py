#!/usr/bin/env python3
"""Draws the profile README's images into assets/.

GitHub shows a README's SVGs through <img>, where no web font loads and no script runs, so every
letter is drawn as an outline (each glyph stored once, then reused) and all motion is CSS keyframes
inside the file. Colours, type sizes and component shapes are the Portfolio design system's
(design-system/tokens.css and the component READMEs in anna-hovhan/Portfolio). Motion stops under
prefers-reduced-motion, where each image holds one finished still frame.

Run:  pip install fonttools uharfbuzz && python3 scripts/build_readme.py
The three typefaces (all OFL) are downloaded once from google/fonts into scripts/.fonts/.
"""
import io
import math
import os
import urllib.parse
import urllib.request

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "assets")
CACHE = os.path.join(HERE, ".fonts")
SOURCE = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
FILES = {
    "Newsreader.ttf": "newsreader/Newsreader[opsz,wght].ttf",
    "Schibsted.ttf": "schibstedgrotesk/SchibstedGrotesk[wght].ttf",
    "PlexMono-Regular.ttf": "ibmplexmono/IBMPlexMono-Regular.ttf",
    "PlexMono-Medium.ttf": "ibmplexmono/IBMPlexMono-Medium.ttf",
}

# Tokens, from design-system/tokens.css (v19).
BG, SURFACE, RAISED, GHOST = "#05060f", "#0a0b20", "#0b0d26", "#090a1e"
BORDER_SUBTLE, BORDER, BORDER_STRONG, BORDER_NODE, BORDER_MARK = "#191b38", "#1f2246", "#2c2f5e", "#2e3166", "#3a3d78"
RULE_DASHED = "#24275a"
TEXT, MUTED, SUBTLE, TEXT_NODE = "#eeedf7", "#b4b6d4", "#9c9fc4", "#c9c6ea"
LILAC_50, LILAC_100, LILAC_200, LILAC_300, LILAC_400 = "#f5edff", "#eadcff", "#e6d9ff", "#c4a7ff", "#b8a6ff"
VIOLET_500, VIOLET_600, VIOLET_700 = "#8f7cff", "#6d5dfc", "#5b4fe0"
GLOW, ON_ACCENT, SUCCESS = "#b794f6", "#07081a", "#7ee2a8"


def f(v, n=2):
    """A number as short as it can be written."""
    s = ("%.*f" % (n, v)).rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


class Font:
    count = 0

    def __init__(self, file, **axes):
        tt = TTFont(os.path.join(CACHE, file))
        if axes:
            tt = instancer.instantiateVariableFont(tt, axes)
        raw = io.BytesIO()
        tt.save(raw)
        data = raw.getvalue()
        self.tt = TTFont(io.BytesIO(data))
        self.glyphs = self.tt.getGlyphSet()
        self.order = self.tt.getGlyphOrder()
        self.upm = self.tt["head"].unitsPerEm
        self.hb = hb.Font(hb.Face(data))
        Font.count += 1
        self.key = Font.count

    def shape(self, text):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.hb, buf, {"liga": False, "calt": False})
        return [(self.order[i.codepoint], p.x_advance) for i, p in zip(buf.glyph_infos, buf.glyph_positions)]

    def width(self, text, size, track=0.0):
        g = self.shape(text)
        return (sum(a for _, a in g) / self.upm + track * len(g)) * size


class Doc:
    """One SVG: the glyph outlines it uses, its keyframes, and its drawing."""

    def __init__(self, w, h, label):
        self.w, self.h, self.label = w, h, label
        self.ids, self.defs, self.css, self.out = {}, [], [], []

    def add(self, s):
        self.out.append(s)

    def glyph(self, font, name):
        k = (font.key, name)
        if k not in self.ids:
            pen = SVGPathPen(font.glyphs, ntos=lambda v: str(int(round(v))))
            font.glyphs[name].draw(pen)
            d = pen.getCommands()
            self.ids[k] = "g%d" % len(self.ids) if d else None
            if d:
                self.defs.append('<path id="%s" d="%s"/>' % (self.ids[k], d))
        return self.ids[k]

    def text(self, s, font, size, x, y, fill, track=0.0, anchor="start", attrs="", each=None):
        """Outlined text with its baseline at y. `track` is in em; `each(i)` adds attributes per letter."""
        glyphs = font.shape(s)
        sc = size / font.upm
        tr = track * font.upm
        w = (sum(a for _, a in glyphs) + tr * len(glyphs)) * sc
        if anchor == "end":
            x -= w
        elif anchor == "middle":
            x -= w / 2
        uses, cx = [], 0
        for i, (name, adv) in enumerate(glyphs):
            g = self.glyph(font, name)
            if g:
                uses.append('<use href="#%s" x="%d"%s/>' % (g, round(cx), each(i) if each else ""))
            cx += adv + tr
        self.add('<g transform="translate(%s %s) scale(%s -%s)" fill="%s"%s>%s</g>' % (f(x), f(y), f(sc, 5), f(sc, 5), fill, attrs, "".join(uses)))
        return w

    def save(self, name):
        css = "".join(self.css) + "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %s %s" width="%s" height="%s" role="img" aria-label="%s">'
            "<title>%s</title><style>%s</style><defs>%s</defs>%s</svg>"
            % (f(self.w), f(self.h), f(self.w), f(self.h), self.label, self.label, css, "".join(self.defs), "".join(self.out))
        )
        with open(os.path.join(OUT, name), "w") as fh:
            fh.write(svg)
        print("%-28s %6.1f KB" % (name, len(svg) / 1024))


def fonts():
    os.makedirs(CACHE, exist_ok=True)
    for file, path in FILES.items():
        target = os.path.join(CACHE, file)
        if not os.path.exists(target):
            urllib.request.urlretrieve(SOURCE + urllib.parse.quote(path), target)
    return {
        "h1": Font("Newsreader.ttf", wght=400, opsz=60),
        "h2": Font("Newsreader.ttf", wght=400, opsz=36),
        "sans": Font("Schibsted.ttf", wght=400),
        "sans5": Font("Schibsted.ttf", wght=500),
        "sans6": Font("Schibsted.ttf", wght=600),
        "mono": Font("PlexMono-Regular.ttf"),
        "mono5": Font("PlexMono-Medium.ttf"),
    }


def wrap(font, size, text, width):
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if cur and font.width(trial, size) > width:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + [cur]


# ---------------------------------------------------------------- shared pieces


def panel(d, x, y, w, h, r, fill, stroke):
    d.add('<rect x="%s" y="%s" width="%s" height="%s" rx="%s" fill="%s" stroke="%s"/>' % (f(x + 0.5), f(y + 0.5), f(w - 1), f(h - 1), r, fill, stroke))


def mark(d, x, y, size=11, dot=3, outline=BORDER_MARK, fill=VIOLET_500):
    """The system's one mark: a square outline with a centred square dot."""
    d.add('<rect x="%s" y="%s" width="%s" height="%s" fill="none" stroke="%s"/>' % (f(x + 0.5), f(y + 0.5), size - 1, size - 1, outline))
    o = (size - dot) / 2
    d.add('<rect x="%s" y="%s" width="%s" height="%s" fill="%s"/>' % (f(x + o), f(y + o), dot, dot, fill))


def route(points, r=10):
    """A routed line with rounded corners: its path, and the points a pulse passes on the way."""
    d = "M%s %s" % (f(points[0][0]), f(points[0][1]))
    pts = [points[0]]
    for k in range(1, len(points) - 1):
        a, b, c = points[k - 1], points[k], points[k + 1]
        l1, l2 = dist(a, b), dist(b, c)
        rr = min(r, l1 / 2, l2 / 2)
        u = ((b[0] - a[0]) / l1, (b[1] - a[1]) / l1)
        v = ((c[0] - b[0]) / l2, (c[1] - b[1]) / l2)
        e = (b[0] - u[0] * rr, b[1] - u[1] * rr)
        x = (b[0] + v[0] * rr, b[1] + v[1] * rr)
        cen = (e[0] + v[0] * rr, e[1] + v[1] * rr)
        m = (cen[0] + (b[0] - cen[0]) / math.sqrt(2), cen[1] + (b[1] - cen[1]) / math.sqrt(2))
        sweep = 1 if u[0] * v[1] - u[1] * v[0] > 0 else 0
        d += "L%s %sA%s %s 0 0 %d %s %s" % (f(e[0]), f(e[1]), f(rr), f(rr), sweep, f(x[0]), f(x[1]))
        pts += [e, m, x]
    d += "L%s %s" % (f(points[-1][0]), f(points[-1][1]))
    return d, pts + [points[-1]]


class Graph:
    """CodeNode boxes joined by routed lines, with soft pulses that light each node as they arrive."""

    def __init__(self, d, F, cycle, per):
        self.d, self.F, self.cycle, self.per = d, F, cycle, per
        self.nodes, self.edges, self.pulses, self.lit = [], [], [], []

    def node(self, x, cy, label):
        w = round(self.F["mono5"].width(label, 12) + 50)
        self.nodes.append({"x": x, "cy": cy, "w": w, "l": label})
        return len(self.nodes) - 1

    def side(self, a, b, mid):
        """From a's right side, down or up a vertical run at `mid`, into b's left side."""
        A, B = self.nodes[a], self.nodes[b]
        pts = [(A["x"] + A["w"], A["cy"]), (B["x"], B["cy"])]
        if A["cy"] != B["cy"]:
            pts = [pts[0], (mid, A["cy"]), (mid, B["cy"]), pts[1]]
        self.edges.append(route(pts))
        return len(self.edges) - 1

    def drop(self, a, b):
        """From a's foot, down, then into b's right side."""
        A, B = self.nodes[a], self.nodes[b]
        cx = A["x"] + A["w"] / 2
        self.edges.append(route([(cx, A["cy"] + 17), (cx, B["cy"]), (B["x"] + B["w"], B["cy"])]))
        return len(self.edges) - 1

    def pulse(self, start, edges, nodes):
        """One pulse along these edges, `per` seconds each; `nodes` are the ones it lights, in order."""
        self.pulses.append((start, edges))
        self.lit += [(n, start + i * self.per) for i, n in enumerate(nodes)]

    def box(self, n, lit):
        d, x, y = self.d, n["x"], n["cy"] - 17
        if lit:
            d.add('<rect x="%s" y="%s" width="%s" height="34" rx="8" fill="%s" opacity=".55" filter="url(#glow)"/>' % (f(x), f(y), n["w"], GLOW))
        d.add('<rect x="%s" y="%s" width="%s" height="33" rx="8" fill="%s" stroke="%s"/>' % (f(x + 0.5), f(y + 0.5), n["w"] - 1, RAISED, "url(#lit)" if lit else BORDER_NODE))
        d.add('<rect x="%s" y="%s" width="6" height="6" fill="%s"/>' % (f(x + 14), f(n["cy"] - 3), LILAC_50 if lit else VIOLET_700))
        d.text(n["l"], self.F["mono5"], 12, x + 28, n["cy"] + 4.2, "#fff" if lit else TEXT_NODE)

    def draw(self):
        d, cycle = self.d, self.cycle
        d.defs.append('<filter id="glow" x="-40%%" y="-150%%" width="180%%" height="400%%"><feGaussianBlur stdDeviation="8"/></filter>')
        d.defs.append('<linearGradient id="lit" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="%s"/><stop offset="1" stop-color="%s"/></linearGradient>' % (LILAC_100, VIOLET_600))
        for path, _ in self.edges:
            d.add('<path d="%s" fill="none" stroke="%s" stroke-opacity=".38"/>' % (path, VIOLET_500))
        # Pulses: a bright square with three fading squares behind it, under the nodes.
        for i, (start, edges) in enumerate(self.pulses):
            frames = []
            for k, e in enumerate(edges):
                pts = self.edges[e][1]
                run = [0.0]
                for a, b in zip(pts, pts[1:]):
                    run.append(run[-1] + dist(a, b))
                for p, l in zip(pts, run):
                    t = (k + l / run[-1]) * self.per
                    if not frames or t > frames[-1][0]:
                        frames.append((t, p))
            end = frames[-1][0]
            move = lambda p: "transform:translate(%spx,%spx)" % (f(p[0], 1), f(p[1], 1))
            kf = "@keyframes p%d{0%%{%s;opacity:0}%s%%{opacity:1}" % (i, move(frames[0][1]), f(30 / cycle, 3))
            for t, p in frames[1:-1]:
                kf += "%s%%{%s}" % (f(t / cycle * 100, 3), move(p))
            kf += "%s%%{%s;opacity:1}%s%%{opacity:0}100%%{%s;opacity:0}}" % (f(end / cycle * 100, 3), move(frames[-1][1]), f((end + 0.3) / cycle * 100, 3), move(frames[-1][1]))
            d.css.append(kf)
            for s in (3, 2, 1, 0):
                z = 3.5 if s == 0 else 2
                d.add(
                    '<rect class="pulse" x="%s" y="%s" width="%s" height="%s" fill="%s" fill-opacity="%s" style="animation:p%d %ss linear %ss infinite backwards"/>'
                    % (f(-z / 2), f(-z / 2), z, z, LILAC_50 if s == 0 else LILAC_300, f(0.9 if s == 0 else 0.42 - s * 0.09), i, f(cycle), f(start + s * 0.07))
                )
        d.css.append(".pulse{opacity:0}")
        for n in self.nodes:
            self.box(n, False)
        # Lit copies, shown only while a pulse is on the node.
        d.css.append("@keyframes lit{0%%{opacity:0}%s%%{opacity:1}%s%%{opacity:1}%s%%{opacity:0}100%%{opacity:0}}" % (f(35 / cycle, 3), f(85 / cycle, 3), f(150 / cycle, 3)))
        d.css.append(".lit{opacity:0;animation:lit %ss linear infinite backwards}" % f(cycle))
        for n, t in self.lit:
            d.add('<g class="lit" style="animation-delay:%ss">' % f(t - 0.35))
            self.box(self.nodes[n], True)
            d.add("</g>")


# ---------------------------------------------------------------- the images


def hero(F):
    W, H = 900, 400
    d = Doc(W, H, "Anna Hovhannisyan. Enterprise agentic AI, from discovery to delivery. Strategy, data, and execution in one place. AI Technical Architect at Miro, building AI agents, systems and plugins for teams. Beside the text, an agent graph: discovery.md, context/ and data.stack feed agent.plan() and skills/, which lead to agent.build(), mcp://crm and eval.run(), then team.enable().")
    d.defs.append('<clipPath id="card"><rect width="%d" height="%d" rx="16"/></clipPath>' % (W, H))
    d.defs.append('<pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="12" cy="12" r="1" fill="%s" fill-opacity=".09"/></pattern>' % VIOLET_500)
    d.defs.append('<pattern id="dots2" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="12" cy="12" r="1.1" fill="%s" fill-opacity=".5"/></pattern>' % VIOLET_500)
    d.defs.append('<linearGradient id="band"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>')
    d.defs.append('<mask id="wave" maskUnits="userSpaceOnUse" x="0" y="0" width="%d" height="%d"><rect class="wave" x="-420" y="-200" width="340" height="800" fill="url(#band)" transform="skewX(-18)"/></mask>' % (W, H))
    # The ambient dot grid, with a slow wave of light passing through it.
    d.css.append("@keyframes wave{from{transform:translateX(0)}to{transform:translateX(1500px)}}.wave{animation:wave 16s linear infinite}")
    d.add('<g clip-path="url(#card)"><rect width="%d" height="%d" fill="%s"/><rect width="%d" height="%d" fill="url(#dots)"/><g mask="url(#wave)"><rect width="%d" height="%d" fill="url(#dots2)"/></g></g>' % (W, H, BG, W, H, W, H))
    d.add('<rect x=".5" y=".5" width="%d" height="%d" rx="15.5" fill="none" stroke="%s"/>' % (W - 1, H - 1, BORDER))

    # Copy.
    x = 40
    mark(d, x, 39, 12, 4, LILAC_100, "#fff")
    d.text("Anna Hovhannisyan", F["sans6"], 17, x + 24, 51, TEXT, -0.005)
    for i, line in enumerate(["ENTERPRISE AGENTIC AI,", "FROM DISCOVERY TO DELIVERY"]):
        d.text(line, F["mono5"], 12, x, 118 + i * 18, LILAC_300, 0.1)
    d.text("Strategy, data,", F["h1"], 44, x, 190, TEXT, -0.015)
    d.text("and execution", F["h1"], 44, x, 238, TEXT, -0.015)
    d.text("in one place.", F["h1"], 44, x, 286, LILAC_300, -0.015)
    for i, line in enumerate(wrap(F["sans"], 16, "AI Technical Architect at Miro. I build AI agents, systems and plugins for teams.", 316)):
        d.text(line, F["sans"], 16, x, 330 + i * 25.6, MUTED)

    # The agent graph (design-system README, Diagrams), in three columns.
    g = Graph(d, F, cycle=12, per=3)
    a, b, c = 388, 548, 708
    n = [
        g.node(a, 64, "discovery.md"), g.node(a, 176, "context/"), g.node(a, 288, "data.stack"),
        g.node(b, 120, "agent.plan()"), g.node(b, 232, "skills/"),
        g.node(c, 64, "agent.build()"), g.node(c, 176, "mcp://crm"), g.node(c, 288, "eval.run()"),
        g.node(b, 344, "team.enable()"),
    ]
    ab, bc = 536, 696
    e = [g.side(0, 3, ab), g.side(1, 3, ab), g.side(1, 4, ab), g.side(2, 4, ab), g.side(3, 5, bc), g.side(3, 6, bc), g.side(4, 6, bc), g.side(4, 7, bc), g.drop(7, 8)]
    # One pulse per input, a third of a cycle apart.
    g.pulse(0, [e[0], e[4]], [n[0], n[3], n[5]])
    g.pulse(4, [e[2], e[6]], [n[1], n[4], n[6]])
    g.pulse(8, [e[3], e[7], e[8]], [n[2], n[4], n[7], n[8]])
    g.draw()
    d.save("hero.svg")


def prompt(d, x, y):
    """The terminal's prompt sign, drawn (IBM Plex Mono has no such glyph)."""
    d.add('<path d="M%s %sl4.2 4-4.2 4" fill="none" stroke="%s" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>' % (f(x + 1.6), f(y - 8.4), VIOLET_500))


def terminal(F):
    W, PAD, CH, LH = 900, 24, 7.8, 21
    whoami = [
        ("name", "anna hovhannisyan", TEXT),
        ("role", "ai technical architect at miro", TEXT),
        ("focus", "enterprise agentic ai, from discovery to delivery", TEXT),
        ("experience", "11+ years in tech · ai since 2019", TEXT),
        ("in-house", "miro · asics · pwc · monks", TEXT),
        ("based", "amsterdam", TEXT),
        ("site", "annahovhannisyan.com", LILAC_300),
    ]
    steps = [("discover", "use-cases.md"), ("build", "agents/ evals/"), ("scale", "platform/"), ("enable", "playbooks/")]
    H = 40 + 24 + LH + 16 + len(whoami) * LH + 16 + LH + 16 + len(steps) * 29 + 16 + 37 + 16 + LH + 28
    d = Doc(W, H, "A terminal. whoami: Anna Hovhannisyan, AI Technical Architect at Miro. Focus: enterprise agentic AI, from discovery to delivery. 11+ years in tech, AI since 2019. In-house at Miro, ASICS, PwC and Monks. Based in Amsterdam. Then how I work, as four steps that run in a loop: discover ships use-cases.md, build ships agents and evals, scale ships a platform, enable ships playbooks.")
    d.css.append("@keyframes show{from{opacity:0}to{opacity:1}}.k{animation:show 1ms linear backwards}")
    d.css.append("@keyframes blink{50%{opacity:0}}.caret{animation:blink 1.1s steps(1) infinite}")
    d.css.append(".bar{transform-box:fill-box;transform-origin:0 50%}")
    d.defs.append('<clipPath id="win"><rect width="%d" height="%d" rx="16"/></clipPath>' % (W, H))
    d.add('<g clip-path="url(#win)"><rect width="%d" height="%d" fill="%s"/><rect width="%d" height="40" fill="%s"/><rect y="40" width="%d" height="1" fill="%s"/></g>' % (W, H, SURFACE, W, RAISED, W, BORDER))
    d.add('<rect x=".5" y=".5" width="%d" height="%d" rx="15.5" fill="none" stroke="%s"/>' % (W - 1, H - 1, BORDER))
    for i in range(3):
        d.add('<circle cx="%s" cy="20" r="5.5" fill="%s"/>' % (f(21.5 + i * 19), BORDER_STRONG))
    d.add('<circle cx="%s" cy="20" r="3.5" fill="%s"/>' % (f(W - 19.5), SUCCESS))
    d.text("anna-hovhan · zsh", F["mono"], 12, W / 2, 24, SUBTLE, anchor="middle")

    def typed(s, x, y, start, step):
        d.text(s, F["mono"], 13, x, y, MUTED, each=lambda i: ' class="k" style="animation-delay:%ss"' % f(start + i * step))
        return start + len(s) * step

    y = 40 + 24 + 14.5
    prompt(d, PAD, y)
    t = typed("whoami", PAD + 2 * CH, y, 0.6, 0.08)
    y += LH + 16
    t += 0.3
    for key, value, colour in whoami:
        d.add('<g class="k" style="animation-delay:%ss">' % f(t))
        d.text(key, F["mono"], 13, PAD, y, SUBTLE)
        d.text(value, F["mono"], 13, PAD + 96, y, colour)
        d.add("</g>")
        y += LH
        t += 0.12
    y += 16
    t += 0.4
    d.add('<g class="k" style="animation-delay:%ss">' % f(t))
    prompt(d, PAD, y)
    d.add("</g>")
    t = typed("run how-i-work --loop", PAD + 2 * CH, y, t + 0.3, 0.06)
    y += LH + 16
    t += 0.3

    # The steps (TerminalSequence): they run in turn, 2.4s each, hold one beat all done, then start again.
    run, cycle = 2.4, len(steps) * 2.4 + 1.6
    go = t + 0.9
    x_name, x_ships, x_bar, x_status = PAD + 4 * CH, PAD + 15 * CH, 600, 748
    for i, (name, ships) in enumerate(steps):
        p1, p2 = f(i * run / cycle * 100, 3), f((i + 1) * run / cycle * 100, 3)
        first = i == 0
        d.css.append("@keyframes q%d{%s}" % (i, "0%,100%{opacity:0}" if first else "0%%{opacity:1}%s%%{opacity:0}100%%{opacity:0}" % p1))
        d.css.append("@keyframes r%d{%s%s%%{opacity:0}100%%{opacity:0}}" % (i, "0%{opacity:1}" if first else "0%%{opacity:0}%s%%{opacity:1}" % p1, p2))
        d.css.append("@keyframes d%d{0%%{opacity:0}%s%%{opacity:1}100%%{opacity:1}}" % (i, p2))
        d.css.append("@keyframes b%d{0%%{transform:scaleX(0)}%s%s%%{transform:scaleX(1)}100%%{transform:scaleX(1)}}" % (i, "" if first else "%s%%{transform:scaleX(0)}" % p1, p2))
        anim = lambda k, timing="step-end": "animation:%s%d %ss %s %ss infinite backwards" % (k, i, f(cycle), timing, f(go))
        still = "done" if i == 0 else "running" if i == 1 else "queued"  # the frame held when motion is off
        cy = y - 4.4
        d.add('<g class="k" style="animation-delay:%ss">' % f(t + i * 0.08))
        d.text("%02d" % (i + 1), F["mono"], 13, PAD, y, SUBTLE)
        d.text(name, F["mono"], 13, x_name, y, TEXT)
        w = d.text("ships ", F["mono"], 13, x_ships, y, SUBTLE)
        d.text(ships, F["mono"], 13, x_ships + w, y, VIOLET_500)
        d.add('<rect x="%d" y="%s" width="120" height="4" rx="2" fill="%s"/>' % (x_bar, f(cy - 2), BORDER))
        # queued
        d.add('<g style="opacity:%d;%s">' % (still == "queued", anim("q")))
        d.add('<circle cx="%s" cy="%s" r="3.3" fill="none" stroke="%s" stroke-width="1.2"/>' % (f(x_status + 3.9), f(cy), SUBTLE))
        d.text("queued", F["mono"], 13, x_status + 2 * CH, y, SUBTLE)
        d.add("</g>")
        # running
        d.add('<g style="opacity:%d;%s">' % (still == "running", anim("r")))
        d.add('<rect class="bar" x="%d" y="%s" width="120" height="4" rx="2" fill="%s" style="transform:scaleX(.6);%s"/>' % (x_bar, f(cy - 2), VIOLET_500, anim("b", "linear")))
        d.add('<circle cx="%s" cy="%s" r="3.3" fill="none" stroke="%s" stroke-width="1.2"/><path d="M%s %sa3.3 3.3 0 0 0 0 6.6z" fill="%s"/>' % (f(x_status + 3.9), f(cy), VIOLET_500, f(x_status + 3.9), f(cy - 3.3), VIOLET_500))
        d.text("running", F["mono"], 13, x_status + 2 * CH, y, VIOLET_500)
        d.add("</g>")
        # done
        d.add('<g style="opacity:%d;%s">' % (still == "done", anim("d")))
        d.add('<rect x="%d" y="%s" width="120" height="4" rx="2" fill="%s"/>' % (x_bar, f(cy - 2), SUCCESS))
        d.add('<path d="M%s %sl2.7 2.9 5-6.6" fill="none" stroke="%s" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>' % (f(x_status + 0.3), f(cy + 0.6), SUCCESS))
        d.text("done", F["mono"], 13, x_status + 2 * CH, y, SUCCESS)
        d.add("</g></g>")
        y += 29
    y += 16 - 8
    t += 0.5
    # The loop line, built from the steps.
    d.add('<g class="k" style="animation-delay:%ss">' % f(t))
    d.add('<rect x="%s" y="%s" width="%d" height="36" rx="8" fill="none" stroke="%s" stroke-dasharray="4 4"/>' % (f(PAD + 0.5), f(y - 14 + 0.5), W - 2 * PAD - 1, RULE_DASHED))
    w = d.text("↺ ", F["mono"], 12, PAD + 16, y + 8.5, SUCCESS)
    d.text(" → ".join(s for s, _ in steps), F["mono"], 12, PAD + 16 + w, y + 8.5, MUTED)
    d.add("</g>")
    y += 37 - 14 + 16 + 14.5
    d.add('<g class="k" style="animation-delay:%ss">' % f(t + 0.2))
    prompt(d, PAD, y)
    d.add('<rect class="caret" x="%s" y="%s" width="8" height="15.6" fill="%s"/>' % (f(PAD + 2 * CH), f(y - 12.2), VIOLET_500))
    d.add("</g>")
    d.save("terminal.svg")


def card_head(d, F, x, y, path, right):
    mark(d, x, y - 9.5)
    d.text(path, F["mono"], 12, x + 21, y, SUBTLE)
    d.text("↗", F["mono5"], 15, right, y + 1, LILAC_300, anchor="end")


def featured(F):
    W, H, P = 900, 276, 32
    d = Doc(W, H, "Company Brain: strategy, goals, projects and weekly work in one linked folder that AI agents read before they act, so every answer starts with company context. An Obsidian vault run by Claude through 32 skills, an MCP server and a CLI, with private, team and company layers. Opens the repository anna-hovhan/company-brain.")
    panel(d, 0, 0, W, H, 20, SURFACE, BORDER)
    card_head(d, F, P, 50, "anna-hovhan/company-brain", W - P)
    d.text("Company Brain", F["h2"], 30, P, 100, TEXT, -0.01)
    y = 136
    for line in wrap(F["sans"], 16, "Strategy, goals, projects and weekly work in one linked folder that AI agents read before they act, so every answer starts with company context.", 430):
        d.text(line, F["sans"], 16, P, y, MUTED)
        y += 25.6
    d.text("claude-code · obsidian · mcp-server · cli · 32 skills", F["mono"], 12, P, H - P - 2, VIOLET_500)
    # The three layers, each read by the agent.
    g = Graph(d, F, cycle=9, per=2.4)
    a, b = 536, 722
    layers = [g.node(a, 100, "company/"), g.node(a, 156, "team/"), g.node(a, 212, "private/")]
    agent = g.node(b, 156, "agent.read()")
    for i, n in enumerate(layers):
        g.pulse(i * 3, [g.side(n, agent, 688)], [n, agent])
    g.draw()
    d.save("card-company-brain.svg")


def small_cards(F):
    cards = [
        ("card-loopboard.svg", "anna-hovhan/loopboard", "loopboard", "A Claude Code plugin that gathers Slack and Jira conversations onto a Miro board, then exports board items back to Jira as issues.", "claude-code · slack · jira · miro", 0),
        ("card-shared-context-sync.svg", "anna-hovhan/shared-context-sync", "shared-context-sync", "A Claude plugin that keeps one Claude Project in sync with a shared Google Drive folder and your private local files, on a daily schedule.", "claude · google-drive · scheduled-task", 8),
    ]
    CW, P = 442, 28
    wrapped = [wrap(F["sans"], 16, c[3], CW - 2 * P) for c in cards]
    H = 116 + max(len(w) for w in wrapped) * 25.6 + 6 + 12 + P
    for (file, path, title, body, tags, left), lines in zip(cards, wrapped):
        # Each image is 450 wide and carries half of the 16px gutter, so two at 50% sit flush with the card above.
        d = Doc(CW + 8, H, "%s: %s Opens the repository %s." % (title, body, path))
        d.add('<g transform="translate(%d 0)">' % left)
        panel(d, 0, 0, CW, H, 16, SURFACE, BORDER)
        card_head(d, F, P, 46, path, CW - P)
        d.text(title, F["sans6"], 20, P, 86, TEXT, -0.01)
        for i, line in enumerate(lines):
            d.text(line, F["sans"], 16, P, 118 + i * 25.6, MUTED)
        d.text(tags, F["mono"], 12, P, H - P - 2, VIOLET_500)
        d.add("</g>")
        d.save(file)


def buttons(F):
    """Pills at the small control height (44px). Each image has the same margins, so they line up in a row."""
    M, TOP, H = 6, 6, 68
    for file, label, arrow, primary in [("btn-work.svg", "See my work", "→", True), ("btn-linkedin.svg", "linkedin.com/in/anna-hovhannisyan", "↗", False), ("btn-email.svg", "Email me", "→", False)]:
        font = F["sans6"] if primary else F["sans5"]
        tw, aw = font.width(label, 16), font.width(arrow, 16)
        w = round(18 + tw + 10 + aw + 18)
        d = Doc(w + 2 * M, H, label)
        if primary:
            d.defs.append('<filter id="s" x="-20%" y="-60%" width="140%" height="260%"><feGaussianBlur stdDeviation="7"/></filter>')
            d.add('<rect x="%d" y="%d" width="%d" height="26" rx="13" fill="%s" opacity=".7" filter="url(#s)"/>' % (M + 14, TOP + 24, w - 28, VIOLET_500))
            d.add('<rect x="%d" y="%d" width="%d" height="44" rx="22" fill="%s"/>' % (M, TOP, w, VIOLET_500))  # the accent, violet-500, solid
            d.add('<rect x="%s" y="%s" width="%d" height="43" rx="21.5" fill="none" stroke="#fff" stroke-opacity=".45"/>' % (f(M + 0.5), f(TOP + 0.5), w - 1))
        else:
            d.add('<rect x="%s" y="%s" width="%d" height="43" rx="21.5" fill="%s" stroke="%s"/>' % (f(M + 0.5), f(TOP + 0.5), w - 1, GHOST, BORDER_STRONG))
        ink = ON_ACCENT if primary else TEXT
        d.text(label, font, 16, M + 18, TOP + 27.5, ink)
        d.text(arrow, font, 16, M + 18 + tw + 10, TOP + 27.5, ink if primary else LILAC_300)
        d.save(file)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    F = fonts()
    hero(F)
    buttons(F)
    featured(F)
    small_cards(F)
    terminal(F)
