"""
crawler/browser_fetch.py — Cloudflare-aware, human-like Playwright fetcher
===========================================================================
A persistent-profile Chromium browser that:
  * always runs with headless=False so it looks like a real desktop browser,
  * uses a persistent profile (browser_profile/) to reuse cookies, localStorage,
    and the Cloudflare cf_clearance cookie across runs,
  * randomises viewport size and User-Agent per session,
  * performs realistic human behaviour: random scrolls, mouse moves,
    randomised typing delays, and waiting for network idle,
  * polls each page until the "Just a moment" Cloudflare challenge clears,
  * retries with exponential back-off and restarts the browser context if
    blocked repeatedly,
  * auto-restarts if the browser process crashes.

This is the primary fetcher on a VPS where plain httpx is always blocked.
"""

import os
import random
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

try:
    from playwright_stealth import Stealth
    _stealth_available = True
except ImportError:
    _stealth_available = False

from config import (
    BASE_URL,
    BROWSER_ARGS,
    BROWSER_RESTART_AFTER_CF_BLOCKS,
    CHALLENGE_MAX_WAIT_SECONDS,
    CHALLENGE_POLL_SECONDS,
    HEADLESS,
    PAGE_SETTLE_MS,
    PAGE_TIMEOUT,
    RETRY_DELAYS,
    SLOW_MO,
    USE_VIRTUAL_DISPLAY,
    get_random_user_agent,
    get_random_viewport,
)
from utils.logger import log

PROFILE_DIR = Path(__file__).parent.parent / "browser_profile"

# A headful browser needs a display. On a screenless VPS we start one virtual
# Xvfb display for the whole process; this holds the reference so it stays up.
_virtual_display = None


def _ensure_display(want_headful: bool) -> bool:
    """Make sure a display exists for a headful browser.

    Returns the *headless* value to actually launch with: False if a real or
    virtual display is available, True if we must fall back to headless."""
    global _virtual_display

    if not want_headful:
        return True  # caller explicitly wants headless

    if os.environ.get("DISPLAY"):
        return False  # a real X display is already available

    if _virtual_display is not None:
        return False  # a virtual display is already running from a prior start

    if not USE_VIRTUAL_DISPLAY:
        log.warning("[Browser] Headful requested but no DISPLAY and "
                    "USE_VIRTUAL_DISPLAY is off — falling back to headless.")
        return True

    try:
        from pyvirtualdisplay import Display
    except ImportError:
        log.warning(
            "[Browser] pyvirtualdisplay not installed — cannot create a "
            "virtual display. Install it:  pip install pyvirtualdisplay  and "
            "the system package:  sudo apt install -y xvfb . "
            "Falling back to headless for now."
        )
        return True

    try:
        _virtual_display = Display(visible=False, size=(1920, 1080))
        _virtual_display.start()
        log.info("[Browser] Started Xvfb virtual display (DISPLAY=%s) — "
                 "running headful Chrome on a screenless host.",
                 os.environ.get("DISPLAY"))
        return False
    except Exception as exc:
        log.warning(
            "[Browser] Could not start an Xvfb virtual display: %s . "
            "Install it with  'sudo apt install -y xvfb'  for true headful "
            "mode. Falling back to headless.", exc,
        )
        _virtual_display = None
        return True

_CF_MARKERS = (
    "just a moment",
    "checking your browser",
    "enable javascript and cookies",
    "performing security verification",
    "challenges.cloudflare.com",
    "cf-chl-widget",
    "cf-challenge",
    "ray id",
)


def _looks_like_challenge(html: str) -> bool:
    """True if *html* is a Cloudflare interstitial rather than real content."""
    if not html:
        return True
    low = html.lower()
    return any(m in low for m in _CF_MARKERS)


def _looks_dead(exc: Exception) -> bool:
    """True if an exception means the browser/context is gone."""
    msg = str(exc).lower()
    return any(m in msg for m in (
        "has been closed", "browser closed", "connection closed",
        "crashed", "disconnected", "target page", "object was collected",
    ))


# ─── Human simulation helpers ─────────────────────────────────────────────────

def _random_sleep(min_s: float, max_s: float):
    """Sleep for a random duration between min_s and max_s seconds."""
    time.sleep(random.uniform(min_s, max_s))


def _human_scroll(page, *, min_scrolls: int = 2, max_scrolls: int = 6):
    """Simulate human-like random scrolling on the current page."""
    try:
        num_scrolls = random.randint(min_scrolls, max_scrolls)
        for _ in range(num_scrolls):
            # Scroll down a random amount
            scroll_y = random.randint(200, 800)
            page.mouse.wheel(0, scroll_y)
            page.wait_for_timeout(random.randint(300, 1200))
        # Occasionally scroll back up a bit
        if random.random() < 0.4:
            page.mouse.wheel(0, -random.randint(100, 400))
            page.wait_for_timeout(random.randint(200, 800))
    except Exception:
        pass


def _human_mouse_move(page, *, num_moves: int | None = None):
    """Simulate random mouse movements across the page."""
    try:
        vp = page.viewport_size or {"width": 1280, "height": 800}
        w, h = vp["width"], vp["height"]
        moves = num_moves if num_moves is not None else random.randint(2, 6)
        for _ in range(moves):
            x = random.randint(int(w * 0.05), int(w * 0.95))
            y = random.randint(int(h * 0.05), int(h * 0.90))
            page.mouse.move(x, y)
            page.wait_for_timeout(random.randint(80, 400))
    except Exception:
        pass


def _wait_network_idle(page, timeout_ms: int = 10_000):
    """Best-effort wait for network idle after navigation."""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception:
        pass  # networkidle may time out on slow pages; that's fine


# ─── BrowserManager ───────────────────────────────────────────────────────────

class BrowserManager:
    """Playwright Chromium using a persistent profile directory.

    The persistent profile keeps cookies (including Cloudflare's cf_clearance),
    localStorage, and browsing history so once a challenge is solved the rest
    of the session reuses it. A new User-Agent and viewport are picked randomly
    each time the browser is (re)started."""

    def __init__(self):
        self._playwright = None
        self._context = None
        self.page = None
        self._started = False
        self._cf_block_count = 0   # consecutive CF blocks — drives browser restart

    # ─── lifecycle ───────────────────────────────────────────────────────────

    def start(self, headless: bool = HEADLESS):
        if self._started:
            return

        viewport = get_random_viewport()
        ua = get_random_user_agent()

        log.info(
            "[Browser] Starting (headless=%s, viewport=%dx%d, profile=%s)",
            headless, viewport["width"], viewport["height"], PROFILE_DIR,
        )
        log.debug("[Browser] User-Agent: %s", ua)

        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()

        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=headless,
            slow_mo=SLOW_MO,
            args=BROWSER_ARGS + [
                f"--window-size={viewport['width']},{viewport['height']}",
            ],
            viewport=viewport,
            user_agent=ua,
            locale="en-US",
            timezone_id="Asia/Kolkata",
            # Extra headers that make the browser look more like a real user
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
            },
        )

        # Patch the most obvious automation fingerprints.
        self._context.add_init_script("""
            // Hide webdriver flag
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            // Restore chrome runtime object (removed in headless)
            window.chrome = { runtime: {} };
            // Fake realistic plugin list
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            // Fake language list
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });
        """)

        if _stealth_available:
            stealth = Stealth()
            for pg in self._context.pages:
                stealth.apply_stealth_sync(pg)
            self._context.on("page", lambda pg: stealth.apply_stealth_sync(pg))
            log.debug("[Browser] playwright-stealth applied")

        self.page = (self._context.pages[0] if self._context.pages
                     else self._context.new_page())
        self._started = True
        self._cf_block_count = 0
        log.info("[Browser] Ready — session reusing profile at %s", PROFILE_DIR)

        self._warm_up()

    def restart(self, rotate_profile: bool = False):
        """Close and reopen the browser, optionally clearing the profile."""
        log.warning("[Browser] Restarting browser context (rotate_profile=%s)", rotate_profile)
        self.close()

        if rotate_profile:
            import shutil
            try:
                shutil.rmtree(PROFILE_DIR, ignore_errors=True)
                PROFILE_DIR.mkdir(parents=True, exist_ok=True)
                log.info("[Browser] Profile rotated — cleared %s", PROFILE_DIR)
            except Exception as exc:
                log.warning("[Browser] Could not rotate profile: %s", exc)

        _random_sleep(3, 8)
        self.start()

    def close(self):
        try:
            if self._context:
                self._context.close()
        except Exception:
            pass
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._context = None
        self._playwright = None
        self.page = None
        self._started = False
        log.info("[Browser] Closed")

    # ─── internals ───────────────────────────────────────────────────────────

    def _warm_up(self):
        """Visit the homepage once so Cloudflare can set a clearance cookie."""
        try:
            log.info("[Browser] Warming up at %s", BASE_URL)
            self.page.goto(BASE_URL, timeout=PAGE_TIMEOUT,
                           wait_until="domcontentloaded")
            _wait_network_idle(self.page, timeout_ms=12_000)
            _human_mouse_move(self.page, num_moves=3)
            _human_scroll(self.page, min_scrolls=1, max_scrolls=3)

            html = self._wait_out_challenge()
            if _looks_like_challenge(html):
                log.warning(
                    "[Browser] Warm-up still shows a CF challenge — "
                    "will keep retrying on each page."
                )
            else:
                log.info("[Browser] Warm-up succeeded — Cloudflare clearance established.")
        except Exception as exc:
            log.warning("[Browser] Warm-up navigation failed: %s", exc)

    def _wait_out_challenge(self) -> str:
        """Poll the current page until the Cloudflare interstitial clears or
        CHALLENGE_MAX_WAIT_SECONDS elapses. Performs human-like activity while
        waiting. Returns the final HTML."""
        deadline = time.time() + CHALLENGE_MAX_WAIT_SECONDS
        self.page.wait_for_timeout(PAGE_SETTLE_MS)

        html = ""
        while True:
            try:
                html = self.page.content()
            except Exception:
                html = ""

            if html and not _looks_like_challenge(html):
                return html
            if time.time() >= deadline:
                return html

            # Human-like activity while the challenge JS runs.
            _human_mouse_move(self.page, num_moves=random.randint(1, 3))
            self.page.wait_for_timeout(CHALLENGE_POLL_SECONDS * 1000)

    # ─── public API ──────────────────────────────────────────────────────────

    def fetch(self, url: str, *, page_type: str = "detail") -> str:
        """Navigate to *url*, wait out any Cloudflare challenge, return HTML.

        *page_type* controls delays: 'listing' uses 5–12 s, 'detail' 8–20 s.
        Returns '' if the page could not be retrieved. Never raises."""
        if not self._started:
            try:
                self.start()
            except Exception as exc:
                log.error("[Browser] Could not start: %s", exc)
                return ""

        log.info("[Browser] → %s", url)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                self.page.goto(url, timeout=PAGE_TIMEOUT,
                               wait_until="domcontentloaded")
                _wait_network_idle(self.page, timeout_ms=10_000)

                # Human activity before reading content
                _human_mouse_move(self.page, num_moves=random.randint(2, 5))
                _human_scroll(self.page, min_scrolls=2, max_scrolls=5)

                html = self._wait_out_challenge()

                if html and not _looks_like_challenge(html):
                    self._cf_block_count = 0
                    log.info("[Browser] ✓ Fetched %s", url)
                    return html

                # Still a challenge page
                self._cf_block_count += 1
                log.warning(
                    "[Browser] 🔒 Cloudflare challenge not cleared — "
                    "%s (attempt %d/%d, block_count=%d)",
                    url, attempt, MAX_RETRIES, self._cf_block_count,
                )

                # Too many consecutive blocks → restart browser (possibly rotate profile)
                if self._cf_block_count >= BROWSER_RESTART_AFTER_CF_BLOCKS:
                    rotate = self._cf_block_count >= BROWSER_RESTART_AFTER_CF_BLOCKS * 2
                    log.warning(
                        "[Browser] 🔄 Restarting browser after %d consecutive CF blocks"
                        " (rotate_profile=%s)",
                        self._cf_block_count, rotate,
                    )
                    self.restart(rotate_profile=rotate)
                    # after restart, loop continues to retry

            except Exception as exc:
                log.error(
                    "[Browser] Navigation error on attempt %d/%d for %s: %s",
                    attempt, MAX_RETRIES, url, exc,
                )
                if _looks_dead(exc):
                    log.warning("[Browser] Browser appears dead — restarting")
                    try:
                        self.restart()
                    except Exception as rexc:
                        log.error("[Browser] Restart failed: %s", rexc)
                        return ""

            # Exponential back-off between retries
            if attempt < MAX_RETRIES:
                delay_idx = min(attempt - 1, len(RETRY_DELAYS) - 1)
                delay = RETRY_DELAYS[delay_idx] + random.uniform(0, 5)
                log.info("[Browser] Waiting %.1fs before retry %d/%d", delay, attempt + 1, MAX_RETRIES)
                time.sleep(delay)

        log.error("[Browser] ✗ Gave up on %s after %d attempts", url, MAX_RETRIES)
        return ""

    def fetch_listing(self, url: str) -> str:
        """Fetch a listing page with listing-appropriate delays (5–12 s)."""
        from config import LISTING_MIN_DELAY, LISTING_MAX_DELAY
        html = self.fetch(url, page_type="listing")
        if html:
            _random_sleep(LISTING_MIN_DELAY, LISTING_MAX_DELAY)
        return html

    def fetch_detail(self, url: str) -> str:
        """Fetch a detail page with detail-appropriate delays (8–20 s)."""
        from config import DETAIL_MIN_DELAY, DETAIL_MAX_DELAY
        html = self.fetch(url, page_type="detail")
        if html:
            _random_sleep(DETAIL_MIN_DELAY, DETAIL_MAX_DELAY)
        return html

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.close()


# Shared singleton — one browser process for the whole bot lifetime.
MAX_RETRIES = 5   # module-level alias used in fetch()
browser_manager = BrowserManager()
