import time
import httpx

from bs4 import BeautifulSoup

from database.db import DB, cursor


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64)"
    )
}


def get_page_url(page):

    if page == 1:

        return (
            "https://www.zaubacorp.com/"
            "companies-list"
        )

    return (
        "https://www.zaubacorp.com/"
        f"companies-list/p-{page}-company.html"
    )


def save_company_url(url, page):

    try:

        cursor.execute(
            """
            INSERT INTO company_urls(
                url,
                page_number
            )
            VALUES(?, ?)
            """,
            (url, page)
        )

        DB.commit()

    except Exception:
        pass


def crawl_listing_page(page):

    url = get_page_url(page)

    print(f"\n[+] Crawling page {page}")
    print(f"[+] URL: {url}")

    response = httpx.get(
        url,
        headers=HEADERS,
        timeout=60,
        follow_redirects=True
    )

    print(f"[+] Status Code: {response.status_code}")

    with open(
        f"raw_html/page_{page}.html",
        "w",
        encoding="utf-8"
    ) as f:

        f.write(response.text)

    soup = BeautifulSoup(
        response.text,
        "lxml"
    )

    links = soup.find_all("a")

    print(f"[+] Total links found: {len(links)}")

    discovered = 0

    seen = set()

    blacklist = [
        "faq",
        "privacy-policy",
        "terms",
        "contact-us",
        "refunds",
        "signin",
        "signup",
        "companies-list"
    ]

    for link in links:

        href = link.get("href")

        if not href:
            continue

        if not href.startswith(
            "https://www.zaubacorp.com/"
        ):
            continue

        if any(
            x in href
            for x in blacklist
        ):
            continue

        if href in seen:
            continue

        seen.add(href)

        print(href)

        save_company_url(
            href,
            page
        )

        discovered += 1

    print(
        f"[+] Discovered {discovered} company URLs"
    )


def start_discovery(start_page=1, end_page=5):

    for page in range(
        start_page,
        end_page + 1
    ):

        try:

            crawl_listing_page(page)

            time.sleep(3)

        except Exception as e:

            print(e)