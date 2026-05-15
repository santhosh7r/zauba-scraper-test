"""
crawler/discover.py — listing-page crawler
===========================================
Walks the ZaubaCorp *age-A* bucket — the youngest companies the site indexes —
and records every company URL it finds in the local SQLite queue.

Uses listing-specific delays (5–12 s) between page fetches.
"""

import re
import time
import random

from bs4 import BeautifulSoup

from config import AGE_BUCKET, BASE_URL, LISTING_BASE, LISTING_MIN_DELAY, LISTING_MAX_DELAY
from crawler.fetch import fetch_html, is_blocked
from database.db import save_company_url
from utils.logger import log


URL_BLACKLIST = {
    "faq", "privacy-policy", "terms", "contact-us",
    "refunds", "signin", "signup", "companies-list",
    "about", "sitemap", "press", "careers", "blog",
    "advertise", "feedback", "help",
}

# Matches the bucket's "Last" pagination link, e.g.
#   /companies-list/age-A/p-496-company.html
_LAST_PAGE_RE = re.compile(
    rf"{re.escape(AGE_BUCKET)}/p-(\d+)-company", re.IGNORECASE
)


def _is_company_url(href: str) -> bool:
    if not href.startswith(BASE_URL):
        return False
    path = href.replace(BASE_URL, "").strip("/")
    if not path:
        return False
    first_segment = path.split("/")[0].lower()
    if any(bl in first_segment for bl in URL_BLACKLIST):
        return False
    if not any(c.isalpha() for c in path):
        return False
    return True


def listing_url(page: int) -> str:
    """URL of page *page* within the age bucket."""
    if page <= 1:
        return f"{LISTING_BASE}/{AGE_BUCKET}-company.html"
    return f"{LISTING_BASE}/{AGE_BUCKET}/p-{page}-company.html"


def get_total_pages() -> int:
    """Return how many listing pages the age bucket currently has.

    Parses the pagination of page 1. Returns 0 if it cannot be determined
    (e.g. the page was blocked) so the caller can back off and retry."""
    html = fetch_html(listing_url(1), "listing page-count", page_type="listing")
    if not html or is_blocked(html):
        log.error("[Discover] Could not load page 1 to determine total page count.")
        return 0

    pages = [int(m) for m in _LAST_PAGE_RE.findall(html)]
    if not pages:
        # Single-page bucket, or pagination markup changed — treat as 1 page.
        log.warning("[Discover] No pagination found in age bucket; assuming a single page.")
        return 1
    return max(pages)


def crawl_listing_page(page: int) -> list[str]:
    """Fetch one listing page and return the company URLs it contains.

    Every URL is also recorded in the local SQLite queue so we know we've
    seen it. Returns [] on failure — the caller simply moves on."""
    url = listing_url(page)
    log.info("[Discover] Crawling listing page %d → %s", page, url)

    html = fetch_html(url, f"listing p{page}", page_type="listing")
    if not html or is_blocked(html):
        log.error("[Discover] Failed to load listing page %d — 🔒 blocked or empty", page)
        return []

    soup = BeautifulSoup(html, "lxml")

    seen: set[str] = set()
    urls: list[str] = []

    for tag in soup.find_all("a", href=True):
        href: str = tag["href"].strip()
        if href.startswith("/"):
            href = BASE_URL + href
        if href in seen or not _is_company_url(href):
            continue
        seen.add(href)
        try:
            save_company_url(href, page)
        except Exception as exc:
            # A queue write failing must never abort discovery.
            log.warning("[Discover] Could not queue URL %s: %s", href, exc)
        urls.append(href)

    log.info("[Discover] Page %d → %d company URLs found", page, len(urls))
    return urls
