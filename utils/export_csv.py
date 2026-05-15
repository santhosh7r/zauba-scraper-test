import os
import httpx
import pandas as pd
from datetime import datetime

from config import EXPORTS_DIR, SUPABASE_URL, SUPABASE_KEY
from database.supabase_client import get_headers, get_base_url
from utils.logger import log

os.makedirs(EXPORTS_DIR, exist_ok=True)


def export_companies(filename: str | None = None) -> str | None:
    """Export all companies from Supabase to CSV. Returns the output file path."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        log.warning("Supabase configuration missing. Cannot export CSV.")
        return None

    if filename is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"companies_{ts}.csv"

    out_path = os.path.join(EXPORTS_DIR, filename)

    url = f"{get_base_url()}/rest/v1/companies"

    try:
        # Note: In a production db with millions of rows, pagination is required.
        # This basic implementation fetches up to 1000 for demonstration.
        response = httpx.get(
            url,
            headers=get_headers(),
            params={"select": "*", "limit": "1000"},
            timeout=30.0
        )
        response.raise_for_status()
        data = response.json()
        if not data:
            log.warning("No data found in Supabase to export.")
            return None
        
        df = pd.DataFrame(data)
        df.to_csv(out_path, index=False)
        log.info("Exported %d companies → %s", len(df), out_path)
        return out_path
    except Exception as e:
        log.error("Failed to export companies from Supabase: %s", e)
        return None


