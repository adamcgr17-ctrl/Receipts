"""Headless check of Receipts.

Usage:
  python3 tools/check.py docs [outdir]          check the whole website (served locally at its real path)
  python3 tools/check.py index.html [outdir]    check one self-contained page

Fails (exit 1) on console errors, sideways scrolling, a story that will not open, a story
link that does not open its story, broken feeds, or a missing share image. Writes screenshots,
plus charts.png (every story chart in one image, for spotting label collisions) and
lead-chart.png (the top story's chart, for social posts).
"""
import functools
import http.server
import json
import os
import pathlib
import sys
import tempfile
import threading
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

from PIL import Image
from playwright.sync_api import sync_playwright

target = pathlib.Path(sys.argv[1]).resolve()
out = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "shots")
out.mkdir(parents=True, exist_ok=True)
problems = []
site = target.is_dir()

if site:
    cfg = json.loads((target.parent / "site.json").read_text())
    domain = cfg.get("domain") or ((target / "CNAME").read_text().strip() if (target / "CNAME").exists() else "")
    sp = "/" if domain else (urlparse(cfg["site_url"]).path or "/")
    tmp = pathlib.Path(tempfile.mkdtemp())
    if sp == "/":
        root_dir = target
    else:
        root_dir = tmp
        (tmp / sp.strip("/")).parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target, tmp / sp.strip("/"))
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    handler = functools.partial(Quiet, directory=str(root_dir))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    origin = f"http://127.0.0.1:{httpd.server_address[1]}"
    home = origin + sp
    ed = json.loads((target / "edition.json").read_text())
    date = ed["date"]
    ids = [s["id"] for s in ed["stories"]]
    for s in ids:
        if not (target / "og" / date / f"{s}.png").exists():
            problems.append(f"missing share image og/{date}/{s}.png")
    try:
        ET.parse(target / "feed.xml")
        json.loads((target / "feed.json").read_text())
    except Exception as ex:  # noqa: BLE001
        problems.append(f"feed does not parse: {ex}")
else:
    home = target.as_uri()


def watch(pg, errs):
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))


def sheet_open(pg):
    return pg.evaluate("document.getElementById('sheet').getAttribute('aria-hidden')") == "false"


with sync_playwright() as p:
    chrome = pathlib.Path("/usr/bin/google-chrome")
    browser = p.chromium.launch(executable_path=str(chrome)) if chrome.exists() else p.chromium.launch()
    for name, vw, vh in [("mobile", 390, 844), ("desktop", 1280, 800)]:
        for scheme in ["light", "dark"]:
            tag = f"{name}/{scheme}"
            ctx = browser.new_context(viewport={"width": vw, "height": vh}, device_scale_factor=2, color_scheme=scheme)
            pg = ctx.new_page()
            errs = []
            watch(pg, errs)
            pg.goto(home)
            pg.wait_for_timeout(500)
            sw = pg.evaluate("document.documentElement.scrollWidth")
            if sw > vw:
                problems.append(f"{tag}: front page is {sw}px wide in a {vw}px window (sideways scroll)")
            pg.screenshot(path=str(out / f"{name}-{scheme}-front.png"))
            ids_here = pg.evaluate("Array.from(document.querySelectorAll('template[id^=\"tpl-\"]')).map(t => t.id.slice(4))")
            figs = []
            for sid in ids_here:
                pg.evaluate(f"location.hash = '#{sid}'")
                pg.wait_for_timeout(420)
                if not sheet_open(pg):
                    problems.append(f"{tag}: story '{sid}' did not open")
                    continue
                extra = pg.evaluate("document.getElementById('sheet').scrollWidth - document.getElementById('sheet').clientWidth")
                if extra > 1:
                    problems.append(f"{tag}: story '{sid}' sheet scrolls sideways by {extra}px")
                if name == "mobile" and scheme == "light":
                    f = out / f"fig-{sid}.png"
                    pg.locator("#sheet .s-fig").first.screenshot(path=str(f))
                    figs.append(f)
            if site and ids_here:
                pg.goto(home)
                pg.wait_for_timeout(300)
                pg.locator(f'a.card[data-story="{ids_here[1]}"]').first.click()
                pg.wait_for_timeout(450)
                want = f"{urlparse(home).path}e/{date}/{ids_here[1]}/"
                if not sheet_open(pg) or urlparse(pg.url).path != want:
                    problems.append(f"{tag}: tapping a card did not open its story at {want} (got {pg.url})")
                pg.go_back()
                pg.wait_for_timeout(400)
                if sheet_open(pg):
                    problems.append(f"{tag}: Back did not close the story")
            pg.goto(home + "#brief")
            pg.wait_for_timeout(500)
            if name == "mobile":
                pg.screenshot(path=str(out / f"{name}-{scheme}-brief.png"))
            if site:
                for path in [f"e/{date}/{ids[0]}/", "archive/", "about/", "404.html"]:
                    pg.goto(home + path)
                    pg.wait_for_timeout(400)
                    sw = pg.evaluate("document.documentElement.scrollWidth")
                    if sw > vw:
                        problems.append(f"{tag}: {path} is {sw}px wide (sideways scroll)")
                    if path.startswith("e/") and not sheet_open(pg):
                        problems.append(f"{tag}: story link {path} did not open its story")
                    if name == "mobile" and scheme == "light":
                        shot = path.strip("/").replace("/", "-").replace(".html", "") or "home"
                        pg.screenshot(path=str(out / f"page-{shot}.png"))
            problems += [f"{tag}: console error: {e}" for e in errs]
            ctx.close()
            if figs:
                ims = [Image.open(f) for f in figs]
                w, cols = max(i.width for i in ims), 2
                rows = (len(ims) + cols - 1) // cols
                hs = [max(i.height for i in ims[r * cols:(r + 1) * cols]) for r in range(rows)]
                grid = Image.new("RGB", (w * cols + 24 * (cols + 1), sum(hs) + 24 * (rows + 1)), "white")
                y = 24
                for r in range(rows):
                    for c, im in enumerate(ims[r * cols:(r + 1) * cols]):
                        grid.paste(im, (24 + c * (w + 24), y))
                    y += hs[r] + 24
                grid.save(out / "charts.png")
                figs[0].replace(out / "lead-chart.png")
                for f in figs[1:]:
                    f.unlink()
    browser.close()

print(json.dumps({"problems": problems, "screenshots": sorted(x.name for x in out.glob("*.png"))}, indent=1))
sys.exit(1 if problems else 0)
