#!/usr/bin/env python3
"""
Zauba Corp Scraper Bot
======================
Scrapes Indian company data from zaubacorp.com using plain HTTP (httpx).
No browser needed — the site is accessible without Playwright.

Usage examples:
  # Full run (discover + scrape + export)
  python bot.py

  # Discover only (pages 1-20)
  python bot.py --discover --start-page 1 --end-page 20

  # Scrape already-discovered URLs (up to 500)
  python bot.py --scrape --limit 500

  # Export DB to CSV only
  python bot.py --export

  # Scrape a single URL for testing
  python bot.py --test-url https://www.zaubacorp.com/PACIFIC-INFRABUILD-LLP-AAE-6126
"""

import argparse
import sys

from database.db import initialize_database
from crawler.discover import start_discovery
from crawler.detail_scraper import scrape_company, start_scraping
from utils.export_csv import export_companies
from utils.logger import log


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bot.py",
        description="Zauba Corp company data scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    mode = p.add_argument_group("Mode (default: run all steps)")
    mode.add_argument("--discover", action="store_true",
                      help="Only run the URL discovery phase")
    mode.add_argument("--scrape", action="store_true",
                      help="Only run the detail scraping phase")
    mode.add_argument("--export", action="store_true",
                      help="Only export the DB to CSV")
    mode.add_argument("--test-url", metavar="URL",
                      help="Scrape a single URL and print results (for testing)")

    disc = p.add_argument_group("Discovery options")
    disc.add_argument("--start-page", type=int, default=1,
                      help="First listing page to crawl (default: 1)")
    disc.add_argument("--end-page", type=int, default=5,
                      help="Last listing page to crawl (default: 5)")

    scrp = p.add_argument_group("Scraping options")
    scrp.add_argument("--limit", type=int, default=100,
                      help="Max companies to scrape per run (default: 100)")

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("Zauba Corp Scraper Bot — starting")
    log.info("=" * 60)

    initialize_database()

    # ── Single URL test ───────────────────────────────────────────
    if args.test_url:
        log.info("Test mode: scraping single URL")
        ok = scrape_company(args.test_url)
        if ok:
            log.info("Test scrape succeeded")
        else:
            log.error("Test scrape failed")
            sys.exit(1)
        return

    run_all     = not (args.discover or args.scrape or args.export)
    run_discover = run_all or args.discover
    run_scrape   = run_all or args.scrape
    run_export   = run_all or args.export

    # ── Phase 1: Discovery ────────────────────────────────────────
    if run_discover:
        log.info("Phase 1: Discovering URLs (pages %d–%d)",
                 args.start_page, args.end_page)
        total = start_discovery(start_page=args.start_page, end_page=args.end_page)
        log.info("Discovery complete — %d URLs found", total)

    # ── Phase 2: Scraping ─────────────────────────────────────────
    if run_scrape:
        log.info("Phase 2: Scraping company details (limit=%d)", args.limit)
        stats = start_scraping(limit=args.limit)
        log.info(
            "Scraping complete — success: %d | failed: %d | total: %d",
            stats["success"], stats["failed"], stats["total"]
        )

    # ── Phase 3: Export ───────────────────────────────────────────
    if run_export:
        log.info("Phase 3: Exporting to CSV")
        csv_path = export_companies()
        log.info("Saved → %s", csv_path)

    log.info("=" * 60)
    log.info("Bot finished. Check exports/ for CSV and logs/ for full log.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
