"""Receipts: app-style news front page with bespoke data graphics.

Usage: python3 build.py [edition.json] [index.html]
Reads one edition, refuses to build if validate() finds a problem, writes one self-contained HTML page.
site.py imports this module to render every page of the website (load() + render())."""
import datetime
import hashlib
import html
import json
import math
import pathlib
import re
import sys
import zoneinfo

ROOT = pathlib.Path(__file__).parent
CT = zoneinfo.ZoneInfo("America/Chicago")
D, STORIES, BY_ID = {}, [], {}
PAGE = {}  # set by site.py for pages of the website; empty means one self-contained page


def load(data, page=None):
    """Point the renderer at one edition and, on the website, at that page's URLs."""
    global D, STORIES, BY_ID, PAGE
    D, STORIES = data, data["stories"]
    BY_ID = {s["id"]: s for s in STORIES}
    PAGE = page or {}
TOPICS = ["Agents", "Models", "Money", "Chips", "Jobs"]


def esc(s):
    return html.escape(str(s), quote=True)


def n(x):
    return f"{x:.2f}".rstrip("0").rstrip(".")


def surl(sid):
    """A story's address: its own page on the website, an in-page anchor otherwise."""
    return f'{PAGE["base"]}{sid}/' if PAGE.get("base") else f"#{sid}"


def slink(sid):
    return f'href="{esc(surl(sid))}" data-story="{esc(sid)}"'


# ---------- charts (inline SVG; colors come from CSS tokens) ----------

def svg(w, h, inner, label, cls=""):
    return (f'<svg class="chart {cls}" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(label)}" '
            f'preserveAspectRatio="xMidYMid meet">{inner}</svg>')


def hatch(uid):
    return (f'<defs><pattern id="h-{uid}" width="5" height="5" patternUnits="userSpaceOnUse" '
            f'patternTransform="rotate(45)"><rect class="hatch" width="2" height="5"/></pattern></defs>')


def vbar(x, y, w, h, r=4):
    r = min(r, w / 2, h)
    return (f"M{n(x)},{n(y + h)}V{n(y + r)}Q{n(x)},{n(y)} {n(x + r)},{n(y)}H{n(x + w - r)}"
            f"Q{n(x + w)},{n(y)} {n(x + w)},{n(y + r)}V{n(y + h)}Z")


def hbar(x, y, w, h, r=4):
    r = min(r, h / 2, w)
    return (f"M{n(x)},{n(y)}H{n(x + w - r)}Q{n(x + w)},{n(y)} {n(x + w)},{n(y + r)}"
            f"V{n(y + h - r)}Q{n(x + w)},{n(y + h)} {n(x + w - r)},{n(y + h)}H{n(x)}Z")


def mark_attrs(kind, uid):
    if kind == "guide":
        return f'fill="url(#h-{uid})" class="guide"'
    return f'class="{"m" if kind == "main" else "k"}"'


def c_vbars(c, uid):
    W, H, top, bot, side = 320, 190, 24, 24, 12
    ph = H - top - bot
    data = c["data"]
    band = (W - 2 * side) / len(data)
    bw = min(66, band * 0.6)
    vmax = max(v for _, v, _, _ in data)
    out = [hatch(uid), f'<line class="g" x1="{side}" x2="{W - side}" y1="{top + ph}" y2="{top + ph}"/>']
    for i, (lab, v, disp, kind) in enumerate(data):
        x = side + band * i + (band - bw) / 2
        h = max(2, ph * v / vmax)
        y = top + ph - h
        out.append(f'<path d="{vbar(x, y, bw, h)}" {mark_attrs(kind, uid)}><title>{esc(lab)}: {esc(disp)}</title></path>')
        out.append(f'<text class="tv" x="{n(x + bw / 2)}" y="{n(y - 7)}" text-anchor="middle">{esc(disp)}</text>')
        out.append(f'<text class="t" x="{n(x + bw / 2)}" y="{H - 7}" text-anchor="middle">{esc(lab)}</text>')
    return W, H, "".join(out)


def c_hbars(c, uid):
    data = c["data"]
    W, row = 320, 40
    H = len(data) * row + 4
    vmax = c.get("max") or max(v for _, v, _, _ in data)
    span = W - 78
    out = [hatch(uid)]
    for i, (lab, v, disp, kind) in enumerate(data):
        y0 = i * row
        w = max(3, span * v / vmax)
        out.append(f'<text class="t" x="0" y="{y0 + 13}">{esc(lab)}</text>')
        out.append(f'<path d="{hbar(0, y0 + 19, w, 13)}" {mark_attrs(kind, uid)}><title>{esc(lab)}: {esc(disp)}</title></path>')
        out.append(f'<text class="tv" x="{n(w + 8)}" y="{y0 + 30}">{esc(disp)}</text>')
    return W, H, "".join(out)


def days(d):
    return datetime.date.fromisoformat(d).toordinal()


def c_slope(c, uid):
    W, H, top, bot, left, right = 320, 200, 34, 24, 40, 64
    x0, x1 = days("2026-03-01"), days("2026-11-30")
    y0, y1 = 800, 1300
    pw, ph = W - left - right, H - top - bot
    X = lambda d: left + pw * (days(d) - x0) / (x1 - x0)
    Y = lambda v: top + ph * (1 - (v - y0) / (y1 - y0))
    out = []
    for v, lab in [(900, "$0.9T"), (1000, "$1.0T"), (1100, "$1.1T"), (1200, "$1.2T"), (1300, "$1.3T")]:
        out.append(f'<line class="g" x1="{left}" x2="{W - right + 8}" y1="{n(Y(v))}" y2="{n(Y(v))}"/>')
        out.append(f'<text class="t" x="{left - 6}" y="{n(Y(v) + 4)}" text-anchor="end">{lab}</text>')
    for m, lab in [("2026-03-01", "Mar"), ("2026-05-01", "May"), ("2026-07-01", "Jul"), ("2026-09-01", "Sep"), ("2026-11-01", "Nov")]:
        out.append(f'<text class="t" x="{n(X(m))}" y="{H - 6}" text-anchor="middle">{lab}</text>')
    lx = left
    for s in c["series"]:
        (da, va, la), (db, vb, lb) = s["pts"]
        out.append(f'<line class="ln {s["cls"]}" x1="{n(X(da))}" y1="{n(Y(va))}" x2="{n(X(db))}" y2="{n(Y(vb))}"/>')
        for d, v, l in s["pts"]:
            out.append(f'<circle class="pt {s["cls"]}" cx="{n(X(d))}" cy="{n(Y(v))}" r="4.5"><title>{esc(s["name"])}: {esc(l)}</title></circle>')
        dy = 17 if s["cls"] == "s1" else -10
        out.append(f'<text class="tv" x="{n(X(da))}" y="{n(Y(va) + dy)}" text-anchor="middle">{esc(la)}</text>')
        out.append(f'<text class="tv" x="{n(X(db) + 9)}" y="{n(Y(vb) + 4)}">{esc(lb)}</text>')
        out.append(f'<line class="ln {s["cls"]}" x1="{lx}" x2="{lx + 14}" y1="12" y2="12"/>'
                   f'<text class="t" x="{lx + 19}" y="16">{esc(s["name"])}</text>')
        lx += 92
    return W, H, "".join(out)


def c_scale(c, uid):
    W, H, S = 320, 190, 152
    (bv, bl, bd), (sv, sl, sd) = c["big"], c["small"]
    s = S * math.sqrt(sv / bv)
    bx, by = 6, 22
    sx, sy = bx + S + 46, by + S - s
    cx, cy = sx + s / 2, sy + s / 2
    out = [f'<rect class="k" x="{bx}" y="{by}" width="{S}" height="{S}" rx="3"><title>{esc(bl)}: {esc(bd)}</title></rect>',
           f'<text class="tv" x="{bx + 12}" y="{by + 26}">{esc(bd)}</text>',
           f'<text class="t" x="{bx + 12}" y="{by + 42}">{esc(bl)}</text>',
           f'<rect class="m" x="{n(sx)}" y="{n(sy)}" width="{n(max(s, 0.8))}" height="{n(max(s, 0.8))}"><title>{esc(sl)}: {esc(sd)}</title></rect>',
           f'<circle class="ring" cx="{n(cx)}" cy="{n(cy)}" r="9"/>',
           f'<line class="lead-line" x1="{n(cx)}" y1="{n(cy - 9)}" x2="{n(cx)}" y2="{n(cy - 34)}"/>',
           f'<text class="tbig" x="{n(sx - 4)}" y="{n(cy - 92)}">{esc(sd)}</text>']
    for i, line in enumerate(["All on-chain agent", "payments, Q3.", "Drawn to scale."]):
        out.append(f'<text class="t" x="{n(sx - 4)}" y="{n(cy - 72 + i * 14)}">{line}</text>')
    return W, H, "".join(out)


def c_units(c, uid):
    W, H = 320, 160
    out = []
    for i in range(100):
        r, col = divmod(i, 10)
        cls = "m" if i < c["k"] else "k"
        out.append(f'<circle class="{cls}" cx="{12 + col * 14}" cy="{12 + r * 14}" r="5"/>')
    out.append(f'<text class="tbig" x="172" y="54">{esc(c["big"])}</text>')
    words, lines, cur = c["label"].split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > 22:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    lines.append(cur)
    for i, l in enumerate(lines):
        out.append(f'<text class="t" x="172" y="{76 + i * 15}">{esc(l)}</text>')
    return W, H, "".join(out)


def c_share(c, uid):
    W, H, y, h = 320, 92, 44, 22
    a = W * c["pct"] / 100
    out = [f'<path class="m" d="M{n(a)},{y}H4Q0,{y} 0,{y + 4}V{y + h - 4}Q0,{y + h} 4,{y + h}H{n(a)}Z"><title>{esc(c["a"])}: {c["pct"]}%</title></path>',
           f'<path class="k" d="M{n(a + 2)},{y}H{W - 4}Q{W},{y} {W},{y + 4}V{y + h - 4}Q{W},{y + h} {W - 4},{y + h}H{n(a + 2)}Z"><title>{esc(c["b"])}: {100 - c["pct"]}%</title></path>',
           f'<text class="tv" x="0" y="16">{c["pct"]}%</text><text class="t" x="0" y="32">{esc(c["a"])}</text>',
           f'<text class="tv" x="{W}" y="16" text-anchor="end">{100 - c["pct"]}%</text><text class="t" x="{W}" y="32" text-anchor="end">{esc(c["b"])}</text>']
    return W, H, "".join(out)


def c_steps(c, uid):
    W, H, top, bot, left, right = 320, 190, 26, 24, 40, 18
    x0, x1 = days("2024-08-01"), days("2026-12-15")
    pw, ph = W - left - right, H - top - bot
    X = lambda d: left + pw * (days(d) - x0) / (x1 - x0)
    Y = lambda v: top + ph * (1 - v / 22)
    out = []
    for v, lab in [(0, "$0"), (10, "$10B"), (20, "$20B")]:
        out.append(f'<line class="g" x1="{left}" x2="{W - right}" y1="{n(Y(v))}" y2="{n(Y(v))}"/>')
        out.append(f'<text class="t" x="{left - 6}" y="{n(Y(v) + 4)}" text-anchor="end">{lab}</text>')
    for d, lab in [("2025-01-01", "2025"), ("2026-01-01", "2026")]:
        out.append(f'<text class="t" x="{n(X(d))}" y="{H - 6}" text-anchor="middle">{lab}</text>')
    pts = c["pts"]
    path = f"M{n(X(pts[0][0]))},{n(Y(pts[0][1]))}"
    for (d, v, _), (d2, v2, _) in zip(pts, pts[1:]):
        path += f"H{n(X(d2))}V{n(Y(v2))}"
    out.append(f'<path class="ln s1" d="{path}"/>')
    for d, v, l in pts:
        out.append(f'<circle class="pt s1" cx="{n(X(d))}" cy="{n(Y(v))}" r="4.5"><title>{esc(l)}</title></circle>')
        out.append(f'<text class="tv" x="{n(X(d) - 7)}" y="{n(Y(v) - 9)}" text-anchor="end">{esc(l)}</text>')
    return W, H, "".join(out)


def c_diagram(c, uid):
    """Where something runs: up to three boxes inside a zone, an arrow, and the thing they call.
    Optional keys: zone, nodes (1-3 labels), target, target_sub. Defaults draw the agent-infrastructure diagram."""
    zone = c.get("zone", "Your cloud or data center")
    nodes = c.get("nodes", ["Agent loop", "Sandboxes", "Session history"])
    target, sub = c.get("target", "Model"), c.get("target_sub", "of your choice")
    W, H = 320, 58 + len(nodes) * 44
    out = [f'<rect class="zone" x="4" y="8" width="190" height="{44 + len(nodes) * 44}" rx="14"/>',
           f'<text class="t" x="18" y="30">{esc(zone)}</text>']
    for i, lab in enumerate(nodes):
        y = 44 + i * 44
        out.append(f'<rect class="node" x="18" y="{y}" width="162" height="32" rx="9"/>'
                   f'<text class="tv" x="99" y="{y + 21}" text-anchor="middle">{esc(lab)}</text>')
    mid = 44 + (len(nodes) * 44 - 12) / 2
    out.append(f'<line class="arrow" x1="196" y1="{n(mid)}" x2="226" y2="{n(mid)}"/>'
               f'<path class="arrowhead" d="M226,{n(mid - 6)} L234,{n(mid)} L226,{n(mid + 6)}Z"/>')
    ty = mid - 28
    if sub:
        out.append(f'<rect class="node strong" x="238" y="{n(ty)}" width="80" height="56" rx="10"/>'
                   f'<text class="tv" x="278" y="{n(ty + 24)}" text-anchor="middle">{esc(target)}</text>'
                   f'<text class="t" x="278" y="{n(ty + 40)}" text-anchor="middle">{esc(sub)}</text>')
    else:
        out.append(f'<rect class="node strong" x="238" y="{n(ty)}" width="80" height="56" rx="10"/>'
                   f'<text class="tv" x="278" y="{n(ty + 33)}" text-anchor="middle">{esc(target)}</text>')
    return W, H, "".join(out)


CHARTS = {"vbars": c_vbars, "hbars": c_hbars, "slope": c_slope, "scale": c_scale,
          "units": c_units, "share": c_share, "steps": c_steps, "diagram": c_diagram}


def chart(s, uid, cls=""):
    c = s["chart"]
    W, H, inner = CHARTS[c["type"]](c, uid)
    if cls == "mini" and c["type"] == "units":
        W, H = 146, 146
    label = c.get("title") or s["dek"]
    return svg(W, H, inner, label, cls)


# ---------- markup ----------

AV_COLORS = ["#3B4CCA", "#0E7C66", "#7A4CE0", "#B3471B", "#0369A1", "#A8235A", "#4D7C0F", "#5B6170"]


def avatar(name):
    h = int(hashlib.md5(name.encode()).hexdigest(), 16)
    return f'<span class="av" style="background:{AV_COLORS[h % len(AV_COLORS)]}" aria-hidden="true">{esc(name[0].upper())}</span>'


def sups(s, nums):
    if not nums:
        return ""
    links = ",".join(f'<a href="{esc(s["sources"][k - 1]["url"])}" rel="noopener" aria-label="Source {k}: {esc(s["sources"][k - 1]["name"])}">{k}</a>' for k in nums)
    return f'<sup class="fn">{links}</sup>'


def kicker(s):
    return (f'<div class="kick"><span class="topic">{esc(s["topic"])}</span><span>{esc(s["date"])}</span>'
            f'<span class="ev ev--{s["tier"]}">{esc(s["evidence"])}</span></div>')


def card(i, s):
    attrs = f'{slink(s["id"])} data-id="{esc(s["id"])}" data-topic="{s["topic"].lower()}"'
    k = kicker(s)
    nsrc = f'{len(s["sources"])} sources'
    if i == 0:
        return (f'<a class="card card--lead" {attrs}>{k}<h2 class="hl">{esc(s["headline"])}</h2>'
                f'<p class="dek">{esc(s["dek"])}</p><div class="cover">{chart(s, s["id"] + "-c")}</div>'
                f'<div class="foot"><span>{nsrc}</span><span class="open-cta">Read the story</span></div></a>')
    if i in (1, 2):
        return (f'<a class="card card--feature" {attrs}><div class="cover">{chart(s, s["id"] + "-c")}</div>'
                f'{k}<h2 class="hl">{esc(s["headline"])}</h2><p class="dek">{esc(s["dek"])}</p></a>')
    return (f'<a class="card card--row" {attrs}><div class="txt">{k}<h2 class="hl">{esc(s["headline"])}</h2>'
            f'<p class="dek">{esc(s["dek"])}</p></div><div class="thumb">{chart(s, s["id"] + "-t", "mini")}</div></a>')


def sheet_tpl(i, s):
    nxt = STORIES[(i + 1) % len(STORIES)]
    c = s["chart"]
    cap = f'<p class="s-cap">{esc(c["title"])}</p>' if c.get("title") else ""
    note = f'<p class="s-note">{esc(c["note"])}</p>' if c.get("note") else ""
    facts = "".join(
        f'<div class="fact"><span class="st">{esc(f["stat"])}</span><span class="tx">{esc(f["text"])}{sups(s, f["s"])}</span></div>'
        for f in s["facts"])
    op = s.get("open")
    open_html = (f'<div class="open open--{s["tier"]}"><b>{esc(op["label"])}</b><span>{esc(op["text"])}{sups(s, op["s"])}</span></div>'
                 if op else "")
    srcs = "".join(
        f'<a class="src" href="{esc(x["url"])}" rel="noopener">{avatar(x["name"])}'
        f'<span class="src-t"><span class="nm"><span class="no">{k}</span>{esc(x["name"])}<span class="kind">{esc(x["kind"])}</span></span>'
        f'<span class="ds">{esc(x["desc"])}</span></span>'
        f'<svg class="ext" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3h7v7M13 3 4 12"/></svg></a>'
        for k, x in enumerate(s["sources"], 1))
    cor = s.get("correction")
    corr = (f'<p class="corr"><b>Correction, {esc(cor["date"])}.</b> {esc(cor["text"])}</p>' if cor else "")
    disc = ('<p class="disc">Disclosure: Receipts is written with Claude, an AI model made by Anthropic. '
            'Anthropic is covered like any other company.</p>') if s.get("disclosure") else ""
    return (f'<template id="tpl-{esc(s["id"])}"><article class="s">{kicker(s)}'
            f'<h2 class="s-hl" id="s-hl">{esc(s["headline"])}</h2><p class="s-dek">{esc(s["dek"])}</p>'
            f'<figure class="s-fig">{cap}{chart(s, s["id"] + "-s")}{note}</figure>'
            f'<div class="facts">{facts}</div>{open_html}{corr}'
            f'<section class="srcs"><h3>Sources</h3>{srcs}</section>{disc}'
            f'<div class="s-actions"><button class="pill copy" type="button" data-id="{esc(s["id"])}">Copy link</button></div>'
            f'<a class="s-next" {slink(nxt["id"])}><span class="lbl">Next story</span><span class="nh">{esc(nxt["headline"])}</span></a>'
            f'</article></template>')


LOGO = ('<svg class="logo" viewBox="0 0 28 28" aria-hidden="true"><rect width="28" height="28" rx="8" class="logo-bg"/>'
        '<path d="M8 9.5h12M8 14h12M8 18.5h7" class="logo-ln"/></svg>')
PLAY = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3.5v9l7.5-4.5z"/></svg>'
X = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8"/></svg>'
CHEV_L = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3 5 8l5 5"/></svg>'
CHEV_R = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="m6 3 5 5-5 5"/></svg>'


def get_block():
    """How to get the next edition. Shown only once a channel exists:
    subscribe_url (a newsletter signup page) wins; otherwise inbox (the agent's email address); x_url adds a follow link."""
    links, sub = [], "A new edition every morning. Free, no ads."
    if D.get("subscribe_url"):
        links.append(f'<a class="go" href="{esc(D["subscribe_url"])}" rel="noopener">Get it by email</a>')
    elif D.get("inbox"):
        a = esc(D["inbox"])
        links.append(f'<a class="go" href="mailto:{a}?subject=Subscribe">Subscribe by email</a>')
        sub = (f'Email <span class="addr">{a}</span> with the word subscribe. '
               'Reply stop anytime. Free, no ads.')
    if D.get("x_url"):
        links.append(f'<a class="alt" href="{esc(D["x_url"])}" rel="noopener">Follow on X</a>')
    if not links:
        return ""
    return ('<section class="get" aria-label="Get Receipts daily"><p class="get-t">Get tomorrow\'s edition</p>'
            f'<p class="get-s">{sub}</p><div class="get-a">{"".join(links)}</div></section>')


def tips_line():
    if not D.get("inbox"):
        return ""
    a = esc(D["inbox"])
    return (f'<p>Spot an error or have a tip? Email <a class="addr" href="mailto:{a}?subject=Correction">{a}</a>. '
            'The agent checks every report against the sources before the next edition.</p>')


def validate():
    """Refuse to build an edition that breaks the format or the sourcing rules."""
    errs = []
    ids = [s.get("id") for s in STORIES]
    if not 6 <= len(STORIES) <= 14:
        errs.append(f"need 6-14 stories, found {len(STORIES)}")
    if len(set(ids)) != len(ids):
        errs.append("duplicate story ids")
    for s in STORIES:
        sid = s.get("id", "?")
        for k in ("id", "topic", "date", "tier", "evidence", "headline", "dek", "facts", "chart", "sources"):
            if k not in s:
                errs.append(f"{sid}: missing '{k}'")
        if s.get("topic") not in TOPICS:
            errs.append(f"{sid}: topic must be one of {TOPICS}")
        if s.get("tier") not in ("ok", "warn", "bad"):
            errs.append(f"{sid}: tier must be ok, warn or bad")
        if len(s.get("headline", "")) > 95:
            errs.append(f"{sid}: headline over 95 characters")
        if len(s.get("dek", "")) > 140:
            errs.append(f"{sid}: dek over 140 characters")
        srcs = s.get("sources", [])
        if not srcs:
            errs.append(f"{sid}: no sources")
        for x in srcs:
            if not str(x.get("url", "")).startswith("http"):
                errs.append(f"{sid}: source without a URL")
            if x.get("kind") not in ("Filing", "Company", "Press", "Data"):
                errs.append(f"{sid}: source kind must be Filing, Company, Press or Data")
            if not x.get("name") or not x.get("desc"):
                errs.append(f"{sid}: source missing name or desc")
        facts = s.get("facts", [])
        if not 1 <= len(facts) <= 5:
            errs.append(f"{sid}: need 1-5 facts")
        for f in facts:
            if not f.get("stat") or not f.get("text") or not f.get("s"):
                errs.append(f"{sid}: every fact needs stat, text and at least one source number")
        for f in facts + ([s["open"]] if s.get("open") else []):
            if not all(isinstance(k, int) and 1 <= k <= len(srcs) for k in f.get("s", [])):
                errs.append(f"{sid}: source number out of range")
        texts = [s.get("headline", ""), s.get("dek", "")] + [f.get("text", "") for f in facts]
        if s.get("open"):
            texts.append(s["open"].get("text", ""))
        if s.get("correction"):
            if not s["correction"].get("date") or not s["correction"].get("text"):
                errs.append(f"{sid}: correction needs date and text")
            texts.append(s["correction"].get("text", ""))
        if any("\u2014" in t for t in texts):
            errs.append(f"{sid}: no em dashes in copy")
        c = s.get("chart", {})
        if c.get("type") == "diagram":
            nd = c.get("nodes", ["x"])
            if not 1 <= len(nd) <= 3 or any(len(x) > 18 for x in nd):
                errs.append(f"{sid}: diagram needs 1-3 nodes of at most 18 characters")
            if len(c.get("zone", "")) > 26 or len(c.get("target", "")) > 9 or len(c.get("target_sub", "")) > 15:
                errs.append(f"{sid}: diagram zone max 26, target max 9, target_sub max 15 characters")
        if c.get("type") not in CHARTS:
            errs.append(f"{sid}: chart type must be one of {sorted(CHARTS)}")
        else:
            try:
                chart(s, "validate")
            except Exception as ex:
                errs.append(f"{sid}: chart failed to render ({ex!r})")
    if D.get("inbox") and not re.fullmatch(r"[^@\s<>\"']+@[^@\s<>\"']+\.[A-Za-z]{2,}", str(D["inbox"])):
        errs.append("inbox must be a plain email address")
    for k in ("subscribe_url", "x_url"):
        if D.get(k) and not str(D[k]).startswith("https://"):
            errs.append(f"{k} must be an https:// URL")
    if not 3 <= len(D.get("brief", [])) <= 6:
        errs.append("brief needs 3-6 slides")
    for b in D.get("brief", []):
        if b.get("id") not in BY_ID or not b.get("big") or not b.get("line"):
            errs.append(f"brief slide invalid: {b}")
    for c in D.get("coming", []):
        if len(c) != 4 or c[3] not in BY_ID:
            errs.append(f"coming-up item invalid: {c}")
    if errs:
        print("EDITION INVALID:\n- " + "\n- ".join(errs))
        raise SystemExit(1)


def stamp():
    pub = D.get("published_at")
    return datetime.datetime.fromisoformat(pub).astimezone(CT) if pub else datetime.datetime.now(CT)


def head():
    if not PAGE:
        return ('<title>Receipts AI News</title>\n<meta name="description" content="AI frontier and agent-economy news. '
                'Every number linked to its source. No ads.">')
    p, sp = PAGE, PAGE["site_path"]
    tags = [f'<title>{esc(p["title"])}</title>',
            f'<meta name="description" content="{esc(p["description"])}">',
            f'<link rel="canonical" href="{esc(p["canonical"])}">',
            '<meta property="og:site_name" content="Receipts">',
            f'<meta property="og:type" content="{esc(p["og_type"])}">',
            f'<meta property="og:title" content="{esc(p["og_title"])}">',
            f'<meta property="og:description" content="{esc(p["description"])}">',
            f'<meta property="og:url" content="{esc(p["canonical"])}">',
            f'<meta property="og:image" content="{esc(p["og_image"])}">',
            '<meta property="og:image:width" content="1200">',
            '<meta property="og:image:height" content="630">',
            f'<meta property="og:image:alt" content="{esc(p["og_alt"])}">',
            '<meta name="twitter:card" content="summary_large_image">',
            f'<meta name="twitter:title" content="{esc(p["og_title"])}">',
            f'<meta name="twitter:description" content="{esc(p["description"])}">',
            f'<meta name="twitter:image" content="{esc(p["og_image"])}">',
            '<meta name="theme-color" media="(prefers-color-scheme: light)" content="#FFFFFF">',
            '<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#0B0C0E">',
            f'<link rel="icon" href="{sp}favicon.svg" type="image/svg+xml">',
            f'<link rel="icon" href="{sp}icon-32.png" sizes="32x32" type="image/png">',
            f'<link rel="apple-touch-icon" href="{sp}apple-touch-icon.png">',
            f'<link rel="manifest" href="{sp}site.webmanifest">',
            f'<link rel="alternate" type="application/rss+xml" title="Receipts" href="{sp}feed.xml">',
            f'<link rel="alternate" type="application/feed+json" title="Receipts" href="{sp}feed.json">']
    if p.get("published"):
        tags.append(f'<meta property="article:published_time" content="{esc(p["published"])}">')
    return "\n".join(tags)


def render():
    """The page for the loaded edition, as one HTML string."""
    now = stamp()
    day = now.strftime("%A")
    date = f"{now.strftime('%B')} {now.day}"
    upd = f"Updated {now.strftime('%I').lstrip('0')}:{now.strftime('%M')} {'AM' if now.hour < 12 else 'PM'} CT"

    tabs = '<button class="tab" role="tab" aria-selected="true" data-topic="all">Top</button>' + "".join(
        f'<button class="tab" role="tab" aria-selected="false" data-topic="{t.lower()}">{t}</button>' for t in TOPICS)
    cards = "".join(card(i, s) for i, s in enumerate(STORIES))
    tpls = "".join(sheet_tpl(i, s) for i, s in enumerate(STORIES))
    coming = "".join(
        f'<a class="day" {slink(sid)}><span class="d1">{esc(a)}</span><span class="d2">{esc(b)}</span><span class="d3">{esc(what)}</span></a>'
        for a, b, what, sid in D["coming"])
    coming_sec = ('<section class="coming" aria-labelledby="coming-h"><h2 class="sec-h" id="coming-h">Coming up</h2>'
                  f'<div class="days">{coming}</div></section>') if coming else ""
    bars = "".join('<span class="b-bar"><i></i></span>' for _ in D["brief"])
    slides = "".join(
        f'<div class="b-slide" data-i="{i}"><p class="b-kick">{esc(b["kick"])}</p><p class="b-big">{esc(b["big"])}</p>'
        f'<p class="b-line">{esc(b["line"])}</p><a class="b-cta" {slink(b["id"])}>Read the story</a></div>'
        for i, b in enumerate(D["brief"]))
    order = json.dumps([s["id"] for s in STORIES])
    attr = (f' data-base="{esc(PAGE["base"])}" data-permalink="{esc(PAGE["permalink"])}"' if PAGE else "")
    arch = (f'<p class="arch-note">This is the edition from {esc(date)}. <a href="{esc(PAGE["home"])}">Read today\'s</a></p>'
            if PAGE.get("archived") else "")
    links = (f'<nav class="foot-links" aria-label="More from Receipts"><a href="{esc(PAGE["about"])}">How it works</a>'
             f'<a href="{esc(PAGE["archive"])}">Past editions</a><a href="{esc(PAGE["feed"])}">RSS</a>'
             f'<a href="{esc(PAGE["json"])}">Data for agents</a></nav>') if PAGE else ""

    page = (TEMPLATE.replace("__HEAD__", head()).replace("__HTMLATTR__", attr).replace("__HOME__", esc(PAGE.get("home", "#")))
            .replace("__ARCH__", arch).replace("__LINKS__", links)
            .replace("__CSS__", CSS).replace("__JS__", JS.replace("__ORDER__", order))
            .replace("__LOGO__", LOGO).replace("__PLAY__", PLAY).replace("__X__", X)
            .replace("__CHEVL__", CHEV_L).replace("__CHEVR__", CHEV_R)
            .replace("__DAY__", esc(day)).replace("__DATE__", esc(date)).replace("__UPD__", esc(upd))
            .replace("__TABS__", tabs).replace("__CARDS__", cards).replace("__TPLS__", tpls)
            .replace("__COMING__", coming_sec).replace("__BARS__", bars).replace("__SLIDES__", slides)
            .replace("__N__", str(len(STORIES))).replace("__GET__", get_block()).replace("__TIPS__", tips_line()))
    return page, f"{day}, {date}. {upd}"


def main():
    src = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "edition.json"
    out = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "index.html"
    data = json.loads(src.read_text())
    pub = data.get("published_at")
    if pub and datetime.datetime.now(CT) - datetime.datetime.fromisoformat(pub) > datetime.timedelta(hours=20):
        data.pop("published_at")  # a stale stamp copied from yesterday; this page is being published now
    load(data)
    validate()
    page, when = render()
    out.write_text(page)
    print(f"Wrote {out.name}: {len(STORIES)} stories, {len(page):,} bytes. {when}")


CSS = r"""
:root {
  /* Layout: app shell. Large date title, sticky topic tabs, then a feed ranked by weight:
     a brand-blue lead card, two chart-led feature cards, then compact rows with chart thumbnails.
     Every story opens in a sheet: facts with footnoted sources, the full chart, the source list. */
  --brand: #002FA7;
  --bg: #FFFFFF;
  --surface: #F3F4F6;
  --raised: #FFFFFF;
  --ink: #0E1014;
  --ink-2: #5F6672;
  --ink-3: #9AA0A9;
  --line: #E7E9ED;
  --grid: #E1E4E9;
  --accent: #2E5BEA;
  --accent-2: #D45F1E;
  --ctx: #C4CAD4;
  --ok: #0B7A43;
  --warn: #A35A00;
  --bad: #C2261F;
  --card: var(--surface);
  --font: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI Variable Text", "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --display: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI Variable Display", "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --ease: cubic-bezier(.32, .72, 0, 1);
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #09090B; --surface: #15171B; --raised: #1D2025; --ink: #F3F4F6; --ink-2: #A3A9B4; --ink-3: #6C727C;
    --line: #24272D; --grid: #2A2E35; --accent: #5E7FF5; --accent-2: #E8692A; --ctx: #3A404B;
    --ok: #4CC98A; --warn: #F0AE4C; --bad: #FF7A70; color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #09090B; --surface: #15171B; --raised: #1D2025; --ink: #F3F4F6; --ink-2: #A3A9B4; --ink-3: #6C727C;
  --line: #24272D; --grid: #2A2E35; --accent: #5E7FF5; --accent-2: #E8692A; --ctx: #3A404B;
  --ok: #4CC98A; --warn: #F0AE4C; --bad: #FF7A70; color-scheme: dark;
}
*, *::before, *::after { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; background: var(--bg); }
html.lock { overflow: hidden; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 400 16px/1.45 var(--font); -webkit-font-smoothing: antialiased; }
a { color: inherit; }
button { font: inherit; color: inherit; }
[hidden] { display: none !important; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; border-radius: 6px; }
svg { display: block; }

.app { max-width: 1120px; margin: 0 auto; padding: 0 16px calc(56px + env(safe-area-inset-bottom)); }
.bar { display: flex; align-items: center; justify-content: space-between; height: 58px; }
.wm { display: inline-flex; align-items: center; gap: 9px; text-decoration: none; font: 700 18px/1 var(--display); letter-spacing: -0.02em; }
.logo { width: 28px; height: 28px; }
.logo-bg { fill: var(--brand); }
.logo-ln { stroke: #fff; stroke-width: 2.4; stroke-linecap: round; fill: none; }
.btn-brief { display: inline-flex; align-items: center; gap: 7px; height: 36px; padding: 0 15px 0 12px; border-radius: 999px; background: var(--ink); color: var(--bg); text-decoration: none; font: 600 14px/1 var(--font); }
.btn-brief svg { width: 14px; height: 14px; fill: currentColor; }

.hero { padding: 10px 2px 16px; }
.hero .dayname { margin: 0; font: 600 13px/1 var(--font); color: var(--ink-2); }
.hero h1 { margin: 6px 0 0; font: 800 36px/1.02 var(--display); letter-spacing: -0.035em; }
.live { display: inline-flex; align-items: center; gap: 8px; margin: 10px 0 0; font: 500 13px/1 var(--font); color: var(--ink-2); }
.live i { width: 7px; height: 7px; border-radius: 50%; background: var(--ok); }

.tabs-wrap { position: sticky; top: 0; z-index: 20; margin: 0 -16px; padding: 8px 16px 10px; background: var(--bg); }
@supports (backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px)) {
  .tabs-wrap { background: color-mix(in srgb, var(--bg) 78%, transparent); -webkit-backdrop-filter: saturate(180%) blur(20px); backdrop-filter: saturate(180%) blur(20px); }
}
.tabs { position: relative; display: flex; gap: 2px; padding: 3px; border-radius: 13px; background: var(--surface); overflow-x: auto; scrollbar-width: none; }
.tabs::-webkit-scrollbar { display: none; }
.tab { position: relative; z-index: 1; flex: 1 0 auto; border: 0; background: transparent; color: var(--ink-2); font: 600 14px/1 var(--font); padding: 9px 14px; border-radius: 10px; cursor: pointer; transition: color .2s; }
.tab[aria-selected="true"] { color: var(--ink); }
.ind { position: absolute; z-index: 0; top: 3px; bottom: 3px; left: 0; width: 0; border-radius: 10px; background: var(--raised); box-shadow: 0 1px 2px rgb(0 0 0 / .06), 0 3px 10px rgb(0 0 0 / .06); }

.feed { display: grid; grid-template-columns: minmax(0, 1fr); gap: 12px; margin-top: 6px; }
.card { display: block; color: inherit; text-decoration: none; -webkit-tap-highlight-color: transparent; }
.kick { display: flex; align-items: center; flex-wrap: wrap; gap: 4px 10px; font: 600 12.5px/1.2 var(--font); color: var(--ink-2); }
.kick .topic { color: var(--ink); }
.ev { --c: var(--ink-2); display: inline-flex; align-items: center; gap: 5px; color: var(--c); }
.ev::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--c); }
.ev--ok { --c: var(--ok); } .ev--warn { --c: var(--warn); } .ev--bad { --c: var(--bad); }
.hl { margin: 8px 0 0; font: 650 18.5px/1.24 var(--display); letter-spacing: -0.017em; text-wrap: balance; }
.dek { margin: 6px 0 0; font: 400 14.5px/1.42 var(--font); color: var(--ink-2); }

.card--lead {
  --accent: #FFFFFF; --accent-2: #FFFFFF; --ctx: rgb(255 255 255 / .3); --grid: rgb(255 255 255 / .2);
  --ink: #FFFFFF; --ink-2: rgb(255 255 255 / .76); --card: var(--brand);
  display: flex; flex-direction: column; padding: 20px 20px 16px; border-radius: 24px; background: var(--brand); color: #fff;
}
.card--lead .ev { --c: #fff; }
.card--lead .hl { margin-top: 12px; font-size: 28px; line-height: 1.08; font-weight: 750; letter-spacing: -0.03em; }
.card--lead .dek { font-size: 15.5px; }
.card--lead .cover { margin-top: 14px; }
.card--lead .cover .chart { width: 100%; height: auto; max-height: 240px; }
.foot { display: flex; justify-content: space-between; align-items: center; margin-top: 14px; padding-top: 12px; border-top: 1px solid rgb(255 255 255 / .2); font: 600 13px/1 var(--font); color: rgb(255 255 255 / .8); }
.open-cta { color: #fff; }

.card--feature { padding: 14px 14px 18px; border-radius: 22px; background: var(--surface); }
.card--feature .cover { padding: 10px 6px 4px; margin-bottom: 14px; }
.card--feature .cover .chart { width: 100%; height: auto; max-height: 200px; }
.card--feature .hl { font-size: 20px; }

.card--row { display: grid; grid-template-columns: minmax(0, 1fr) 86px; gap: 14px; align-items: start; padding: 16px 2px; border-top: 1px solid var(--line); }
.card--row .dek { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.thumb { width: 86px; height: 86px; border-radius: 16px; background: var(--surface); padding: 10px; display: grid; place-items: center; }
.thumb .chart { width: 100%; height: 100%; }
.chart.mini text { display: none; }

.card { transition: transform .2s var(--ease), background-color .2s; }
.card:active { transform: scale(.985); }
@media (hover: hover) {
  .card--feature:hover { background: color-mix(in srgb, var(--surface) 70%, var(--line)); }
  .card--row:hover .hl { color: var(--accent); }
  .card--lead:hover { transform: translateY(-2px); }
}

/* chart marks */
.chart text { font-family: var(--font); }
.chart .t { fill: var(--ink-2); font-size: 11px; }
.chart .tv { fill: var(--ink); font-size: 12px; font-weight: 650; font-variant-numeric: tabular-nums; }
.chart .tbig { fill: var(--ink); font-size: 30px; font-weight: 750; letter-spacing: -0.03em; }
.chart .m { fill: var(--accent); }
.chart .k { fill: var(--ctx); }
.chart .guide { stroke: var(--accent); stroke-width: 1.2; }
.chart .hatch { fill: var(--accent); }
.chart .g { stroke: var(--grid); stroke-width: 1; }
.chart .ln { stroke-width: 2.5; stroke-linecap: round; fill: none; }
.chart .ln.s1 { stroke: var(--accent); } .chart .ln.s2 { stroke: var(--accent-2); }
.chart .pt { stroke: var(--card); stroke-width: 2; }
.chart .pt.s1 { fill: var(--accent); } .chart .pt.s2 { fill: var(--accent-2); }
.chart .ring { fill: none; stroke: var(--accent); stroke-width: 1.5; }
.chart .lead-line { stroke: var(--accent); stroke-width: 1.2; }
.chart .zone { fill: none; stroke: var(--accent); stroke-width: 1.4; stroke-dasharray: 5 4; }
.chart .node { fill: var(--bg); stroke: var(--grid); stroke-width: 1; }
.chart .node.strong { stroke: var(--accent); }
.chart .arrow { stroke: var(--accent); stroke-width: 1.6; }
.chart .arrowhead { fill: var(--accent); }

/* coming up */
.get { margin-top: 28px; padding: 18px; border-radius: 16px; background: var(--surface); display: grid; gap: 4px; }
.get-t { margin: 0; font: 700 17px/1.25 var(--display); letter-spacing: -0.01em; }
.get-s { margin: 0 0 10px; font: 400 14px/1.45 var(--font); color: var(--ink-2); }
.get .addr, footer .addr { font-weight: 600; color: var(--ink); overflow-wrap: anywhere; }
.get-a { display: flex; flex-wrap: wrap; gap: 8px; }
.get-a a { display: inline-flex; align-items: center; height: 40px; padding: 0 16px; border-radius: 999px; font: 600 14px/1 var(--font); text-decoration: none; }
.get-a .go { background: var(--ink); color: var(--bg); }
.get-a .alt { border: 1px solid var(--line); background: var(--bg); color: var(--ink); }
.coming { margin-top: 34px; }
.arch-note { margin: 12px 0 0; padding: 10px 12px; border-radius: 12px; background: var(--surface); font: 500 13.5px/1.4 var(--font); color: var(--ink-2); }
.arch-note a { color: var(--ink); font-weight: 600; }
.foot-links { display: flex; flex-wrap: wrap; gap: 6px 18px; }
.foot-links a { color: var(--ink); font-weight: 600; text-decoration: none; }
.foot-links a:hover { text-decoration: underline; }
.doc { max-width: 680px; padding: 6px 2px 0; }
.doc h1 { margin: 12px 0 14px; font: 800 34px/1.05 var(--display); letter-spacing: -0.03em; }
.doc h2 { margin: 30px 0 8px; font: 700 19px/1.2 var(--display); letter-spacing: -0.015em; }
.doc p, .doc li { margin: 0 0 12px; font: 400 16px/1.55 var(--font); color: var(--ink); }
.doc ul { margin: 0 0 12px; padding-left: 20px; }
.doc .lede { font-size: 18px; line-height: 1.5; color: var(--ink-2); }
.doc a { color: var(--accent); }
.doc .addr { color: var(--ink); }
.doc .arch-list { list-style: none; margin: 8px 0 0; padding: 0; }
.arch-list a { display: grid; gap: 5px; padding: 15px 2px; border-top: 1px solid var(--line); text-decoration: none; color: var(--ink); }
.arch-list .d { font: 600 13px/1.2 var(--font); color: var(--ink-2); }
.arch-list .h { font: 700 17px/1.25 var(--display); letter-spacing: -0.01em; }
.arch-list .c { font: 400 13px/1.2 var(--font); color: var(--ink-2); }
.sec-h { margin: 0 2px 12px; font: 700 20px/1.1 var(--display); letter-spacing: -0.02em; }
.days { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(148px, 1fr); gap: 10px; overflow-x: auto; scrollbar-width: none; padding-bottom: 4px; }
.days::-webkit-scrollbar { display: none; }
.day { display: flex; flex-direction: column; gap: 3px; padding: 14px; border-radius: 18px; background: var(--surface); text-decoration: none; min-height: 118px; }
.d1 { font: 600 12.5px/1 var(--font); color: var(--ink-2); }
.d2 { font: 750 22px/1.1 var(--display); letter-spacing: -0.025em; }
.d3 { margin-top: auto; font: 500 13.5px/1.3 var(--font); color: var(--ink-2); }

footer { margin-top: 36px; padding-top: 18px; border-top: 1px solid var(--line); display: grid; gap: 10px; font: 400 13px/1.5 var(--font); color: var(--ink-2); max-width: 70ch; }
footer p { margin: 0; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; }

/* sheet */
.scrim { position: fixed; inset: 0; z-index: 40; background: rgb(8 10 14 / .45); opacity: 0; pointer-events: none; transition: opacity .32s var(--ease); }
.scrim.on { opacity: 1; pointer-events: auto; }
.sheet {
  position: fixed; z-index: 41; left: 0; right: 0; bottom: 0; max-height: 93dvh; display: flex; flex-direction: column;
  background: var(--bg); border-radius: 24px 24px 0 0; box-shadow: 0 -12px 48px rgb(0 0 0 / .22);
  transform: translateY(104%); transition: transform .46s var(--ease); outline: none;
}
.sheet.on { transform: none; }
.sheet-head { flex: none; padding: 8px 12px 6px 18px; touch-action: none; }
.grab { width: 40px; height: 5px; border-radius: 3px; background: var(--line); margin: 0 auto 8px; }
.sheet-nav { display: flex; align-items: center; justify-content: space-between; }
.pos { font: 600 13px/1 var(--font); color: var(--ink-2); font-variant-numeric: tabular-nums; }
.icons { display: flex; gap: 6px; }
.ib { width: 36px; height: 36px; border-radius: 50%; border: 0; background: var(--surface); display: grid; place-items: center; cursor: pointer; }
.ib svg { width: 16px; height: 16px; stroke: var(--ink); stroke-width: 1.8; fill: none; stroke-linecap: round; stroke-linejoin: round; }
.sheet-body { overflow-y: auto; overscroll-behavior: contain; padding: 4px 20px calc(30px + env(safe-area-inset-bottom)); -webkit-overflow-scrolling: touch; }
.s .kick { margin-top: 6px; }
.s-hl { margin: 10px 0 0; font: 750 26px/1.1 var(--display); letter-spacing: -0.03em; text-wrap: balance; }
.s-dek { margin: 8px 0 0; font: 400 16px/1.45 var(--font); color: var(--ink-2); }
.s-fig { margin: 18px 0 0; padding: 14px 14px 12px; border-radius: 18px; background: var(--surface); }
.s-fig .chart { width: 100%; height: auto; }
.s-cap { margin: 0 0 10px; font: 650 13px/1.2 var(--font); }
.s-note { margin: 10px 0 0; font: 400 12px/1.4 var(--font); color: var(--ink-2); }
.facts { margin-top: 18px; }
.fact { display: grid; grid-template-columns: 104px minmax(0, 1fr); gap: 14px; padding: 13px 0; border-top: 1px solid var(--line); }
.fact .st { font: 750 17px/1.25 var(--display); letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
.fact .tx { font: 400 15px/1.45 var(--font); }
.fn { font-size: 10.5px; line-height: 0; vertical-align: .55em; margin-left: 2px; font-weight: 700; }
.fn a { color: var(--accent); text-decoration: none; }
.open { --c: var(--warn); display: grid; gap: 4px; margin-top: 14px; padding: 13px 15px; border-radius: 16px; background: color-mix(in srgb, var(--c) 10%, var(--bg)); font: 400 14.5px/1.45 var(--font); }
.open b { color: var(--c); font: 700 12.5px/1.2 var(--font); }
.open--ok { --c: var(--ink-2); } .open--bad { --c: var(--bad); }
.srcs { margin-top: 22px; }
.srcs h3 { margin: 0 0 6px; font: 700 13px/1 var(--font); color: var(--ink-2); }
.src { display: grid; grid-template-columns: 32px minmax(0, 1fr) 16px; gap: 12px; align-items: center; padding: 11px 0; border-top: 1px solid var(--line); text-decoration: none; }
.av { width: 32px; height: 32px; border-radius: 9px; display: grid; place-items: center; color: #fff; font: 700 14px/1 var(--font); }
.src-t { display: grid; gap: 2px; min-width: 0; }
.nm { font: 600 14.5px/1.25 var(--font); display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; }
.no { color: var(--accent); font-variant-numeric: tabular-nums; }
.kind { font: 500 11.5px/1 var(--font); color: var(--ink-3); }
.ds { font: 400 13px/1.35 var(--font); color: var(--ink-2); }
.ext { width: 14px; height: 14px; stroke: var(--ink-3); stroke-width: 1.6; fill: none; stroke-linecap: round; }
@media (hover: hover) { .src:hover .nm { color: var(--accent); } }
.corr { margin: 16px 0 0; padding: 10px 12px; border-radius: 10px; background: var(--surface); font: 400 13px/1.45 var(--font); color: var(--ink); }
.corr b { font-weight: 600; }
.disc { margin: 16px 0 0; font: 400 12.5px/1.45 var(--font); color: var(--ink-2); }
.s-actions { display: flex; gap: 8px; margin-top: 18px; }
.pill { border: 1px solid var(--line); background: var(--bg); border-radius: 999px; padding: 10px 16px; font: 600 14px/1 var(--font); cursor: pointer; }
.s-next { display: grid; gap: 4px; margin-top: 22px; padding: 16px; border-radius: 18px; background: var(--surface); text-decoration: none; }
.s-next .lbl { font: 600 12.5px/1 var(--font); color: var(--ink-2); }
.s-next .nh { font: 650 16px/1.3 var(--display); letter-spacing: -0.015em; }

@media (min-width: 760px) {
  .app { padding: 0 28px 72px; }
  .hero h1 { font-size: 44px; }
  .feed { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
  .card--lead { grid-column: 1 / -1; padding: 28px 28px 20px; }
  .card--lead .hl { font-size: 38px; max-width: 18ch; }
  .card--row { padding: 18px 4px; }
  .tabs { display: inline-flex; }
  .tab { flex: none; }
  .sheet { left: 50%; right: auto; top: 50%; bottom: auto; width: min(720px, 92vw); max-height: 88vh; border-radius: 24px;
    transform: translate(-50%, -47%) scale(.98); opacity: 0; transition: transform .38s var(--ease), opacity .24s; }
  .sheet.on { transform: translate(-50%, -50%); opacity: 1; }
  .grab { display: none; }
  .sheet-body { padding: 4px 32px 32px; }
  .s-hl { font-size: 32px; }
}
@media (min-width: 1060px) {
  .feed { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .card--lead { grid-column: span 2; grid-row: span 2; }
  .card--lead .cover { margin-top: auto; padding-top: 18px; }
}

/* brief */
.brief { position: fixed; inset: 0; z-index: 60; display: none; flex-direction: column; background: var(--brand); color: #fff;
  padding: calc(12px + env(safe-area-inset-top)) 20px calc(26px + env(safe-area-inset-bottom)); outline: none; }
.brief.on { display: flex; }
.b-bars { display: grid; grid-auto-flow: column; grid-auto-columns: 1fr; gap: 4px; }
.b-bar { height: 3px; border-radius: 2px; background: rgb(255 255 255 / .28); overflow: hidden; }
.b-bar i { display: block; height: 100%; width: 0; background: #fff; }
.b-bar.done i { width: 100%; }
.b-bar.run i { animation: fill 6s linear forwards; }
.brief.paused .b-bar.run i { animation-play-state: paused; }
@keyframes fill { from { width: 0; } to { width: 100%; } }
.b-top { display: flex; align-items: center; justify-content: space-between; margin-top: 14px; font: 600 14px/1 var(--font); position: relative; z-index: 3; }
.b-top .wm { color: #fff; font-size: 16px; }
.b-top .logo-bg { fill: #fff; } .b-top .logo-ln { stroke: var(--brand); }
.b-close { width: 38px; height: 38px; border-radius: 50%; border: 0; background: rgb(255 255 255 / .16); display: grid; place-items: center; cursor: pointer; }
.b-close svg { width: 16px; height: 16px; stroke: #fff; stroke-width: 2; fill: none; stroke-linecap: round; }
.b-stage { position: relative; flex: 1; display: grid; }
.b-slide { grid-area: 1 / 1; display: none; flex-direction: column; justify-content: center; gap: 14px; max-width: 680px; }
.b-slide.on { display: flex; }
.b-kick { margin: 0; font: 600 15px/1 var(--font); opacity: .72; }
.b-big { margin: 0; font: 800 clamp(72px, 23vw, 168px)/.88 var(--display); letter-spacing: -0.055em; font-variant-numeric: tabular-nums; }
.b-line { margin: 0; font: 600 clamp(21px, 5.6vw, 30px)/1.22 var(--display); letter-spacing: -0.02em; max-width: 20ch; }
.b-cta { position: relative; z-index: 3; align-self: flex-start; margin-top: 12px; padding: 14px 20px; border-radius: 999px; background: #fff; color: var(--brand); text-decoration: none; font: 650 15px/1 var(--font); }
.b-tap { position: absolute; z-index: 2; top: 90px; bottom: 0; border: 0; background: transparent; cursor: pointer; }
.b-tap.prev { left: 0; width: 30%; } .b-tap.next { right: 0; width: 70%; }
.b-hint { margin: 0; font: 500 12.5px/1 var(--font); opacity: .6; }

.toast { position: fixed; z-index: 80; left: 50%; bottom: calc(24px + env(safe-area-inset-bottom)); transform: translate(-50%, 12px);
  background: var(--ink); color: var(--bg); padding: 11px 16px; border-radius: 999px; font: 600 14px/1 var(--font); opacity: 0; pointer-events: none; }
.toast.show { opacity: 1; transform: translate(-50%, 0); }

@media (prefers-reduced-motion: no-preference) {
  .ind { transition: transform .38s var(--ease), width .38s var(--ease); }
  .toast { transition: opacity .2s, transform .3s var(--ease); }
  .live i { animation: pulse 2.4s ease-out infinite; }
  @keyframes pulse { 0% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--ok) 55%, transparent); } 70%, 100% { box-shadow: 0 0 0 8px transparent; } }
  .b-slide.on > * { animation: rise .5s var(--ease) both; }
  .b-slide.on > :nth-child(2) { animation-delay: .04s; } .b-slide.on > :nth-child(3) { animation-delay: .09s; } .b-slide.on > :nth-child(4) { animation-delay: .14s; }
  @keyframes rise { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
}
@media (prefers-reduced-motion: reduce) {
  .sheet, .scrim, .card { transition: none; }
  .b-bar.run i { animation: none; width: 100%; }
}
"""

JS = r"""
(function () {
  var ORDER = __ORDER__;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var html = document.documentElement;
  var sheet = $('#sheet'), body = $('#sheet-body'), scrim = $('#scrim'), pos = $('#pos');
  var brief = $('#brief'), slides = $$('.b-slide', brief), bars = $$('.b-bar', brief);
  var toastEl = $('#toast'), toastT;
  var current = null, briefOn = false, lastFocus = null, bi = 0, pushed = false;

  function toast(m) { toastEl.textContent = m; toastEl.classList.add('show'); clearTimeout(toastT); toastT = setTimeout(function () { toastEl.classList.remove('show'); }, 2000); }
  function isStory(id) { return ORDER.indexOf(id) !== -1; }
  var BASE = html.getAttribute('data-base') || '', PERMA = html.getAttribute('data-permalink') || '';
  var canShare = !!(navigator.share && PERMA);
  function fromPath() {
    if (!BASE || location.pathname.indexOf(BASE) !== 0) return '';
    var rest = location.pathname.slice(BASE.length).replace(/\/+$/, '');
    try { rest = decodeURIComponent(rest); } catch (e) {}
    return isStory(rest) ? rest : '';
  }
  function urlFor(h) {
    if (h === 'brief') return location.pathname + location.search + '#brief';
    if (h) return BASE ? BASE + h + '/' : '#' + h;
    return fromPath() ? BASE : location.pathname + location.search;
  }
  function setHash(h, push) {
    try {
      if (push) { history.pushState({ r: h }, '', urlFor(h)); pushed = true; }
      else history.replaceState(h ? { r: h } : null, '', urlFor(h));
    } catch (e) {}
  }

  // ----- sheet -----
  function fill(id) {
    var tpl = document.getElementById('tpl-' + id);
    if (!tpl) return false;
    body.textContent = '';
    body.appendChild(tpl.content.cloneNode(true));
    if (canShare) { var cp = body.querySelector('.copy'); if (cp) cp.textContent = 'Share'; }
    body.scrollTop = 0;
    current = id;
    pos.textContent = (ORDER.indexOf(id) + 1) + ' of ' + ORDER.length;
    return true;
  }
  function openSheet(id, push) {
    if (!fill(id)) return;
    if (!sheet.classList.contains('on')) {
      lastFocus = document.activeElement;
      sheet.removeAttribute('inert'); sheet.setAttribute('aria-hidden', 'false');
      sheet.classList.add('on'); scrim.classList.add('on'); html.classList.add('lock');
      setTimeout(function () { sheet.focus({ preventScroll: true }); }, 60);
    }
    setHash(id, push);
  }
  function closeSheet(fromPop) {
    if (!current) return;
    current = null;
    sheet.classList.remove('on'); scrim.classList.remove('on'); html.classList.remove('lock');
    sheet.setAttribute('aria-hidden', 'true'); sheet.setAttribute('inert', '');
    if (fromPop) pushed = false;
    else if (pushed) { pushed = false; history.back(); }
    else setHash('', false);
    if (lastFocus && lastFocus.focus) lastFocus.focus({ preventScroll: true });
  }
  function step(d) {
    if (!current) return;
    var i = (ORDER.indexOf(current) + d + ORDER.length) % ORDER.length;
    fill(ORDER[i]); setHash(ORDER[i], false);
  }
  $('#s-close').addEventListener('click', function () { closeSheet(false); });
  $('#s-prev').addEventListener('click', function () { step(-1); });
  $('#s-next').addEventListener('click', function () { step(1); });
  scrim.addEventListener('click', function () { closeSheet(false); });

  var sx = 0, sy = 0, st = 0;
  body.addEventListener('touchstart', function (e) { var t = e.touches[0]; sx = t.clientX; sy = t.clientY; st = Date.now(); }, { passive: true });
  body.addEventListener('touchend', function (e) {
    var t = e.changedTouches[0], dx = t.clientX - sx, dy = t.clientY - sy;
    if (Math.abs(dx) > 70 && Math.abs(dx) > Math.abs(dy) * 1.6 && Date.now() - st < 600) step(dx < 0 ? 1 : -1);
  }, { passive: true });
  var head = $('.sheet-head'), y0 = null, narrow = window.matchMedia('(max-width: 759px)');
  head.addEventListener('touchstart', function (e) { if (!narrow.matches) return; y0 = e.touches[0].clientY; sheet.style.transition = 'none'; }, { passive: true });
  head.addEventListener('touchmove', function (e) { if (y0 === null) return; var d = Math.max(0, e.touches[0].clientY - y0); sheet.style.transform = 'translateY(' + d + 'px)'; }, { passive: true });
  head.addEventListener('touchend', function (e) {
    if (y0 === null) return;
    var d = e.changedTouches[0].clientY - y0; y0 = null;
    sheet.style.transition = ''; sheet.style.transform = '';
    if (d > 110) closeSheet(false);
  });

  // ----- brief -----
  function show(i) {
    bi = Math.max(0, Math.min(slides.length - 1, i));
    slides.forEach(function (s, k) { s.classList.toggle('on', k === bi); });
    bars.forEach(function (b, k) { b.classList.toggle('done', k < bi); b.classList.remove('run'); });
    void bars[bi].offsetWidth; bars[bi].classList.add('run');
  }
  bars.forEach(function (b, k) {
    b.firstElementChild.addEventListener('animationend', function () {
      if (!briefOn || k !== bi) return;
      if (bi < slides.length - 1) show(bi + 1); else closeBrief(false);
    });
  });
  function openBrief(push) {
    briefOn = true; lastFocus = document.activeElement;
    brief.classList.add('on'); brief.removeAttribute('inert'); html.classList.add('lock');
    show(0); setHash('brief', push);
    setTimeout(function () { brief.focus({ preventScroll: true }); }, 30);
  }
  function closeBrief(fromPop) {
    if (!briefOn) return;
    briefOn = false; brief.classList.remove('on', 'paused'); brief.setAttribute('inert', ''); html.classList.remove('lock');
    bars.forEach(function (b) { b.classList.remove('run', 'done'); });
    if (fromPop) pushed = false;
    else if (pushed) { pushed = false; history.back(); }
    else setHash('', false);
    if (lastFocus && lastFocus.focus) lastFocus.focus({ preventScroll: true });
  }
  $('.b-close').addEventListener('click', function () { closeBrief(false); });
  $('.b-tap.prev').addEventListener('click', function () { show(bi - 1); });
  $('.b-tap.next').addEventListener('click', function () { if (bi < slides.length - 1) show(bi + 1); else closeBrief(false); });
  brief.addEventListener('pointerdown', function (e) { if (!e.target.closest('a,button')) brief.classList.add('paused'); });
  ['pointerup', 'pointercancel', 'pointerleave'].forEach(function (ev) { brief.addEventListener(ev, function () { brief.classList.remove('paused'); }); });

  // ----- routing -----
  document.addEventListener('click', function (e) {
    var a = e.target.closest('a[data-story], a[href="#brief"]');
    if (a && !(e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button > 0)) {
      var h = a.getAttribute('data-story') || 'brief';
      if (h === 'brief') { e.preventDefault(); openBrief(true); return; }
      if (isStory(h)) {
        e.preventDefault();
        if (briefOn) { var keep = pushed; closeBrief(true); pushed = keep; setHash(h, false); openSheet(h, false); return; }
        if (current) { fill(h); setHash(h, false); } else openSheet(h, true);
        return;
      }
    }
    var c = e.target.closest('.copy');
    if (c) {
      var cid = c.getAttribute('data-id');
      var url = PERMA ? PERMA + cid + '/' : location.href.split('#')[0] + '#' + cid;
      if (canShare) {
        var hl = body.querySelector('.s-hl');
        navigator.share({ title: hl ? hl.textContent : document.title, url: url }).catch(function () {});
        return;
      }
      try { navigator.clipboard.writeText(url).then(function () { toast('Link copied'); }, function () { toast('Copy blocked by the browser'); }); }
      catch (err) { toast('Copy blocked by the browser'); }
    }
  });
  function route() {
    var h = location.hash.slice(1);
    if (h === 'brief') { if (current) closeSheet(true); if (!briefOn) openBrief(false); return; }
    if (briefOn) closeBrief(true);
    if (!isStory(h)) h = fromPath();
    if (h) { if (current !== h) { if (current) { fill(h); } else openSheet(h, false); } }
    else if (current) closeSheet(true);
  }
  window.addEventListener('popstate', route);
  window.addEventListener('hashchange', route);

  document.addEventListener('keydown', function (e) {
    if (briefOn) {
      if (e.key === 'Escape') closeBrief(false);
      else if (e.key === 'ArrowRight') { if (bi < slides.length - 1) show(bi + 1); else closeBrief(false); }
      else if (e.key === 'ArrowLeft') show(bi - 1);
      else if (e.key === ' ') { e.preventDefault(); brief.classList.toggle('paused'); }
      return;
    }
    if (current) {
      if (e.key === 'Escape') closeSheet(false);
      else if (e.key === 'ArrowRight' || e.key === 'j') step(1);
      else if (e.key === 'ArrowLeft' || e.key === 'k') step(-1);
    }
  });

  // ----- tabs -----
  var tabs = $$('.tab'), ind = $('.ind'), cards = $$('.card');
  function moveInd(t) { ind.style.width = t.offsetWidth + 'px'; ind.style.transform = 'translateX(' + t.offsetLeft + 'px)'; }
  function sel() { return tabs.filter(function (t) { return t.getAttribute('aria-selected') === 'true'; })[0]; }
  tabs.forEach(function (t) {
    t.addEventListener('click', function () {
      tabs.forEach(function (o) { o.setAttribute('aria-selected', o === t ? 'true' : 'false'); });
      moveInd(t);
      var topic = t.getAttribute('data-topic');
      cards.forEach(function (c) { c.hidden = !(topic === 'all' || c.getAttribute('data-topic') === topic); });
      t.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' });
    });
  });
  function place() { moveInd(sel()); }
  window.addEventListener('resize', place);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(place);
  place();

  sheet.setAttribute('inert', ''); brief.setAttribute('inert', '');
  route();
})();
"""

TEMPLATE = """<!DOCTYPE html>
<html lang="en"__HTMLATTR__>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
__HEAD__
<style>__CSS__</style>
</head>
<body>
<div class="app">
  <header class="bar">
    <a class="wm" href="__HOME__" aria-label="Receipts, today's edition">__LOGO__<span>Receipts</span></a>
    <a class="btn-brief" href="#brief">__PLAY__<span>60-second brief</span></a>
  </header>
  <section class="hero">
    <p class="dayname">__DAY__</p>
    <h1>__DATE__</h1>
    <p class="live"><i aria-hidden="true"></i>__UPD__</p>__ARCH__
  </section>
  <nav class="tabs-wrap" aria-label="Topics"><div class="tabs" role="tablist"><span class="ind" aria-hidden="true"></span>__TABS__</div></nav>
  <main class="feed" id="feed">__CARDS__</main>__GET__
  __COMING__
  <footer>
    <p class="legend"><span class="ev ev--ok">Filing or company</span><span class="ev ev--warn">Press report</span><span class="ev ev--bad">Unconfirmed</span></p>
    <p>Every number in a story links to the source it came from. Tap a story for its facts, chart and sources.</p>
    <p>Researched, checked against its sources and published each morning by an AI agent: Claude, a model made by Anthropic. Anthropic is covered like any other company. Mistakes are fixed on the story, with a dated correction. No ads, no sponsors.</p>
    __TIPS__
    __LINKS__
  </footer>
</div>

<div class="scrim" id="scrim"></div>
<section class="sheet" id="sheet" role="dialog" aria-modal="true" aria-labelledby="s-hl" aria-hidden="true" tabindex="-1">
  <div class="sheet-head">
    <div class="grab" aria-hidden="true"></div>
    <div class="sheet-nav">
      <span class="pos" id="pos"></span>
      <div class="icons">
        <button class="ib" id="s-prev" type="button" aria-label="Previous story">__CHEVL__</button>
        <button class="ib" id="s-next" type="button" aria-label="Next story">__CHEVR__</button>
        <button class="ib" id="s-close" type="button" aria-label="Close">__X__</button>
      </div>
    </div>
  </div>
  <div class="sheet-body" id="sheet-body"></div>
</section>

<div class="brief" id="brief" role="dialog" aria-modal="true" aria-label="60-second brief" tabindex="-1">
  <div class="b-bars">__BARS__</div>
  <div class="b-top"><span class="wm">__LOGO__<span>Receipts brief</span></span><button class="b-close" type="button" aria-label="Close brief">__X__</button></div>
  <div class="b-stage">__SLIDES__
    <button class="b-tap prev" type="button" aria-label="Previous"></button>
    <button class="b-tap next" type="button" aria-label="Next"></button>
  </div>
  <p class="b-hint">Tap to go on. Hold to pause.</p>
</div>
<div class="toast" id="toast" role="status" aria-live="polite"></div>
__TPLS__
<script>__JS__</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
