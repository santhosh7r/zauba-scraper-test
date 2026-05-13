from database.db import initialize_database

from crawler.discover import start_discovery

from crawler.detail_scraper import start_scraping

from utils.export_csv import export_companies


def main():

    initialize_database()

    print("[1] Discovering company URLs")

    start_discovery(
        start_page=1,
        end_page=5
    )

    print("[2] Scraping company details")

    start_scraping(limit=100)

    print("[3] Exporting CSV")

    export_companies()

    print("[+] Done")


if __name__ == "__main__":

    main()
