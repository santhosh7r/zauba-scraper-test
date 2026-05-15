#!/usr/bin/env python3
"""
Zauba Corp Continuous Scraper
=============================
Continuously scrapes the *newest* companies on zaubacorp.com — the ``age-A``
bucket, which is the youngest companies the site indexes — and stores every one
in Supabase (deduplicated by CIN). Downstream, query the data ordered by
``incorporation_date DESC`` to read it newest → oldest.

The bot is built to run unattended on a VPS forever:
  * every error is caught and recovered from with exponential backoff,
  * Cloudflare blocks trigger a cooldown instead of a crash,
  * each sweep walks every listing page; finished URLs are skipped,
  * when a full sweep ends it pauses, then sweeps again to pick up
    newly-added companies.

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
    MAX_DELAY,
    MIN_DELAY,
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


def run_sweep() -> dict:
    """Walk every listing page in the age bucket, scraping each page's URLs.

    A failure on any single page or URL is logged and skipped — the sweep
    keeps going."""
    totals = {"stored": 0, "failed": 0, "skipped": 0, "pages": 0}

    total_pages = get_total_pages()
    if total_pages < 1:
        raise RuntimeError("Could not determine listing page count (site blocked?)")
    log.info("Age bucket currently has %d listing pages", total_pages)

    for page in range(1, total_pages + 1):
        urls = crawl_listing_page(page)
        if not urls:
            log.warning("Listing page %d returned no URLs — skipping.", page)
            continue

        stats = scrape_urls(urls)
        for k, v in stats.items():
            totals[k] = totals.get(k, 0) + v
        totals["pages"] += 1

        log.info(
            "Page %d/%d done — stored:%d failed:%d skipped:%d "
            "| sweep totals stored:%d failed:%d skipped:%d",
            page, total_pages,
            stats["stored"], stats["failed"], stats["skipped"],
            totals["stored"], totals["failed"], totals["skipped"],
        )

        time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

    return totals


def main():
    args = build_parser().parse_args()

    log.info("=" * 60)
    log.info("Zauba Corp continuous scraper starting")
    log.info("=" * 60)

    # The database must exist before anything else; retry until it does.
    while True:
        try:
            initialize_database()
            break
        except Exception as exc:
            log.error("Database init failed: %s — retrying in 30s", exc)
            time.sleep(30)

    sweep = 1
    backoff = ERROR_BACKOFF_SECONDS

    while True:
        try:
            log.info("--- Sweep #%d starting ---", sweep)
            totals = run_sweep()
            qs = queue_stats()
            log.info(
                "Sweep #%d complete — pages:%d stored:%d failed:%d skipped:%d "
                "| queue total:%d synced:%d with-failures:%d",
                sweep,
                totals["pages"], totals["stored"], totals["failed"],
                totals["skipped"],
                qs["total"], qs["synced"], qs["failed"],
            )

            if args.once:
                log.info("--once given — exiting after one sweep.")
                return

            # A clean sweep means recovery worked; reset the backoff.
            backoff = ERROR_BACKOFF_SECONDS
            sweep += 1

            log.info("Pausing %ds before the next sweep...", SWEEP_PAUSE_SECONDS)
            time.sleep(SWEEP_PAUSE_SECONDS)

        except KeyboardInterrupt:
            log.info("Bot stopped manually by user.")
            return

        except Exception as exc:
            # Catch-all: the bot must never die on a VPS. Log, back off, retry.
            log.exception("Unhandled error in sweep #%d: %s", sweep, exc)
            log.info("Recovering automatically — retrying in %ds", backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, ERROR_BACKOFF_MAX_SECONDS)


if __name__ == "__main__":
    main()
