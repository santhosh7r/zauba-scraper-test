"""
crawler/detail_scraper.py — company detail extraction
======================================================
Fetches a company's ZaubaCorp page, extracts structured data (JSON-LD first,
HTML-table fallback), validates it, filters to the last 30 days, and stores
it in Supabase.

Uses detail-appropriate delays (8–20 s) between page fetches.
Retries failed pages up to MAX_RETRIES times with increasing cooldowns.
"""

import json
import random
import hashlib
import time
from datetime import datetime, date, timedelta

from bs4 import BeautifulSoup

from config import DETAIL_MIN_DELAY, DETAIL_MAX_DELAY, MAX_RETRIES, ONLY_LAST_30_DAYS, RETRY_DELAYS
from crawler.fetch import fetch_html, is_blocked
from database.db import mark_stored, mark_failed, url_already_processed
from database.supabase_client import upsert_company_to_supabase
from utils.address_parser import extract_state, extract_city
from utils.logger import log


# ─── Helpers ─────────────────────────────────────────────────────────────────

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


def _extract_labeled_value(soup: BeautifulSoup, label: str) -> str | None:
    """Pull a value from ZaubaCorp's contact block, where fields appear either
    inline as ``<span>Label: value</span>`` or split across two spans as
    ``<span>Label:</span><span>value</span>``."""
    needle = label.lower() + ":"
    for span in soup.find_all("span"):
        text = span.get_text(" ", strip=True)
        if not text.lower().startswith(needle):
            continue
        inline = text[len(label) + 1:].strip()
        if inline:
            return inline
        nxt = span.find_next_sibling("span")
        if nxt:
            return nxt.get_text(" ", strip=True) or None
        return None
    return None


def _generate_hash(data: dict) -> str:
    keys = (
        "cin", "company_name", "status", "roc", "company_type",
        "incorporation_date", "email", "website", "address",
        "authorized_capital", "paid_up_capital",
        "company_category", "company_subcategory",
    )
    payload = json.dumps(
        {k: data.get(k) for k in keys}, sort_keys=True, ensure_ascii=False
    )
    return hashlib.md5(payload.encode()).hexdigest()


_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%d-%b-%Y",
    "%d %B %Y",
    "%d %b %Y",
    "%B %d, %Y",
)


def _parse_date(raw: str | None) -> date | None:
    """Best-effort parse of an incorporation_date string into a date."""
    if not raw:
        return None
    raw = raw.strip()
    if "T" in raw:  # ISO 8601 with a time component
        raw = raw.split("T", 1)[0]
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _is_within_last_30_days(inc_date: date | None) -> bool:
    """Return True if *inc_date* falls within the last 30 calendar days."""
    if inc_date is None:
        return False
    cutoff = date.today() - timedelta(days=30)
    return inc_date >= cutoff


# ─── Parser ───────────────────────────────────────────────────────────────────

def _parse_company_page(html: str, url: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    json_ld = _extract_json_ld(soup)

    cin               = (json_ld.get("identifier") or {}).get("value")
    company_name      = json_ld.get("legalName") or json_ld.get("name")
    email             = json_ld.get("email")
    incorporation_raw = json_ld.get("foundingDate")

    # Address & website live in the page's contact block, not the JSON-LD
    # (whose "url" field just points back to the ZaubaCorp page itself).
    address = json_ld.get("address") or _extract_labeled_value(soup, "Address")
    if isinstance(address, dict):  # JSON-LD PostalAddress object
        address = ", ".join(
            str(v) for v in address.values() if v and isinstance(v, str)
        ) or None
    website = _extract_labeled_value(soup, "Website")
    if website and ("not available" in website.lower()
                    or "zaubacorp.com" in website.lower()):
        website = None

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
        log.warning("[Detail] Could not extract company name from %s", url)
        return None

    if not cin:
        cin = (_extract_table_value(soup, "CIN")
               or _extract_table_value(soup, "LLP Identification Number"))

    if not incorporation_raw:
        incorporation_raw = (
            _extract_table_value(soup, "Date of Incorporation")
            or _extract_table_value(soup, "Incorporation Date")
        )

    inc_date = _parse_date(incorporation_raw)

    status              = _extract_table_value(soup, "Company Status")
    roc                 = (_extract_table_value(soup, "Registrar of Companies")
                            or _extract_table_value(soup, "ROC"))
    company_type        = (_extract_table_value(soup, "Class of Company")
                            or _extract_table_value(soup, "Company Type")
                            or _extract_table_value(soup, "Principal Business"))
    authorized_capital  = (_extract_table_value(soup, "Authorised Share Capital")
                            or _extract_table_value(soup, "Authorized Capital"))
    paid_up_capital     = (_extract_table_value(soup, "Paid-up Share Capital")
                            or _extract_table_value(soup, "Paid up capital")
                            or _extract_table_value(soup, "Paid Up Capital"))
    company_category    = _extract_table_value(soup, "Company Category")
    company_subcategory = (_extract_table_value(soup, "Company Sub Category")
                            or _extract_table_value(soup, "Company Subcategory"))

    state = extract_state(address)
    city  = extract_city(address)

    data = {
        "cin":                 cin,
        "company_name":        company_name,
        "status":              status,
        "roc":                 roc,
        "company_type":        company_type,
        "incorporation_date":  inc_date.isoformat() if inc_date else None,
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
    data["_inc_date_obj"] = inc_date   # keep for 30-day filter (stripped before storage)
    data["content_hash"] = _generate_hash(data)
    return data


def _validate(data: dict) -> bool:
    if not data.get("cin"):
        log.warning("[Detail] Validation failed: CIN missing for %s", data.get("source_url"))
        return False
    if not data.get("company_name"):
        log.warning("[Detail] Validation failed: company_name missing")
        return False
    name = data["company_name"].lower()
    for phrase in ("just a moment", "search results", "cloudflare",
                   "checking your browser"):
        if phrase in name:
            log.warning("[Detail] Validation failed: invalid phrase in company name")
            return False
    return True


# ─── Scraper ─────────────────────────────────────────────────────────────────

def scrape_company(url: str) -> str:
    """Scrape and store a single company URL.

    Returns one of: 'stored', 'failed', 'skipped', 'too_old'.
    Retries up to MAX_RETRIES times with increasing cooldowns."""
    if url_already_processed(url):
        return "skipped"

    log.info("[Detail] Scraping: %s", url)

    html = ""
    for attempt in range(1, MAX_RETRIES + 1):
        html = fetch_html(url, "detail", page_type="detail")
        if html and not is_blocked(html):
            break
        delay_idx = min(attempt - 1, len(RETRY_DELAYS) - 1)
        delay = RETRY_DELAYS[delay_idx] + random.uniform(0, 5)
        log.warning(
            "[Detail] 🔒 Blocked/empty on attempt %d/%d for %s — "
            "retrying in %.1fs",
            attempt, MAX_RETRIES, url, delay,
        )
        if attempt < MAX_RETRIES:
            time.sleep(delay)

    if not html or is_blocked(html):
        log.error("[Detail] ✗ Failed to fetch %s after %d attempts", url, MAX_RETRIES)
        mark_failed(url)
        return "failed"

    data = _parse_company_page(html, url)
    if data is None or not _validate(data):
        log.error("[Detail] Validation failed for %s", url)
        mark_failed(url)
        return "failed"

    # 30-day filter — skip companies incorporated more than 30 days ago.
    if ONLY_LAST_30_DAYS:
        inc_date = data.pop("_inc_date_obj", None)
        if not _is_within_last_30_days(inc_date):
            log.info(
                "[Detail] ⏭  Skipping %s (incorporated %s — older than 30 days)",
                data.get("company_name"), data.get("incorporation_date"),
            )
            # Mark as processed so we don't revisit it every sweep.
            mark_stored(url, data["cin"], data.get("incorporation_date"),
                        data["content_hash"])
            return "too_old"
    else:
        data.pop("_inc_date_obj", None)

    if upsert_company_to_supabase(data):
        mark_stored(url, data["cin"], data["incorporation_date"],
                    data["content_hash"])
        log.info(
            "[Detail] ✓ Stored %s | CIN: %s | inc: %s | %s, %s",
            data["company_name"], data["cin"], data["incorporation_date"],
            data["city"], data["state"],
        )
        return "stored"

    log.warning("[Detail] Failed to sync %s to Supabase — will retry next sweep", url)
    mark_failed(url)
    return "failed"


def scrape_urls(urls: list[str]) -> dict:
    """Scrape a batch of URLs. A failure on one URL never stops the batch.

    Randomised human-like delays (8–20 s) are applied between non-skipped pages;
    the browser_fetch module applies an additional post-fetch delay internally."""
    stats = {"stored": 0, "failed": 0, "skipped": 0, "too_old": 0}

    for i, url in enumerate(urls, start=1):
        try:
            outcome = scrape_company(url)
        except Exception as exc:
            log.error("[Detail] Unhandled error for %s: %s", url, exc)
            try:
                mark_failed(url)
            except Exception:
                pass
            outcome = "failed"

        stats[outcome] = stats.get(outcome, 0) + 1
        log.debug("[Detail] [%d/%d] %s → %s", i, len(urls), url, outcome)

        # Extra inter-request delay for non-skipped pages to pace scraping.
        if outcome not in ("skipped", "too_old"):
            extra = random.uniform(DETAIL_MIN_DELAY, DETAIL_MAX_DELAY)
            log.debug("[Detail] Sleeping %.1fs before next URL", extra)
            time.sleep(extra)

    return stats
