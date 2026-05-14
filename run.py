"""
run.py — legacy entry point (kept for backward compatibility).
Use bot.py for the full CLI experience.
"""
from database.db import initialize_database
from crawler.browser_fetch import browser_manager
from crawler.discover import start_discovery
from crawler.detail_scraper import start_scraping
from utils.export_csv import export_companies
from utils.logger import log


def main():
    initialize_database()

    log.info("[1] Discovering company URLs (pages 1–5)")
    browser_manager.start(headless=True)
    try:
        start_discovery(start_page=1, end_page=5)

        log.info("[2] Scraping company details (limit=100)")
        start_scraping(limit=100)
    finally:
        browser_manager.close()

    log.info("[3] Exporting CSV")
    export_companies()

    log.info("[+] Done")


if __name__ == "__main__":
    main()
