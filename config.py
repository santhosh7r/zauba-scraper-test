import os
from dotenv import load_dotenv

load_dotenv()

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

# ZaubaCorp has no public "newest companies" page. Its company list is bucketed
# by age: 'age-A' is the YOUNGEST bucket — the most recently incorporated
# companies the site indexes. We sweep this bucket so we always scrape the
# latest companies first. Page 1 of the bucket is
#   /companies-list/age-A-company.html
# and subsequent pages are
#   /companies-list/age-A/p-{n}-company.html
AGE_BUCKET = "age-A"

MIN_DELAY = 2.0   # seconds between requests
MAX_DELAY = 5.0   # random jitter upper bound
MAX_RETRIES = 3   # httpx retries per URL before falling back to the browser

# Store every company we scrape (no incorporation-date filtering). The data is
# already the newest bucket; downstream queries order it newest→oldest by
# incorporation_date.
STORE_ALL_COMPANIES = True

# A URL is retried across sweeps until it either succeeds or hits this many
# failed attempts, after which it is abandoned.
MAX_URL_ATTEMPTS = 5

# Pause between full sweeps of the age bucket.
SWEEP_PAUSE_SECONDS = 1800   # 30 minutes

# ─── Resilience (unattended VPS operation) ───────────────────────────────────
# Base sleep after an unhandled error, doubled on each consecutive failure up
# to the cap. Reset once a sweep completes cleanly.
ERROR_BACKOFF_SECONDS = 60
ERROR_BACKOFF_MAX_SECONDS = 1800

# When Cloudflare blocks this many fetches in a row, cool down hard before
# hammering the site again.
CF_COOLDOWN_AFTER_BLOCKS = 8
CF_COOLDOWN_SECONDS = 900    # 15 minutes

# Fall back to a real (Playwright) browser when plain httpx is Cloudflare-blocked.
USE_BROWSER_FALLBACK = True

# ─── Database ────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(
    os.path.dirname(__file__),
    "scraper.db"
)

# ─── Supabase ────────────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# ─── Paths ───────────────────────────────────────────────────────────────────
RAW_HTML_DIR = os.path.join(os.path.dirname(__file__), "raw_html")
EXPORTS_DIR  = os.path.join(os.path.dirname(__file__), "exports")
LOGS_DIR     = os.path.join(os.path.dirname(__file__), "logs")

# ─── Logging ─────────────────────────────────────────────────────────────────
# Rotate the log file so it never fills the VPS disk.
LOG_MAX_BYTES = 5 * 1024 * 1024   # 5 MB per file
LOG_BACKUP_COUNT = 5              # keep 5 rotated files
