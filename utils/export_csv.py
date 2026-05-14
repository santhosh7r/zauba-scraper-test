import os
import pandas as pd
from datetime import datetime

from config import EXPORTS_DIR
from database.db import DB
from utils.logger import log

os.makedirs(EXPORTS_DIR, exist_ok=True)


def export_companies(filename: str | None = None) -> str:
    """Export all companies to CSV. Returns the output file path."""
    if filename is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"companies_{ts}.csv"

    out_path = os.path.join(EXPORTS_DIR, filename)

    df = pd.read_sql(
        "SELECT * FROM companies ORDER BY company_name",
        DB
    )

    df.to_csv(out_path, index=False)
    log.info("Exported %d companies → %s", len(df), out_path)
    return out_path
