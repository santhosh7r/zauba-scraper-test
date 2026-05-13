import sqlite3

DB = sqlite3.connect(
    "scraper.db",
    check_same_thread=False
)

cursor = DB.cursor()


def initialize_database():

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS company_urls(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        url TEXT UNIQUE,

        page_number INTEGER,

        scraped INTEGER DEFAULT 0,

        failed INTEGER DEFAULT 0,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS companies(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        cin TEXT UNIQUE,

        company_name TEXT,

        status TEXT,

        roc TEXT,

        company_type TEXT,

        incorporation_date TEXT,

        email TEXT,

        website TEXT,

        address TEXT,

        state TEXT,

        city TEXT,

        authorized_capital TEXT,

        paid_up_capital TEXT,

        company_category TEXT,

        company_subcategory TEXT,

        source_url TEXT,

        content_hash TEXT,

        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    DB.commit()