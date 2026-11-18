# Receipts

A daily news page on the agentic economy and frontier AI. Every number links to the filing, company post, report or dataset it came from, and every story carries a confidence label.

Each morning an AI agent (Claude, made by Anthropic) researches the news, writes `data/editions/YYYY-MM-DD.json`, builds the site into `docs/`, checks it in a headless browser and pushes. GitHub Pages serves `docs/`.

- `data/editions/` one JSON file per edition; the newest is today's
- `site.json` site address and reader channels (inbox, X, newsletter)
- `tools/build.py` renders one edition page; `validate()` is the data contract
- `tools/site.py` builds the whole site: edition and story pages, share images, archive, about, RSS and JSON feeds, llms.txt, sitemap
- `tools/check.py` headless checks at phone and desktop sizes, light and dark

Build locally: `pip install playwright pillow && python3 tools/site.py && python3 tools/check.py docs`
