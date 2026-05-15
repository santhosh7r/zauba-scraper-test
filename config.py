import os
import random
from dotenv import load_dotenv

load_dotenv()

# ─── Browser ────────────────────────────────────────────────────────────────
# Never run headless — headless=False makes the browser look like a real user.
HEADLESS = False
SLOW_MO = 80                    # ms between browser actions (subtle, not obvious)
PAGE_TIMEOUT = 120_000          # ms — navigation timeout
PAGE_SETTLE_MS = 6_000          # ms — initial settle wait after a page loads

# Cloudflare's "Just a moment" interstitial: keep polling until it clears.
# Datacenter IPs can be challenged for 30–90 seconds.
CHALLENGE_MAX_WAIT_SECONDS = 120
CHALLENGE_POLL_SECONDS = 4

# Always use real Playwright browser as primary on a VPS.
BROWSER_FIRST = True

# When headful is requested on a host with no DISPLAY (a VPS), start an Xvfb
# virtual display automatically (needs the `xvfb` package + pyvirtualdisplay).
USE_VIRTUAL_DISPLAY = True

# Persistent browser profiles. The first is the warmed-up one; the bot rotates
# to the next when Cloudflare blocks persistently.
PROFILE_DIRS = ["browser_profile", "browser_profile_2", "browser_profile_3"]

# ─── User-Agent Rotation ─────────────────────────────────────────────────────
# Realistic Chrome desktop user agents — rotated per browser session.
USER_AGENTS = [
    # Chrome 124 – Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome 123 – Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    # Chrome 122 – Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    # Chrome 124 – macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome 123 – macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    # Chrome 124 – Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome 122 – macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    # Chrome 121 – Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

def get_random_user_agent() -> str:
    """Return a random realistic Chrome desktop UA string."""
    return random.choice(USER_AGENTS)

# Default UA for httpx fallback (pick one at import time).
USER_AGENT = get_random_user_agent()

# ─── Random Viewport Sizes ───────────────────────────────────────────────────
# Realistic desktop resolutions — randomized per session to vary fingerprint.
VIEWPORT_SIZES = [
    {"width": 1920, "height": 1080},
    {"width": 1680, "height": 1050},
    {"width": 1600, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1280, "height": 800},
    {"width": 1280, "height": 720},
]

def get_random_viewport() -> dict:
    """Return a random realistic desktop viewport."""
    return random.choice(VIEWPORT_SIZES)

# ─── Stealth Browser Launch Arguments ────────────────────────────────────────
BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-infobars",
    "--disable-notifications",
    "--disable-extensions",
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
    "--disable-ipc-flooding-protection",
    "--password-store=basic",
    "--use-mock-keychain",
    # Stability on Linux VPS / headless environments
    "--disable-gpu-sandbox",
    "--disable-software-rasterizer",
]

# ─── Crawling ────────────────────────────────────────────────────────────────
BASE_URL = "https://www.zaubacorp.com"
LISTING_BASE = f"{BASE_URL}/companies-list"

# ZaubaCorp has no public "newest companies" page. Its company list is bucketed
# by age: 'age-A' is the YOUNGEST bucket. We sweep this to always get the
# latest companies first.
AGE_BUCKET = "age-A"

# Human-like delays — listing pages: 5–12s, detail pages: 8–20s
LISTING_MIN_DELAY = 5.0    # seconds between listing page requests
LISTING_MAX_DELAY = 12.0
DETAIL_MIN_DELAY  = 8.0    # seconds between detail page requests
DETAIL_MAX_DELAY  = 20.0

# Legacy aliases used by older code paths
MIN_DELAY = DETAIL_MIN_DELAY
MAX_DELAY = DETAIL_MAX_DELAY

MAX_RETRIES = 5             # retries per URL before giving up
MAX_URL_ATTEMPTS = 5        # abandon a URL after this many total failed sweeps

# Only store companies incorporated in the last 30 days.
ONLY_LAST_30_DAYS = True
STORE_ALL_COMPANIES = False

# Pause between full sweeps of the age bucket.
SWEEP_PAUSE_SECONDS = 1800   # 30 minutes

# ─── Resilience (unattended VPS operation) ───────────────────────────────────
# Base sleep after an unhandled error — doubled on consecutive failures up to cap.
ERROR_BACKOFF_SECONDS = 60
ERROR_BACKOFF_MAX_SECONDS = 1800

# When Cloudflare blocks this many fetches in a row, cool down hard.
CF_COOLDOWN_AFTER_BLOCKS = 5
CF_COOLDOWN_SECONDS = 900    # 15 minutes

# Retry delays with increasing cooldowns (seconds): attempt 1→2→3→4→5
RETRY_DELAYS = [10, 30, 60, 120, 300]

# Browser restart: how many consecutive CF blocks before we restart the browser.
BROWSER_RESTART_AFTER_CF_BLOCKS = 3

# Fall back to real Playwright browser when plain httpx is Cloudflare-blocked.
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
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB per file
LOG_BACKUP_COUNT = 10             # keep 10 rotated files
