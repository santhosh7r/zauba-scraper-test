import time
import random
import httpx

from bs4 import BeautifulSoup

from config import (
    BASE_URL,
    LISTING_BASE,
    LISTING_PAGE_TEMPLATE,
    MIN_DELAY,
    MAX_DELAY,
    MAX_RETRIES,
)
from database.db import save_company_url
from utils.logger import log


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
}

URL_BLACKLIST = {
    "faq", "privacy-policy", "terms", "contact-us",
    "refunds", "signin", "signup", "companies-list",
    "about", "sitemap", "press", "careers", "blog",
    "advertise", "feedback", "help",
}


def _is_blocked(html: str) -> bool:
    """Detect actual Cloudflare Turnstile challenge pages.

    NOTE: Zauba legitimate pages contain 'cloudflare-static/email-decode.min.js'
    so bare 'cloudflare' is a false positive. Use specific CF challenge phrases.
    """
    lower = html.lower()
    return any(k in lower for k in [
        "just a moment",
        "checking your browser",
        "enable javascript and cookies",
        "performing security verification",
        "challenges.cloudflare.com",
        "cf-chl-widget",
    ])


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


def _get_listing_url(page: int) -> str:
    if page == 1:
        return LISTING_BASE
    return LISTING_PAGE_TEMPLATE.format(page=page)


def crawl_listing_page(page: int) -> int:
    url = _get_listing_url(page)
    log.info("Crawling listing page %d → %s", page, url)

    html = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = httpx.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
            html = r.text
            if not _is_blocked(html):
                break
            log.warning("CF block on listing page %d, attempt %d/%d", page, attempt, MAX_RETRIES)
            time.sleep(5 * attempt)
        except Exception as exc:
            log.warning("HTTP error listing page %d attempt %d: %s", page, attempt, exc)
            time.sleep(3 * attempt)

    if not html or _is_blocked(html):
        log.error("Failed to load listing page %d", page)
        return 0

    soup = BeautifulSoup(html, "lxml")
    links = soup.find_all("a", href=True)
    log.debug("Found %d total links on page %d", len(links), page)

    seen: set[str] = set()
    discovered = 0

    for tag in links:
        href: str = tag["href"].strip()
        if href.startswith("/"):
            href = BASE_URL + href
        if href in seen or not _is_company_url(href):
            continue
        seen.add(href)
        save_company_url(href, page)
        log.debug("  [URL] %s", href)
        discovered += 1

    log.info("Page %d → discovered %d company URLs", page, discovered)
    return discovered


def start_discovery(start_page: int = 1, end_page: int = 5) -> int:
    total = 0
    for page in range(start_page, end_page + 1):
        try:
            count = crawl_listing_page(page)
            total += count
        except Exception as exc:
            log.error("Error on listing page %d: %s", page, exc)

        delay = random.uniform(MIN_DELAY, MAX_DELAY)
        log.debug("Sleeping %.1fs", delay)
        time.sleep(delay)

    log.info("Discovery complete — %d URLs found", total)
    return total