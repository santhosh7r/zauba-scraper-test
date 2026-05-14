import time
import json
import random
import hashlib
import httpx

from bs4 import BeautifulSoup

from config import MIN_DELAY, MAX_DELAY, MAX_RETRIES
from database.db import (
    get_unscraped_urls,
    save_company,
    mark_scraped,
    mark_failed,
)
from utils.address_parser import extract_state, extract_city
from utils.logger import log


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _is_blocked(html: str) -> bool:
    """Detect actual Cloudflare Turnstile challenge pages.

    NOTE: Zauba legitimate pages contain 'cloudflare-static/email-decode.min.js'
    so bare 'cloudflare' is a false positive. Use specific CF challenge phrases.
    """
    lower = html.lower()
    return any(k in lower for k in [
        "just a moment",
        "checking your browser",
        "enable javascript and cookies",    # exact CF Turnstile phrase
        "performing security verification",  # CF Managed Challenge phrase
        "challenges.cloudflare.com",         # CF Turnstile script URL
        "cf-chl-widget",                    # CF challenge widget element
    ])


def _extract_json_ld(soup: BeautifulSoup) -> dict:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            continue
    return {}


def _extract_table_value(soup: BeautifulSoup, label: str) -> str | None:
    for row in soup.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 2:
            continue
        key = cols[0].get_text(strip=True)
        if label.lower() in key.lower():
            return cols[1].get_text(strip=True) or None
    return None


def _generate_hash(data: dict) -> str:
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(payload.encode()).hexdigest()


# ─── HTTP fetcher ─────────────────────────────────────────────────────────────

def _fetch(url: str) -> str:
    """Fetch URL with httpx, retry on failure."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = httpx.get(
                url,
                headers=HEADERS,
                timeout=30,
                follow_redirects=True
            )
            html = r.text

            if _is_blocked(html):
                log.warning(
                    "Cloudflare block on attempt %d/%d for %s",
                    attempt, MAX_RETRIES, url
                )
                if attempt < MAX_RETRIES:
                    time.sleep(5 * attempt + random.uniform(0, 3))
                continue

            return html

        except Exception as exc:
            log.warning("HTTP error attempt %d/%d for %s: %s", attempt, MAX_RETRIES, url, exc)
            if attempt < MAX_RETRIES:
                time.sleep(3 * attempt)

    return ""


# ─── Parser ───────────────────────────────────────────────────────────────────

def _parse_company_page(html: str, url: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    json_ld = _extract_json_ld(soup)

    cin              = (json_ld.get("identifier") or {}).get("value")
    company_name     = json_ld.get("legalName") or json_ld.get("name")
    email            = json_ld.get("email")
    address          = json_ld.get("address")
    website          = json_ld.get("url")
    incorporation_date = json_ld.get("foundingDate")

    if not company_name:
        title_tag = soup.find("title")
        if title_tag:
            company_name = (
                title_tag.text
                .replace("| ZaubaCorp", "")
                .replace("| Zauba Corp", "")
                .strip()
            )

    if not company_name or "just a moment" in company_name.lower():
        log.warning("Could not extract company name from %s", url)
        return None

    status              = _extract_table_value(soup, "Company Status")
    roc                 = (_extract_table_value(soup, "Registrar of Companies") or
                           _extract_table_value(soup, "ROC"))
    company_type        = (_extract_table_value(soup, "Company Type") or
                           _extract_table_value(soup, "Principal Business"))
    authorized_capital  = _extract_table_value(soup, "Authorized Capital")
    paid_up_capital     = (_extract_table_value(soup, "Paid up capital") or
                           _extract_table_value(soup, "Paid Up Capital"))
    company_category    = _extract_table_value(soup, "Company Category")
    company_subcategory = (_extract_table_value(soup, "Company Sub Category") or
                           _extract_table_value(soup, "Company Subcategory"))

    state = extract_state(address)
    city  = extract_city(address)

    data = {
        "cin":                 cin,
        "company_name":        company_name,
        "status":              status,
        "roc":                 roc,
        "company_type":        company_type,
        "incorporation_date":  incorporation_date,
        "email":               email,
        "website":             website,
        "address":             address,
        "state":               state,
        "city":                city,
        "authorized_capital":  authorized_capital,
        "paid_up_capital":     paid_up_capital,
        "company_category":    company_category,
        "company_subcategory": company_subcategory,
        "source_url":          url,
    }
    data["content_hash"] = _generate_hash(data)
    return data


# ─── Scraper ─────────────────────────────────────────────────────────────────

def scrape_company(url: str) -> bool:
    log.info("Scraping: %s", url)

    html = _fetch(url)

    if not html:
        log.error("Failed to fetch %s", url)
        mark_failed(url)
        return False

    if _is_blocked(html):
        log.error("Permanently blocked for %s", url)
        mark_failed(url)
        return False

    data = _parse_company_page(html, url)

    if data is None:
        mark_failed(url)
        return False

    save_company(data)
    mark_scraped(url)

    log.info(
        "✓ %s | CIN: %s | %s, %s",
        data["company_name"], data["cin"], data["city"], data["state"]
    )
    return True


def start_scraping(limit: int = 100) -> dict:
    urls = get_unscraped_urls(limit)

    if not urls:
        log.info("No unscraped URLs in database")
        return {"total": 0, "success": 0, "failed": 0}

    log.info("Starting scraping — %d URLs queued", len(urls))
    success = failed = 0

    for i, url in enumerate(urls, start=1):
        log.info("[%d/%d]", i, len(urls))
        try:
            ok = scrape_company(url)
            if ok:
                success += 1
            else:
                failed += 1
        except Exception as exc:
            log.error("Unhandled error for %s: %s", url, exc)
            mark_failed(url)
            failed += 1

        delay = random.uniform(MIN_DELAY, MAX_DELAY)
        time.sleep(delay)

    stats = {"total": len(urls), "success": success, "failed": failed}
    log.info(
        "Done — total: %d | success: %d | failed: %d",
        stats["total"], stats["success"], stats["failed"]
    )
    return stats