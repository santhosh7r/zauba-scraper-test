#!/usr/bin/env python3
"""
bot.py — Zauba Corp Continuous Scraper
=======================================
Continuously scrapes the *newest* companies on zaubacorp.com — the ``age-A``
bucket, which is the youngest companies the site indexes — and stores only
those incorporated within the last 30 days in Supabase (deduplicated by CIN).

The bot is built to run unattended on a VPS forever:
  * every error is caught and recovered from with exponential backoff,
  * Cloudflare blocks trigger a cooldown instead of a crash,
  * automatic browser session recovery if the browser crashes or gets blocked,
  * each sweep walks every listing page; finished URLs are skipped,
  * between sweeps it pauses, then sweeps again to pick up newly-added companies,
  * all Cloudflare detections, retries, restarts, and page outcomes are logged.

Usage:
  python bot.py            # run forever (default)
  python bot.py --once     # run a single sweep, then exit (for testing)
"""

import argparse
import random
import time

from config import (
    ERROR_BACKOFF_MAX_SECONDS,
    ERROR_BACKOFF_SECONDS,
    LISTING_MAX_DELAY,
    LISTING_MIN_DELAY,
    ONLY_LAST_30_DAYS,
    SWEEP_PAUSE_SECONDS,
)
from crawler.discover import crawl_listing_page, get_total_pages
from crawler.detail_scraper import scrape_urls
from database.db import initialize_database, queue_stats
from utils.logger import log


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bot.py",
        description="Zauba Corp continuous latest-company scraper",
    )
    p.add_argument(
        "--once", action="store_true",
        help="Run a single sweep and exit (default: run forever)",
    )
    return p


def _log_sweep_header(sweep: int):
    log.info("=" * 68)
    log.info("  Sweep #%d starting  (last-30-days filter: %s)", sweep, ONLY_LAST_30_DAYS)
    log.info("=" * 68)


def run_sweep() -> dict:
    """Walk every listing page in the age bucket, scraping each page's URLs.

    A failure on any single page or URL is logged and skipped — the sweep
    keeps going. Returns aggregate stats for the whole sweep."""
    totals = {"stored": 0, "failed": 0, "skipped": 0, "too_old": 0, "pages": 0}

    total_pages = get_total_pages()
    if total_pages < 1:
        raise RuntimeError("Could not determine listing page count (site blocked?)")
    log.info("[Bot] Age bucket has %d listing pages", total_pages)

    for page in range(1, total_pages + 1):
        try:
            urls = crawl_listing_page(page)
        except Exception as exc:
            log.error("[Bot] Error crawling listing page %d: %s", page, exc)
            urls = []

        if not urls:
            log.warning("[Bot] Listing page %d returned no URLs — skipping.", page)
        else:
            try:
                stats = scrape_urls(urls)
            except Exception as exc:
                log.error("[Bot] Error scraping URLs from page %d: %s", page, exc)
                stats = {"stored": 0, "failed": len(urls), "skipped": 0, "too_old": 0}

            for k, v in stats.items():
                totals[k] = totals.get(k, 0) + v
            totals["pages"] += 1

            log.info(
                "[Bot] Page %d/%d done — "
                "stored:%d failed:%d skipped:%d too_old:%d"
                " | sweep totals stored:%d failed:%d skipped:%d too_old:%d",
                page, total_pages,
                stats.get("stored", 0), stats.get("failed", 0),
                stats.get("skipped", 0), stats.get("too_old", 0),
                totals["stored"], totals["failed"],
                totals["skipped"], totals["too_old"],
            )

        # Human-like delay between listing pages (5–12 s).
        inter_page_delay = random.uniform(LISTING_MIN_DELAY, LISTING_MAX_DELAY)
        log.debug("[Bot] Sleeping %.1fs before next listing page", inter_page_delay)
        time.sleep(inter_page_delay)

    return totals


def _try_recover_browser():
    """Best-effort browser session recovery without crashing the sweep."""
    try:
        from crawler.browser_fetch import browser_manager
        if browser_manager._started:
            log.warning("[Bot] 🔄 Attempting browser session recovery...")
            browser_manager.restart()
            log.info("[Bot] ✓ Browser session recovered")
    except Exception as exc:
        log.warning("[Bot] Browser recovery attempt failed (non-fatal): %s", exc)


def main():
    args = build_parser().parse_args()

    log.info("=" * 68)
    log.info("  Zauba Corp Continuous Scraper — VPS Human-Mode")
    log.info("  headless=False | persistent profile | 30-day filter=%s", ONLY_LAST_30_DAYS)
    log.info("=" * 68)

    # The database must exist before anything else; retry until it does.
    while True:
        try:
            initialize_database()
            break
        except Exception as exc:
            log.error("[Bot] Database init failed: %s — retrying in 30s", exc)
            time.sleep(30)

    sweep = 1
    backoff = ERROR_BACKOFF_SECONDS
    consecutive_errors = 0

    while True:
        try:
            _log_sweep_header(sweep)
            totals = run_sweep()
            qs = queue_stats()
            log.info(
                "[Bot] ✓ Sweep #%d complete — pages:%d stored:%d failed:%d "
                "skipped:%d too_old:%d | queue total:%d synced:%d with-failures:%d",
                sweep,
                totals["pages"], totals["stored"], totals["failed"],
                totals["skipped"], totals.get("too_old", 0),
                qs["total"], qs["synced"], qs["failed"],
            )

            if args.once:
                log.info("[Bot] --once given — exiting after one sweep.")
                return

            # A clean sweep means recovery worked; reset error tracking.
            backoff = ERROR_BACKOFF_SECONDS
            consecutive_errors = 0
            sweep += 1

            log.info(
                "[Bot] Pausing %ds (%dm) before the next sweep...",
                SWEEP_PAUSE_SECONDS, SWEEP_PAUSE_SECONDS // 60,
            )
            time.sleep(SWEEP_PAUSE_SECONDS)

        except KeyboardInterrupt:
            log.info("[Bot] Stopped manually by user.")
            return

        except Exception as exc:
            consecutive_errors += 1
            # Catch-all: the bot must never die on a VPS.
            log.exception(
                "[Bot] ❌ Unhandled error in sweep #%d (consecutive=%d): %s",
                sweep, consecutive_errors, exc,
            )

            # After a few consecutive failures, try to recover the browser.
            if consecutive_errors >= 2:
                _try_recover_browser()

            log.info("[Bot] 🔁 Auto-recovering — retrying in %ds", backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, ERROR_BACKOFF_MAX_SECONDS)


if __name__ == "__main__":
    main()
