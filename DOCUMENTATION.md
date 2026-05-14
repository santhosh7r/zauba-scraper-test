# Technical Documentation: Zauba Corp Scraper Bot

## 1. Overview
The Zauba Corp Scraper is a modular, high-performance Python-based bot designed to extract Indian company information from [ZaubaCorp](https://www.zaubacorp.com). It implements a multi-stage pipeline: URL discovery, detailed data extraction, and automated CSV export.

### Core Technical Stack
*   **Networking:** `httpx` (Synchronous with advanced header management)
*   **Parsing:** `BeautifulSoup4` (LXML backend)
*   **Data Storage:** `SQLite3` (Persistent state management)
*   **Analysis:** `Pandas` (CSV Export generation)

---

## 2. System Architecture

The project is designed with a modular architecture to ensure separation of concerns:

- **`bot.py`**: Unified CLI interface using `argparse`. Handles execution modes (full, discovery-only, or scraping-only).
- **`crawler/discover.py`**: Crawls listing pages to find unique company URLs. It filters out non-company links and avoids duplicates using the DB.
- **`crawler/detail_scraper.py`**: The core extraction engine. It fetches individual company pages and parses structured data.
- **`database/db.py`**: Manages the SQLite connection and schema. Tracks URL status (`scraped`, `failed`, `page_number`).
- **`utils/address_parser.py`**: Uses regex and state-code mapping to decompose raw address strings into City and State.
- **`config.py`**: Centralized settings for timeouts, delays, and HTTP headers.

---

## 3. Key Technical Features & Fixes

### 🛡️ Advanced Anti-Detection
The project moved from heavy Playwright browser automation to lightweight `httpx` with a highly optimized detection bypass:
*   **False Positive Correction:** Resolved an issue where legitimate pages were flagged as "blocked" because they contained the word "cloudflare" (due to a CDN script). The new logic specifically targets actual Cloudflare Turnstile challenge patterns.
*   **Jittered Delays:** Mimics human browsing by using random uniform delays between requests.
*   **Header Rotation:** Uses realistic User-Agents and browser-standard headers.

### 📊 Data Extraction Strategy
1.  **JSON-LD First:** Prioritizes extracting structured data from `<script type="application/ld+json">`.
2.  **HTML Table Fallback:** Dynamically parses the "Company Details" HTML table as a secondary source.
3.  **Deduplication:** Uses content hashing to ensure data integrity across runs.

### 📍 Intelligent Address Parsing
Accurately extracts City and State from unstructured address strings by leveraging Indian State Codes and Pincode pattern recognition.

---

## 4. Data Flow

1.  **Discovery:** Crawls listing pages to populate the `company_urls` table.
2.  **Queueing:** Fetches unscraped URLs from the database.
3.  **Extraction:** Fetches and parses each company page using structured extraction logic.
4.  **Persistence:** Saves company data to the `companies` table and updates the scrape status.
5.  **Export:** Generates a timestamped CSV file in the `exports/` directory.

---

## 5. Usage

```bash
# Full execution
python bot.py --start-page 1 --end-page 10 --limit 500

# Single URL test
python bot.py --test-url https://www.zaubacorp.com/company/EXAMPLE-URL

# Export to CSV
python bot.py --export
```
