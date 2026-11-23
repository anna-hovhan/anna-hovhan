#!/usr/bin/env python3
"""Draws the profile README's images into assets/: the banner, the stack row and the link buttons.

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
GLOW = "#b794f6"


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
        "sans6": Font("Schibsted.ttf", wght=600),
        "mono5": Font("PlexMono-Medium.ttf"),
    }


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
    W, H = 900, 200
    d = Doc(W, H, "Anna Hovhannisyan. Enterprise agentic AI, from discovery to delivery. Strategy, data, and execution in one place. Beside the text, part of an agent graph: discovery.md, context/ and data.stack feed agent.plan() and skills/.")
    d.defs.append('<clipPath id="card"><rect width="%d" height="%d" rx="16"/></clipPath>' % (W, H))
    d.defs.append('<pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="12" cy="12" r="1" fill="%s" fill-opacity=".09"/></pattern>' % VIOLET_500)
    d.defs.append('<pattern id="dots2" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="12" cy="12" r="1.1" fill="%s" fill-opacity=".5"/></pattern>' % VIOLET_500)
    d.defs.append('<linearGradient id="band"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>')
    d.defs.append('<mask id="wave" maskUnits="userSpaceOnUse" x="0" y="0" width="%d" height="%d"><rect class="wave" x="-420" y="-200" width="340" height="800" fill="url(#band)" transform="skewX(-18)"/></mask>' % (W, H))
    # The ambient dot grid, with a slow wave of light passing through it.
    d.css.append("@keyframes wave{from{transform:translateX(0)}to{transform:translateX(1500px)}}.wave{animation:wave 16s linear infinite}")
    d.add('<g clip-path="url(#card)"><rect width="%d" height="%d" fill="%s"/><rect width="%d" height="%d" fill="url(#dots)"/><g mask="url(#wave)"><rect width="%d" height="%d" fill="url(#dots2)"/></g></g>' % (W, H, BG, W, H, W, H))
    d.add('<rect x=".5" y=".5" width="%d" height="%d" rx="15.5" fill="none" stroke="%s"/>' % (W - 1, H - 1, BORDER))

    # Copy: the wordmark, the eyebrow and the headline, with its one phrase in lilac.
    x = 40
    mark(d, x, 31, 12, 4, LILAC_100, "#fff")
    d.text("Anna Hovhannisyan", F["sans6"], 17, x + 24, 43, TEXT, -0.005)
    d.text("ENTERPRISE AGENTIC AI, FROM DISCOVERY TO DELIVERY", F["mono5"], 12, x, 80, LILAC_300, 0.1)
    d.text("Strategy, data, and", F["h1"], 44, x, 127, TEXT, -0.015)
    w = d.text("execution ", F["h1"], 44, x, 173, TEXT, -0.015)
    d.text("in one place.", F["h1"], 44, x + w, 173, LILAC_300, -0.015)

    # The inputs' side of the agent graph (design-system README, Diagrams).
    g = Graph(d, F, cycle=12, per=3)
    a, b, mid = 572, 732, 720
    n = [g.node(a, 44, "discovery.md"), g.node(a, 100, "context/"), g.node(a, 156, "data.stack"), g.node(b, 72, "agent.plan()"), g.node(b, 128, "skills/")]
    e = [g.side(0, 3, mid), g.side(1, 3, mid), g.side(1, 4, mid), g.side(2, 4, mid)]
    # One pulse per input, a third of a cycle apart.
    g.pulse(0, [e[0]], [n[0], n[3]])
    g.pulse(4, [e[2]], [n[1], n[4]])
    g.pulse(8, [e[3]], [n[2], n[4]])
    g.draw()
    d.save("hero.svg")


STACK = ["Python", "TypeScript", "Claude Code", "Obsidian", "MCP", "Anthropic", "OpenAI", "Google", "Cloudflare", "Supabase"]
LINKS = [("link-website.svg", "annahovhannisyan.com"), ("link-linkedin.svg", "linkedin.com/in/anna-hovhannisyan"), ("link-email.svg", "hello@annahovhannisyan.com")]


def stack(F):
    """The stack as one row of mono tags joined by dots, the way the site lists a post's topics."""
    W, H, x = 900, 92, 40
    d = Doc(W, H, "Stack: " + ", ".join(STACK) + ".")
    d.defs.append('<clipPath id="card"><rect width="%d" height="%d" rx="16"/></clipPath>' % (W, H))
    d.defs.append('<pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="12" cy="12" r="1" fill="%s" fill-opacity=".09"/></pattern>' % VIOLET_500)
    d.add('<g clip-path="url(#card)"><rect width="%d" height="%d" fill="%s"/><rect width="%d" height="%d" fill="url(#dots)"/></g>' % (W, H, BG, W, H))
    d.add('<rect x=".5" y=".5" width="%d" height="%d" rx="15.5" fill="none" stroke="%s"/>' % (W - 1, H - 1, BORDER))
    d.text("STACK", F["mono5"], 12, x, 37, SUBTLE, 0.1)
    size, cx = 13, x
    for i, item in enumerate(STACK):
        if i:
            cx += d.text(" \u00b7 ", F["mono5"], size, cx, 64, VIOLET_700)
        cx += d.text(item, F["mono5"], size, cx, 64, LILAC_400)
    assert cx <= W - x, "the stack row is %d wide and must end by %d" % (cx, W - x)
    d.save("stack.svg")


def links(F):
    """One CodeNode per link, each its own image so each can carry its own link in the README."""
    for name, label in LINKS:
        w = round(F["mono5"].width(label, 12) + 65)
        d = Doc(w, 34, label)
        d.add('<rect x=".5" y=".5" width="%d" height="33" rx="8" fill="%s" stroke="%s"/>' % (w - 1, RAISED, BORDER_NODE))
        d.add('<rect x="14" y="14" width="6" height="6" fill="%s"/>' % VIOLET_500)
        d.text(label, F["mono5"], 12, 28, 21.2, TEXT_NODE)
        # The site's "opens elsewhere" arrow, pointing up and to the right.
        d.add('<path d="M%d 21l8-8m-6 0h6v6" fill="none" stroke="%s" stroke-width="1.4"/>' % (w - 23, LILAC_300))
        d.save(name)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    F = fonts()
    hero(F)
    stack(F)
    links(F)
