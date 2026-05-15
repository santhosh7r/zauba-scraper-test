"""
crawler/fetch.py — resilient HTML fetcher
=========================================
A single entry point, ``fetch_html``, used by both the listing crawler and the
detail scraper. It tries plain ``httpx`` first and, when Cloudflare blocks the
request, transparently falls back to a real Playwright browser. Every failure
mode is handled internally so callers only ever get back a string (empty on
total failure) and never an exception.
"""

import random
import time

import httpx

from config import (
    CF_COOLDOWN_AFTER_BLOCKS,
    CF_COOLDOWN_SECONDS,
    MAX_RETRIES,
    USER_AGENT,
    USE_BROWSER_FALLBACK,
)
from utils.logger import log


HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

_CF_MARKERS = (
    "just a moment",
    "checking your browser",
    "enable javascript and cookies",
    "performing security verification",
    "challenges.cloudflare.com",
    "cf-chl-widget",
)

# Number of consecutive Cloudflare blocks seen across all calls. When it gets
# high we assume the site has clamped down and cool off for a long while.
_consecutive_blocks = 0

# Set once the browser fallback has proven unavailable, so we stop retrying it.
_browser_disabled = not USE_BROWSER_FALLBACK


def is_blocked(html: str) -> bool:
    """True if *html* looks like a Cloudflare interstitial rather than content."""
    if not html:
        return False
    lower = html.lower()
    return any(marker in lower for marker in _CF_MARKERS)


def _browser_fetch(url: str) -> str:
    """Best-effort fetch through Playwright. Returns '' if the browser is
    unavailable or fails — never raises."""
    global _browser_disabled
    if _browser_disabled:
        return ""
    try:
        from crawler.browser_fetch import browser_manager
        browser_manager.start()
        html = browser_manager.fetch(url)
        return html or ""
    except Exception as exc:
        log.warning("Browser fallback unavailable — disabling it: %s", exc)
        _browser_disabled = True
        return ""


def fetch_html(url: str, label: str = "page") -> str:
    """Fetch *url* and return its HTML, or '' if it could not be retrieved.

    Strategy: httpx with retries → Playwright browser fallback → give up.
    Cloudflare interstitials count as failures. Persistent blocking triggers a
    long cooldown so we never hammer the site."""
    global _consecutive_blocks

    blocked_seen = False

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = httpx.get(
                url,
                headers=HEADERS,
                timeout=httpx.Timeout(45.0, connect=15.0),
                follow_redirects=True,
            )
            html = r.text
            if html and not is_blocked(html):
                _consecutive_blocks = 0
                return html
            blocked_seen = True
            log.warning(
                "Cloudflare block on %s (attempt %d/%d): %s",
                label, attempt, MAX_RETRIES, url,
            )
        except Exception as exc:
            log.warning(
                "HTTP error on %s (attempt %d/%d): %s — %s",
                label, attempt, MAX_RETRIES, url, exc,
            )
        if attempt < MAX_RETRIES:
            time.sleep(3 * attempt + random.uniform(0, 3))

    # httpx exhausted — try a real browser.
    html = _browser_fetch(url)
    if html and not is_blocked(html):
        _consecutive_blocks = 0
        return html
    if is_blocked(html):
        blocked_seen = True

    if blocked_seen:
        _consecutive_blocks += 1
        if _consecutive_blocks >= CF_COOLDOWN_AFTER_BLOCKS:
            log.error(
                "Cloudflare blocking persistently (%d in a row) — cooling down %ds",
                _consecutive_blocks, CF_COOLDOWN_SECONDS,
            )
            time.sleep(CF_COOLDOWN_SECONDS)
            _consecutive_blocks = 0

    log.error("Giving up on %s after all attempts: %s", label, url)
    return ""
