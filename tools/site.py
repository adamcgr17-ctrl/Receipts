"""Builds the Receipts website into docs/, which GitHub Pages serves.

Usage, from the repository root:  python3 tools/site.py

Inputs:  site.json (site_url, inbox, x_url, subscribe_url, domain)
         data/editions/YYYY-MM-DD.json (one file per edition; the newest is today's)
Output:  docs/  the whole site: today's page, a permanent page per edition and per story,
         share images, archive, about, RSS and JSON feeds, llms.txt, sitemap, icons.
"""
import datetime
import html
import json
import pathlib
import sys
import zoneinfo
from email.utils import format_datetime
from urllib.parse import urlparse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build as B  # noqa: E402

ROOT = pathlib.Path.cwd()
OUT = ROOT / "docs"
CT = zoneinfo.ZoneInfo("America/Chicago")
CFG = json.loads((ROOT / "site.json").read_text())
CNAME = OUT / "CNAME"
DOMAIN = CFG.get("domain") or (CNAME.read_text().strip() if CNAME.exists() else "")
SITE = (f"https://{DOMAIN}/" if DOMAIN else CFG["site_url"].rstrip("/") + "/")
SP = urlparse(SITE).path or "/"
HOST = "" if ("OWNER" in SITE or urlparse(SITE).netloc.endswith("github.io")) else urlparse(SITE).netloc  # cards show the address only once it is a real domain
FULL_STORY_DAYS = 14   # editions this recent get a full page per story; older ones get a light page
OG_KEEP_DAYS = 60      # share images older than this are deleted to keep the site small
CHANNELS = ("inbox", "x_url", "subscribe_url")
esc = B.esc


def write(rel, text):
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def nice_date(dt):
    return f"{dt.strftime('%A')}, {dt.strftime('%B')} {dt.day}"


# ---------- editions ----------

files = sorted((ROOT / "data" / "editions").glob("????-??-??.json"))
if not files:
    raise SystemExit("No editions in data/editions/")
EDS = []
for f in files:
    d = json.loads(f.read_text())
    if f == files[-1] and not str(d.get("published_at", "")).startswith(f.stem):
        d["published_at"] = datetime.datetime.now(CT).isoformat(timespec="minutes")
        f.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n")
    for k in CHANNELS:
        if CFG.get(k):
            d[k] = CFG[k]
        else:
            d.pop(k, None)
    EDS.append((f.stem, d))
LATEST = EDS[-1][0]
TODAY = datetime.date.fromisoformat(LATEST)

B.load(EDS[-1][1])
B.validate()  # today's edition must pass; older ones were checked when they ran


def page_meta(date, d, story=None, root=False):
    dt = datetime.datetime.fromisoformat(d["published_at"]).astimezone(CT)
    base, perma = f"{SP}e/{date}/", f"{SITE}e/{date}/"
    m = dict(base=base, permalink=perma, site_path=SP, home=SP, archived=date != LATEST,
             about=f"{SP}about/", archive=f"{SP}archive/", feed=f"{SP}feed.xml", json=f"{SP}edition.json",
             published=d["published_at"], analytics=CFG.get("analytics", ""))
    lead = d["stories"][0]
    if story:
        m.update(title=f'{story["headline"]} | Receipts', og_title=story["headline"], description=story["dek"],
                 canonical=f"{perma}{story['id']}/", og_type="article", og_image=og_url(date, story["id"]),
                 og_alt=f'{story["headline"]}. Chart and sources inside.')
    else:
        m.update(title=f"Receipts: AI and agent-economy news, {nice_date(dt)}",
                 og_title=f"Receipts, {nice_date(dt)}: {lead['headline']}",
                 description=f"{lead['headline']}. Plus {len(d['stories']) - 1} more stories, every number linked to its source.",
                 canonical=SITE if root else perma, og_type="website", og_image=og_url(date),
                 og_alt=f"Receipts for {nice_date(dt)}. Lead story: {lead['headline']}")
    return m


def og_url(date, sid=None):
    age = (TODAY - datetime.date.fromisoformat(date)).days
    if age > OG_KEEP_DAYS:
        return f"{SITE}og/default.png"
    return f"{SITE}og/{date}/{sid}.png" if sid else f"{SITE}og/{date}.png"


def light_story_page(date, d, s):
    """For older editions: share tags, then straight on to the story inside its edition page."""
    m = page_meta(date, d, s)
    B.load(d, m)
    target = f"{m['base']}#{s['id']}"
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">{B.head()}'
            f'<meta http-equiv="refresh" content="0; url={esc(target)}">'
            f'<script>location.replace({json.dumps(target)})</script></head>'
            f'<body><p><a href="{esc(target)}">{esc(s["headline"])}</a></p></body></html>')


pages = []  # (url, lastmod) for the sitemap
for date, d in EDS:
    age = (TODAY - datetime.date.fromisoformat(date)).days
    B.load(d, page_meta(date, d))
    write(f"e/{date}/index.html", B.render()[0])
    pages.append((f"{SITE}e/{date}/", date))
    for s in d["stories"]:
        if age <= FULL_STORY_DAYS:
            B.load(d, page_meta(date, d, s))
            write(f"e/{date}/{s['id']}/index.html", B.render()[0])
            pages.append((f"{SITE}e/{date}/{s['id']}/", date))
        else:
            write(f"e/{date}/{s['id']}/index.html", light_story_page(date, d, s))
    pub = {"date": date, "published_at": d["published_at"], "url": f"{SITE}e/{date}/",
           "stories": [dict(s, url=f"{SITE}e/{date}/{s['id']}/") for s in d["stories"]],
           "brief": d["brief"], "coming": d["coming"]}
    write(f"e/{date}/edition.json", json.dumps(pub, indent=1, ensure_ascii=False))
    if date == LATEST:
        write("edition.json", json.dumps(pub, indent=1, ensure_ascii=False))

d = EDS[-1][1]
B.load(d, page_meta(LATEST, d, root=True))
write("index.html", B.render()[0])
pages.insert(0, (SITE, LATEST))


# ---------- plain pages: about, archive, 404 ----------

DOC = """<!DOCTYPE html>
<html lang="en">
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
    <a class="btn-brief" href="__HOME__"><span>Today's edition</span></a>
  </header>
  <main class="doc">__BODY__</main>
  <footer>__LINKS__</footer>
</div>
</body>
</html>
"""


def doc_page(rel, title, description, body):
    m = dict(page_meta(LATEST, d, root=True), title=f"{title} | Receipts", og_title=title, description=description,
             canonical=f"{SITE}{rel}", og_type="website")
    B.load(d, m)
    links = (f'<nav class="foot-links" aria-label="More from Receipts"><a href="{SP}">Today\'s edition</a>'
             f'<a href="{SP}about/">How it works</a><a href="{SP}archive/">Past editions</a>'
             f'<a href="{SP}feed.xml">RSS</a><a href="{SP}edition.json">Data for agents</a></nav>')
    return (DOC.replace("__HEAD__", B.head()).replace("__CSS__", B.CSS).replace("__HOME__", SP)
            .replace("__LOGO__", B.LOGO).replace("__BODY__", body).replace("__LINKS__", links))


inbox = CFG.get("inbox", "")
mail = (f'<a class="addr" href="mailto:{esc(inbox)}?subject=Subscribe">{esc(inbox)}</a>' if inbox else "")
get_items = []
if inbox:
    get_items.append(f"<li>Email: send the word subscribe to {mail}. Reply stop anytime.</li>")
if CFG.get("subscribe_url"):
    get_items.append(f'<li>Email: <a href="{esc(CFG["subscribe_url"])}">sign up here</a>.</li>')
if CFG.get("x_url"):
    get_items.append(f'<li>X: <a href="{esc(CFG["x_url"])}">follow Receipts</a>.</li>')
get_items += [f'<li>RSS: <a href="{SP}feed.xml">feed.xml</a>, or <a href="{SP}feed.json">JSON Feed</a>.</li>',
              f'<li>For agents: today\'s edition as data at <a href="{SP}edition.json">edition.json</a>, '
              f'and a site guide at <a href="{SP}llms.txt">llms.txt</a>.</li>']
report = (f"Report one to {mail.replace('Subscribe', 'Correction')}. The agent checks every report against the sources "
          "before the next edition." if inbox else "")
about = f"""<h1>How Receipts works</h1>
<p class="lede">Receipts is a daily page on the agentic economy and frontier AI. Each morning it answers one question: what actually happened, and how do we know?</p>
<h2>Reported by an agent</h2>
<p>Every morning an AI agent, Claude, made by Anthropic, reads the previous day's filings, company announcements, data releases and reporting. It picks the stories that matter most, ranked by money moved, people affected and how hard the change is to reverse. Then it writes each story, draws its chart, checks the page and publishes it. An editor sets the rules the agent follows. The agent does the reporting.</p>
<h2>Every number has a receipt</h2>
<p>Each fact is footnoted to numbered sources, and every source is labeled by kind: Filing, Company, Press or Data. If a number does not appear in a source the agent read, it does not run.</p>
<h2>How sure we are</h2>
<ul>
<li><b>Filing or company:</b> confirmed by a regulatory filing or by the company itself.</li>
<li><b>Press report:</b> credible reporting the company has not confirmed.</li>
<li><b>Unconfirmed:</b> one source, or anonymous ones. Used sparingly.</li>
</ul>
<p>Every story also says what is still unknown.</p>
<h2>Corrections</h2>
<p>When something is wrong, it is fixed on the story with a dated correction. {report}</p>
<h2>Independence</h2>
<p>Receipts is free. No ads, no sponsors, no paid placement. Claude is made by Anthropic, so stories about Anthropic carry a disclosure, and Anthropic is covered like any other company.</p>
<h2>Get it every morning</h2>
<ul>{''.join(get_items)}</ul>"""
write("about/index.html", doc_page("about/", "How Receipts works",
                                   "How the agent reports, sources and corrects Receipts.", about))
pages.append((f"{SITE}about/", LATEST))

rows = []
for date, ed in reversed(EDS):
    dt = datetime.datetime.fromisoformat(ed["published_at"]).astimezone(CT)
    rows.append(f'<li><a href="{SP}e/{date}/"><span class="d">{esc(nice_date(dt))}</span>'
                f'<span class="h">{esc(ed["stories"][0]["headline"])}</span>'
                f'<span class="c">{len(ed["stories"])} stories</span></a></li>')
archive = ('<h1>Past editions</h1><p class="lede">Every edition since the first, newest first. '
           'Each one stays as it was published, corrections included.</p>'
           f'<ul class="arch-list">{"".join(rows)}</ul>')
write("archive/index.html", doc_page("archive/", "Past editions", "Every Receipts edition, newest first.", archive))
pages.append((f"{SITE}archive/", LATEST))

write("404.html", doc_page("404.html", "Page not found", "This page does not exist.",
                           f'<h1>Nothing here</h1><p class="lede">This page does not exist, or it moved.</p>'
                           f'<p><a href="{SP}">Read today\'s edition</a></p>'))


# ---------- feeds, guides, sitemap ----------

def story_html(s):
    facts = "".join(f"<li><b>{esc(f['stat'])}</b> {esc(f['text'])}</li>" for f in s["facts"])
    srcs = "".join(f'<li><a href="{esc(x["url"])}">{esc(x["name"])}</a>: {esc(x["desc"])} ({esc(x["kind"])})</li>'
                   for x in s["sources"])
    return f"<p>{esc(s['dek'])}</p><ul>{facts}</ul><p>Sources:</p><ol>{srcs}</ol><p>Confidence: {esc(s['evidence'])}</p>"


recent = list(reversed(EDS))[:7]
items, jitems = [], []
for date, ed in recent:
    when = datetime.datetime.fromisoformat(ed["published_at"])
    for s in ed["stories"]:
        url = f"{SITE}e/{date}/{s['id']}/"
        items.append(f"<item><title>{esc(s['headline'])}</title><link>{url}</link>"
                     f'<guid isPermaLink="true">{url}</guid><pubDate>{format_datetime(when)}</pubDate>'
                     f"<category>{esc(s['topic'])}</category><description>{esc(story_html(s))}</description></item>")
        jitems.append({"id": url, "url": url, "title": s["headline"], "summary": s["dek"],
                       "content_html": story_html(s), "date_published": ed["published_at"],
                       "tags": [s["topic"]], "image": og_url(date, s["id"])})
now = datetime.datetime.fromisoformat(d["published_at"])
write("feed.xml", f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>
<title>Receipts</title><link>{SITE}</link>
<description>AI and agent-economy news. Every number links to its source.</description>
<language>en-us</language><lastBuildDate>{format_datetime(now)}</lastBuildDate>
<atom:link href="{SITE}feed.xml" rel="self" type="application/rss+xml"/>
<image><url>{SITE}icon-192.png</url><title>Receipts</title><link>{SITE}</link></image>
{''.join(items)}
</channel></rss>
""")
write("feed.json", json.dumps({"version": "https://jsonfeed.org/version/1.1", "title": "Receipts",
                               "home_page_url": SITE, "feed_url": f"{SITE}feed.json",
                               "description": "AI and agent-economy news. Every number links to its source.",
                               "icon": f"{SITE}icon-512.png", "favicon": f"{SITE}icon-32.png",
                               "items": jitems}, indent=1, ensure_ascii=False))
contact = f"\n## Contact\n\n- Corrections, tips and subscriptions: {inbox}\n" if inbox else ""
write("llms.txt", f"""# Receipts

> A daily news page on the agentic economy and frontier AI. Every number links to the filing, company post, report or dataset it came from, and each story carries a confidence label. Researched and published each morning by an AI agent (Claude, made by Anthropic).

## Read

- [Today's edition]({SITE}): the front page
- [Today's edition as JSON]({SITE}edition.json): stories, facts, sources and chart data
- [RSS feed]({SITE}feed.xml) and [JSON Feed]({SITE}feed.json): the last seven days, one item per story
- [Past editions]({SITE}archive/): one permanent page per day, at {SITE}e/YYYY-MM-DD/
- [How it works]({SITE}about/): sourcing rules, confidence labels, corrections
{contact}""")
write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {SITE}sitemap.xml\n")
write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
      + "".join(f"<url><loc>{u}</loc><lastmod>{m}</lastmod></url>" for u, m in pages) + "</urlset>\n")
write("site.webmanifest", json.dumps({
    "name": "Receipts", "short_name": "Receipts", "description": "AI and agent-economy news. Every number links to its source.",
    "start_url": SP, "scope": SP, "display": "standalone", "background_color": "#FFFFFF", "theme_color": "#FFFFFF",
    "icons": [{"src": f"{SP}icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
              {"src": f"{SP}icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}]}, indent=1))
write(".nojekyll", "")
if DOMAIN:
    write("CNAME", DOMAIN + "\n")


# ---------- images: share cards and icons ----------

OG_CSS = """
html, body { margin: 0; width: 1200px; height: 630px; overflow: hidden; background: #002FA7; }
.og { box-sizing: border-box; width: 1200px; height: 630px; padding: 54px 64px 50px; color: #fff;
  display: grid; grid-template-columns: minmax(0, 1fr) 470px; grid-template-rows: auto 1fr auto; column-gap: 48px;
  --font: Inter, sans-serif; --display: "Inter Display", Inter, sans-serif;
  --accent: #FFFFFF; --accent-2: #FFB37A; --ctx: rgb(255 255 255 / .32); --grid: rgb(255 255 255 / .22);
  --ink: #FFFFFF; --ink-2: rgb(255 255 255 / .78); --card: #002FA7; --surface: #002FA7; --bg: #002FA7;
  --line: rgb(255 255 255 / .22); background: #002FA7; font-family: Inter, sans-serif; }
.og-top { grid-column: 1 / -1; display: flex; justify-content: space-between; align-items: center; }
.og-brand { display: flex; align-items: center; gap: 14px; font: 700 31px/1 "Inter Display", Inter, sans-serif; letter-spacing: -0.02em; }
.og-brand svg { width: 44px; height: 44px; }
.og-brand .logo-bg { fill: #fff; } .og-brand .logo-ln { stroke: #002FA7; stroke-width: 2.4; stroke-linecap: round; fill: none; }
.og-meta { display: flex; gap: 22px; font: 600 23px/1 Inter, sans-serif; color: rgb(255 255 255 / .78); }
.og-text { align-self: center; min-width: 0; }
.og-kick { margin: 0 0 18px; font: 600 23px/1.2 Inter, sans-serif; color: rgb(255 255 255 / .78); }
.og-hl { margin: 0; font: 800 58px/1.05 "Inter Display", Inter, sans-serif; letter-spacing: -0.035em;
  display: -webkit-box; -webkit-line-clamp: 5; -webkit-box-orient: vertical; overflow: hidden; text-wrap: balance; }
.og-hl.sm { font-size: 50px; }
.og-chart { grid-row: 2; grid-column: 2; align-self: center; height: 400px; display: flex; align-items: center; }
.og-chart .chart { width: 100%; height: 100%; overflow: visible; }
.og-foot { grid-column: 1 / -1; display: flex; justify-content: space-between; align-items: center;
  font: 600 23px/1 Inter, sans-serif; color: rgb(255 255 255 / .86); }
.og-foot .l { display: flex; gap: 26px; align-items: center; }
.og-ev { display: inline-flex; align-items: center; gap: 11px; }
.og-ev i { width: 13px; height: 13px; border-radius: 50%; background: var(--c); }
.og-solo { grid-column: 1 / -1; align-self: center; }
.og-solo .og-hl { font-size: 84px; -webkit-line-clamp: 3; max-width: 15ch; }
.og-solo p { margin: 22px 0 0; font: 500 32px/1.3 Inter, sans-serif; color: rgb(255 255 255 / .82); max-width: 24ch; }
"""
TIER_DOT = {"ok": "#7BE3AE", "warn": "#FFD27A", "bad": "#FF9C94"}


def og_html(inner):
    return (f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>{B.CSS}{OG_CSS}</style></head>'
            f'<body><div class="og">{inner}</div></body></html>')


def og_card(date, ed, s, edition=False):
    dt = datetime.datetime.fromisoformat(ed["published_at"]).astimezone(CT)
    B.load(ed)
    kick = (f"Daily edition, {len(ed['stories'])} stories" if edition else s["topic"])
    hl_cls = "og-hl sm" if len(s["headline"]) > 72 else "og-hl"
    right = f"{dt.strftime('%b')} {dt.day}, {dt.year}"
    return og_html(
        f'<div class="og-top"><div class="og-brand">{B.LOGO}<span>Receipts</span></div>'
        f'<div class="og-meta"><span>{esc(right)}</span></div></div>'
        f'<div class="og-text"><p class="og-kick">{esc(kick)}</p><h1 class="{hl_cls}">{esc(s["headline"])}</h1></div>'
        f'<div class="og-chart">{B.chart(s, "og-" + s["id"])}</div>'
        f'<div class="og-foot"><div class="l"><span class="og-ev" style="--c:{TIER_DOT[s["tier"]]}"><i></i>{esc(s["evidence"])}</span>'
        f'<span>{len(s["sources"])} sources</span></div><span>{esc(HOST)}</span></div>')


def default_card():
    return og_html(
        f'<div class="og-top"><div class="og-brand">{B.LOGO}<span>Receipts</span></div><div class="og-meta"></div></div>'
        '<div class="og-solo"><h1 class="og-hl">Every number links to its source.</h1>'
        '<p>AI and agent-economy news, every morning.</p></div>'
        f'<div class="og-foot"><div class="l"><span>Free. No ads.</span></div><span>{esc(HOST)}</span></div>')


ICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 28 28"><rect width="28" height="28" rx="{rx}" fill="#002FA7"/>'
        '<path d="M8 9.5h12M8 14h12M8 18.5h7" stroke="#fff" stroke-width="2.4" stroke-linecap="round" fill="none"/></svg>')

jobs = []
for date, ed in EDS:
    age = (TODAY - datetime.date.fromisoformat(date)).days
    folder = OUT / "og" / date
    if age > OG_KEEP_DAYS:
        for f in folder.glob("*.png") if folder.exists() else []:
            f.unlink()
        if folder.exists():
            folder.rmdir()
        (OUT / "og" / f"{date}.png").unlink(missing_ok=True)
        continue
    fresh = date == LATEST
    for s in ed["stories"]:
        p = folder / f"{s['id']}.png"
        if fresh or not p.exists():
            jobs.append((p, og_card(date, ed, s)))
    p = OUT / "og" / f"{date}.png"
    if fresh or not p.exists():
        jobs.append((p, og_card(date, ed, ed["stories"][0], edition=True)))
if not (OUT / "og" / "default.png").exists() or "--all-images" in sys.argv:
    jobs.append((OUT / "og" / "default.png", default_card()))
write("favicon.svg", ICON.replace("{rx}", "7"))
icons = [("icon-32.png", 32, "7"), ("apple-touch-icon.png", 180, "0"), ("icon-192.png", 192, "0"), ("icon-512.png", 512, "0")]

from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as p:
    chrome = pathlib.Path("/usr/bin/google-chrome")
    browser = p.chromium.launch(executable_path=str(chrome)) if chrome.exists() else p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=1)
    for path, doc in jobs:
        path.parent.mkdir(parents=True, exist_ok=True)
        pg.set_content(doc)
        pg.evaluate("document.fonts.ready")
        pg.screenshot(path=str(path), clip={"x": 0, "y": 0, "width": 1200, "height": 630})
    for name, size, rx in icons:
        if (OUT / name).exists() and "--all-images" not in sys.argv:
            continue
        ip = browser.new_page(viewport={"width": size, "height": size}, device_scale_factor=1)
        ip.set_content(f'<html><body style="margin:0;background:transparent">'
                       f'<div style="width:{size}px;height:{size}px">{ICON.replace("{rx}", rx).replace("<svg ", f"<svg width={size} height={size} ")}</div></body></html>')
        ip.screenshot(path=str(OUT / name), omit_background=True)
        ip.close()
    browser.close()

n_pages = sum(1 for _ in OUT.rglob("index.html"))
print(f"Built {SITE}: {len(EDS)} edition(s), {n_pages} pages, {len(jobs)} share image(s) rendered. Latest {LATEST}.")
