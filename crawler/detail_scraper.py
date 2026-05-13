import time
import json
import hashlib
import httpx

from bs4 import BeautifulSoup

from database.db import DB, cursor

from utils.address_parser import (
    extract_state,
    extract_city
)

from crawler.browser_fetch import (
    browser_manager
)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64)"
    )
}


def is_blocked_page(html):

    blocked_keywords = [

        "Just a moment",
        "Checking your browser",
        "Enable JavaScript",
        "Cloudflare"
    ]

    for keyword in blocked_keywords:

        if keyword.lower() in html.lower():
            return True

    return False


def extract_table_value(soup, label):

    rows = soup.find_all("tr")

    for row in rows:

        cols = row.find_all("td")

        if len(cols) < 2:
            continue

        key = cols[0].get_text(
            strip=True
        )

        value = cols[1].get_text(
            strip=True
        )

        if label.lower() in key.lower():

            return value

    return None


def extract_json_ld(soup):

    scripts = soup.find_all(
        "script",
        type="application/ld+json"
    )

    for script in scripts:

        try:

            data = json.loads(
                script.string
            )

            if isinstance(data, dict):

                return data

        except:
            continue

    return {}


def generate_hash(data):

    return hashlib.md5(
        str(data).encode()
    ).hexdigest()


def save_company(data):

    try:

        cursor.execute(
            """
            INSERT OR REPLACE INTO companies(

                cin,
                company_name,
                status,
                roc,
                company_type,
                incorporation_date,
                email,
                website,
                address,
                state,
                city,
                authorized_capital,
                paid_up_capital,
                company_category,
                company_subcategory,
                source_url,
                content_hash

            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                data["cin"],
                data["company_name"],
                data["status"],
                data["roc"],
                data["company_type"],
                data["incorporation_date"],
                data["email"],
                data["website"],
                data["address"],
                data["state"],
                data["city"],
                data["authorized_capital"],
                data["paid_up_capital"],
                data["company_category"],
                data["company_subcategory"],
                data["source_url"],
                data["content_hash"]
            )
        )

        DB.commit()

    except Exception as e:

        print(e)


def scrape_company(url):

    print(f"\n[+] Scraping {url}")

    try:

        response = httpx.get(
            url,
            headers=HEADERS,
            timeout=60,
            follow_redirects=True
        )

        html = response.text

    except Exception as e:

        print(f"[HTTP Error] {e}")

        return

    if is_blocked_page(html):

        print("[!] Cloudflare detected")
        print("[!] Switching to browser mode")

        html = browser_manager.fetch(url)

    if not html:

        print("[!] Empty HTML")

        return

    if is_blocked_page(html):

        print("[!] Still blocked")

        with open(
            "raw_html/blocked_page.html",
            "w",
            encoding="utf-8"
        ) as f:

            f.write(html)

        return

    with open(
        "raw_html/company_page.html",
        "w",
        encoding="utf-8"
    ) as f:

        f.write(html)

    soup = BeautifulSoup(
        html,
        "lxml"
    )

    json_ld = extract_json_ld(soup)

    cin = (
        json_ld.get("identifier", {})
        .get("value")
    )

    company_name = (
        json_ld.get("name")
    )

    email = (
        json_ld.get("email")
    )

    address = (
        json_ld.get("address")
    )

    website = (
        json_ld.get("url")
    )

    incorporation_date = (
        json_ld.get("foundingDate")
    )

    status = extract_table_value(
        soup,
        "Status"
    )

    roc = extract_table_value(
        soup,
        "ROC"
    )

    company_type = (
        extract_table_value(
            soup,
            "Principal Business"
        )
    )

    authorized_capital = (
        extract_table_value(
            soup,
            "Authorized Capital"
        )
    )

    paid_up_capital = (
        extract_table_value(
            soup,
            "Paid up capital"
        )
    )

    company_category = (
        extract_table_value(
            soup,
            "Company Category"
        )
    )

    company_subcategory = (
        extract_table_value(
            soup,
            "Company Subcategory"
        )
    )

    if not company_name:

        title = soup.find("title")

        if title:

            company_name = (
                title.text
                .replace(
                    "| ZaubaCorp",
                    ""
                )
                .strip()
            )

    if (
        not company_name
        or
        "just a moment" in company_name.lower()
    ):

        print("[!] Invalid page")

        with open(
            "raw_html/failed_page.html",
            "w",
            encoding="utf-8"
        ) as f:

            f.write(html)

        return

    state = extract_state(address)

    city = extract_city(address)

    data = {

        "cin": cin,

        "company_name": company_name,

        "status": status,

        "roc": roc,

        "company_type": company_type,

        "incorporation_date": incorporation_date,

        "email": email,

        "website": website,

        "address": address,

        "state": state,

        "city": city,

        "authorized_capital": authorized_capital,

        "paid_up_capital": paid_up_capital,

        "company_category": company_category,

        "company_subcategory": company_subcategory,

        "source_url": url
    }

    data["content_hash"] = generate_hash(data)

    print("\n========== EXTRACTED DATA ==========")

    for k, v in data.items():

        print(f"{k}: {v}")

    print("===================================\n")

    save_company(data)

    cursor.execute(
        """
        UPDATE company_urls
        SET scraped = 1
        WHERE url = ?
        """,
        (url,)
    )

    DB.commit()

    print(
        f"[+] Saved {company_name}"
    )


def start_scraping(limit=100):

    browser_manager.start()

    urls = cursor.execute(
        """
        SELECT url
        FROM company_urls
        WHERE scraped = 0
        LIMIT ?
        """,
        (limit,)
    ).fetchall()

    for row in urls:

        try:

            scrape_company(row[0])

            time.sleep(3)

        except Exception as e:

            print(e)

    browser_manager.close()