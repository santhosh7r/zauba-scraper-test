import pandas as pd
import sqlite3

DB = sqlite3.connect("scraper.db")


def export_companies():

    query = """
    SELECT *
    FROM companies
    """

    df = pd.read_sql(
        query,
        DB
    )

    df.to_csv(
        "exports/companies.csv",
        index=False
    )

    print("[+] CSV Exported")
