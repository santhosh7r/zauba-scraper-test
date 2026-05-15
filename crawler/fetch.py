"""
crawler/fetch.py — resilient HTML fetcher
=========================================
Single entry point ``fetch_html`` used by both the listing crawler and the
detail scraper.

On a VPS (``BROWSER_FIRST = True``) a real Playwright browser is used as the
primary fetcher, because Cloudflare blocks datacenter IPs and plain httpx
never gets through. On a residential connection httpx is tried first (fast)
and falls back to the browser.

Cloudflare detection is tracked across calls:
  * a consecutive block counter drives a hard cooldown,
  * when the counter exceeds BROWSER_RESTART_AFTER_CF_BLOCKS the browser
    context itself is restarted with a fresh (or rotated) profile.

Every failure mode is handled internally — callers only ever get back a
string (empty on total failure) and never an exception.
"""

import random
import time

import httpx

from config import (
    BROWSER_FIRST,
    CF_COOLDOWN_AFTER_BLOCKS,
    CF_COOLDOWN_SECONDS,
    MAX_RETRIES,
    RETRY_DELAYS,
    USE_BROWSER_FALLBACK,
    get_random_user_agent,
)
from utils.logger import log


def _make_headers() -> dict:
    """Generate realistic browser headers with a rotated User-Agent."""
    ua = get_random_user_agent()
    return {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }


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

# Consecutive Cloudflare blocks across all calls — drives the cooldown.
_consecutive_blocks = 0

# Set once the browser has proven unavailable (e.g. Playwright not installed)
# so we stop retrying it.
_browser_disabled = not USE_BROWSER_FALLBACK


def is_blocked(html: str) -> bool:
    """True if *html* looks like a Cloudflare interstitial rather than content."""
    if not html:
        return False
    lower = html.lower()
    return any(marker in lower for marker in _CF_MARKERS)


def _register_block(label: str, url: str):
    """Record a total failure and cool down hard if blocking is persistent."""
    global _consecutive_blocks
    _consecutive_blocks += 1
    log.error(
        "[Fetch] 🔒 Cloudflare blocked %s: %s  (consecutive=%d)",
        label, url, _consecutive_blocks,
    )
    if _consecutive_blocks >= CF_COOLDOWN_AFTER_BLOCKS:
        log.error(
            "[Fetch] ⏳ Persistent blocking (%d in a row) — "
            "cooling down for %ds before next request",
            _consecutive_blocks, CF_COOLDOWN_SECONDS,
        )
        time.sleep(CF_COOLDOWN_SECONDS)
        _consecutive_blocks = 0


def _httpx_fetch(url: str, label: str) -> str:
    """Fetch via plain httpx with retries. Returns '' on failure / block."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            headers = _make_headers()
            r = httpx.get(
                url,
                headers=headers,
                timeout=httpx.Timeout(60.0, connect=20.0),
                follow_redirects=True,
            )
            html = r.text
            if html and not is_blocked(html):
                log.info("[httpx] ✓ Fetched %s", url)
                return html
            log.warning(
                "[httpx] 🔒 CF block on %s (attempt %d/%d): %s",
                label, attempt, MAX_RETRIES, url,
            )
        except Exception as exc:
            log.warning(
                "[httpx] Error on %s (attempt %d/%d): %s — %s",
                label, attempt, MAX_RETRIES, url, exc,
            )

        if attempt < MAX_RETRIES:
            delay_idx = min(attempt - 1, len(RETRY_DELAYS) - 1)
            delay = RETRY_DELAYS[delay_idx] + random.uniform(0, 5)
            log.info("[httpx] Waiting %.1fs before retry %d/%d", delay, attempt + 1, MAX_RETRIES)
            time.sleep(delay)

    return ""


def _browser_fetch(url: str, page_type: str = "detail") -> str:
    """Fetch via the Playwright browser. Returns '' if unavailable or failed.
    *page_type* is 'listing' or 'detail' — controls post-fetch delay."""
    global _browser_disabled
    if _browser_disabled:
        return ""
    try:
        from crawler.browser_fetch import browser_manager
    except Exception as exc:
        log.warning("[Browser] Playwright not available — browser disabled: %s", exc)
        _browser_disabled = True
        return ""
    try:
        browser_manager.start()
    except Exception as exc:
        log.warning("[Browser] Failed to start — browser disabled: %s", exc)
        _browser_disabled = True
        return ""
    try:
        if page_type == "listing":
            return browser_manager.fetch_listing(url) or ""
        return browser_manager.fetch_detail(url) or ""
    except Exception as exc:
        log.warning("[Browser] Fetch failed for %s: %s", url, exc)
        return ""


def fetch_html(url: str, label: str = "page", page_type: str = "detail") -> str:
    """Fetch *url* and return its HTML, or '' if it could not be retrieved.

    *page_type* controls post-fetch human-like delays:
      'listing' → 5–12 s pause
      'detail'  → 8–20 s pause
    """
    global _consecutive_blocks

    # Primary route: browser first on a VPS, httpx first otherwise.
    if BROWSER_FIRST and not _browser_disabled:
        html = _browser_fetch(url, page_type=page_type)
        if html and not is_blocked(html):
            _consecutive_blocks = 0
            return html
        # If browser is still available it just failed this page — on a
        # datacenter IP httpx would also fail, so skip it. If it became
        # disabled, fall through to httpx.
        if not _browser_disabled:
            _register_block(label, url)
            return ""

    elif not BROWSER_FIRST:
        html = _httpx_fetch(url, label)
        if html:
            _consecutive_blocks = 0
            return html

    # Secondary route (browser was disabled → httpx, or httpx failed → browser)
    if BROWSER_FIRST:
        html = _httpx_fetch(url, label)
        if html:
            _consecutive_blocks = 0
            return html
    else:
        html = _browser_fetch(url, page_type=page_type)
        if html and not is_blocked(html):
            _consecutive_blocks = 0
            return html

    _register_block(label, url)
    return ""
