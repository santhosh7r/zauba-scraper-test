"""
database/db.py — local SQLite work queue
==========================================
Tracks every discovered company URL and its processing state. This is only a
*queue* — the scraped company data itself lives in Supabase. A URL is
considered done once it has been ``synced`` (stored in Supabase) or has failed
``MAX_URL_ATTEMPTS`` times.

All writes go through ``_write`` which retries on a transient "database is
locked" error, so a busy database never crashes the bot.
"""

import sqlite3
import time

from config import DB_PATH, MAX_URL_ATTEMPTS
from utils.logger import log

DB = sqlite3.connect(DB_PATH, check_same_thread=False)
DB.row_factory = sqlite3.Row

# WAL mode keeps reads and writes from blocking each other — safer for a
# long-running process.
try:
    DB.execute("PRAGMA journal_mode=WAL;")
    DB.execute("PRAGMA synchronous=NORMAL;")
except sqlite3.OperationalError as exc:
    log.warning("Could not set SQLite pragmas: %s", exc)

cursor = DB.cursor()


def _write(sql: str, params: tuple = (), retries: int = 5):
    """Execute a write statement, retrying briefly if the database is locked."""
    for attempt in range(1, retries + 1):
        try:
            cursor.execute(sql, params)
            DB.commit()
            return
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower() and attempt < retries:
                time.sleep(0.5 * attempt)
                continue
            raise


def initialize_database():
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS company_urls (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        url                TEXT UNIQUE NOT NULL,
        page_number        INTEGER,
        cin                TEXT,
        incorporation_date TEXT,
        is_recent          INTEGER DEFAULT 0,
        content_hash       TEXT,
        scraped            INTEGER DEFAULT 0,
        failed             INTEGER DEFAULT 0,
        synced             INTEGER DEFAULT 0,
        retry_count        INTEGER DEFAULT 0,
        last_attempted     TIMESTAMP,
        created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    DB.commit()

    # Seamless migrations for older databases.
    for stmt in (
        "ALTER TABLE company_urls ADD COLUMN synced INTEGER DEFAULT 0;",
        "ALTER TABLE company_urls ADD COLUMN retry_count INTEGER DEFAULT 0;",
        "ALTER TABLE company_urls ADD COLUMN last_attempted TIMESTAMP;",
        "ALTER TABLE company_urls ADD COLUMN cin TEXT;",
        "ALTER TABLE company_urls ADD COLUMN incorporation_date TEXT;",
        "ALTER TABLE company_urls ADD COLUMN is_recent INTEGER DEFAULT 0;",
        "ALTER TABLE company_urls ADD COLUMN content_hash TEXT;",
    ):
        try:
            cursor.execute(stmt)
        except sqlite3.OperationalError:
            pass

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_company_urls_state "
        "ON company_urls (synced, failed);"
    )
    DB.commit()


def save_company_url(url: str, page: int) -> bool:
    """Insert a freshly-discovered URL. Returns True if newly inserted."""
    try:
        _write(
            "INSERT INTO company_urls(url, page_number) VALUES(?, ?)",
            (url, page),
        )
        return True
    except sqlite3.IntegrityError:
        return False


def url_already_processed(url: str) -> bool:
    """A URL is 'done' once it has been stored in Supabase (synced) or has
    failed too many times. Note: a URL parsed under the old date-filter logic
    but never stored (synced=0) is intentionally NOT done — it gets re-scraped
    so it can finally be stored."""
    row = cursor.execute(
        "SELECT synced, failed FROM company_urls WHERE url = ?",
        (url,),
    ).fetchone()
    if not row:
        return False
    return row["synced"] == 1 or (row["failed"] or 0) >= MAX_URL_ATTEMPTS


def get_cached_content_hash(cin: str) -> str | None:
    row = cursor.execute(
        "SELECT content_hash FROM company_urls "
        "WHERE cin = ? AND content_hash IS NOT NULL LIMIT 1",
        (cin,),
    ).fetchone()
    return row["content_hash"] if row else None


def mark_stored(url: str, cin: str | None, incorporation_date: str | None,
                content_hash: str | None):
    """The company was successfully scraped and stored in Supabase."""
    _write(
        """
        UPDATE company_urls
           SET scraped = 1,
               synced = 1,
               is_recent = 1,
               cin = ?,
               incorporation_date = ?,
               content_hash = ?,
               last_attempted = CURRENT_TIMESTAMP
         WHERE url = ?
        """,
        (cin, incorporation_date, content_hash, url),
    )


def mark_failed(url: str):
    _write(
        """
        UPDATE company_urls
           SET failed = failed + 1,
               retry_count = retry_count + 1,
               last_attempted = CURRENT_TIMESTAMP
         WHERE url = ?
        """,
        (url,),
    )


def queue_stats() -> dict:
    """Snapshot of the work queue, for progress logging."""
    row = cursor.execute(
        """
        SELECT COUNT(*)                                   AS total,
               COALESCE(SUM(synced), 0)                   AS synced,
               COALESCE(SUM(CASE WHEN failed > 0 THEN 1 ELSE 0 END), 0) AS failed
          FROM company_urls
        """
    ).fetchone()
    return {"total": row["total"], "synced": row["synced"], "failed": row["failed"]}
