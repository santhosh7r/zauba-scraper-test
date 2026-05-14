import os

# ─── Browser ────────────────────────────────────────────────────────────────
HEADLESS = True
SLOW_MO = 200                   # ms between browser actions
PAGE_TIMEOUT = 90_000           # ms
PAGE_WAIT_AFTER_LOAD = 15_000   # ms — enough for CF Turnstile to auto-resolve

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ─── Crawling ────────────────────────────────────────────────────────────────
BASE_URL = "https://www.zaubacorp.com"
LISTING_BASE = f"{BASE_URL}/companies-list"
LISTING_PAGE_TEMPLATE = f"{BASE_URL}/companies-list/p-{{page}}-company.html"

MIN_DELAY = 2.0   # seconds between requests
MAX_DELAY = 5.0   # random jitter upper bound
MAX_RETRIES = 3   # retries per URL on failure

# ─── Database ────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(
    os.path.dirname(__file__),
    "scraper.db"
)

# ─── Paths ───────────────────────────────────────────────────────────────────
RAW_HTML_DIR = os.path.join(os.path.dirname(__file__), "raw_html")
EXPORTS_DIR  = os.path.join(os.path.dirname(__file__), "exports")
LOGS_DIR     = os.path.join(os.path.dirname(__file__), "logs")
