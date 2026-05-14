import sqlite3
import os

from config import DB_PATH

DB = sqlite3.connect(
    DB_PATH,
    check_same_thread=False
)
DB.row_factory = sqlite3.Row

cursor = DB.cursor()


def initialize_database():
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS company_urls (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        url         TEXT UNIQUE NOT NULL,
        page_number INTEGER,
        scraped     INTEGER DEFAULT 0,
        failed      INTEGER DEFAULT 0,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS companies (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        cin                 TEXT UNIQUE,
        company_name        TEXT NOT NULL,
        status              TEXT,
        roc                 TEXT,
        company_type        TEXT,
        incorporation_date  TEXT,
        email               TEXT,
        website             TEXT,
        address             TEXT,
        state               TEXT,
        city                TEXT,
        authorized_capital  TEXT,
        paid_up_capital     TEXT,
        company_category    TEXT,
        company_subcategory TEXT,
        source_url          TEXT,
        content_hash        TEXT,
        last_updated        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    DB.commit()


def get_unscraped_urls(limit: int) -> list[str]:
    rows = cursor.execute(
        """
        SELECT url
        FROM company_urls
        WHERE scraped = 0 AND failed < 3
        ORDER BY id
        LIMIT ?
        """,
        (limit,)
    ).fetchall()
    return [row["url"] for row in rows]


def mark_scraped(url: str):
    cursor.execute(
        "UPDATE company_urls SET scraped = 1 WHERE url = ?",
        (url,)
    )
    DB.commit()


def mark_failed(url: str):
    cursor.execute(
        "UPDATE company_urls SET failed = failed + 1 WHERE url = ?",
        (url,)
    )
    DB.commit()


def save_company_url(url: str, page: int):
    try:
        cursor.execute(
            "INSERT INTO company_urls(url, page_number) VALUES(?, ?)",
            (url, page)
        )
        DB.commit()
    except sqlite3.IntegrityError:
        pass  # duplicate — skip silently


def save_company(data: dict):
    cursor.execute(
        """
        INSERT OR REPLACE INTO companies(
            cin, company_name, status, roc, company_type,
            incorporation_date, email, website, address, state,
            city, authorized_capital, paid_up_capital,
            company_category, company_subcategory,
            source_url, content_hash
        )
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            data.get("cin"),
            data.get("company_name"),
            data.get("status"),
            data.get("roc"),
            data.get("company_type"),
            data.get("incorporation_date"),
            data.get("email"),
            data.get("website"),
            data.get("address"),
            data.get("state"),
            data.get("city"),
            data.get("authorized_capital"),
            data.get("paid_up_capital"),
            data.get("company_category"),
            data.get("company_subcategory"),
            data.get("source_url"),
            data.get("content_hash"),
        )
    )
    DB.commit()