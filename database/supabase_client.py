import time

import httpx

from config import SUPABASE_URL, SUPABASE_KEY
from utils.logger import log

# How many times to retry a Supabase write on a transient failure.
_MAX_SYNC_RETRIES = 4


def _headers(prefer: str = "return=representation") -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def get_headers() -> dict:
    return _headers()


def get_base_url() -> str:
    url = SUPABASE_URL.rstrip("/")
    if url.endswith("/rest/v1"):
        url = url[: -len("/rest/v1")]
    return url


def _companies_endpoint() -> str:
    return f"{get_base_url()}/rest/v1/companies"


def fetch_existing_hash(cin: str) -> str | None:
    """Returns the stored content_hash for a CIN, or None if the row doesn't exist."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        r = httpx.get(
            _companies_endpoint(),
            headers=get_headers(),
            params={"cin": f"eq.{cin}", "select": "content_hash", "limit": "1"},
            timeout=10.0,
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return None
        return rows[0].get("content_hash")
    except Exception as exc:
        log.error("Error fetching existing hash for %s: %s", cin, exc)
        return None


def upsert_company_to_supabase(data: dict) -> bool:
    """Insert a new company or update an existing one (keyed by CIN).

    Skips the write entirely when the content_hash matches what is already
    stored, so we don't churn updated_at on no-op syncs.
    Returns True on success (including no-op), False on failure."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        log.warning("Supabase URL or key not configured; skipping sync.")
        return False

    cin = data.get("cin")
    if not cin:
        log.warning("Cannot sync company without CIN.")
        return False

    existing_hash = fetch_existing_hash(cin)
    if existing_hash and existing_hash == data.get("content_hash"):
        log.info("CIN %s unchanged (hash match); skipping update.", cin)
        return True

    for attempt in range(1, _MAX_SYNC_RETRIES + 1):
        try:
            r = httpx.post(
                _companies_endpoint(),
                headers=_headers("return=minimal,resolution=merge-duplicates"),
                params={"on_conflict": "cin"},
                json=data,
                timeout=20.0,
            )
            r.raise_for_status()
            return True
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            # 4xx (except rate-limit) is a permanent data problem — don't retry.
            if status < 500 and status != 429:
                log.error(
                    "HTTP error upserting %s: %s - %s",
                    cin, status, exc.response.text,
                )
                return False
            log.warning(
                "Transient Supabase error %s for %s (attempt %d/%d)",
                status, cin, attempt, _MAX_SYNC_RETRIES,
            )
        except Exception as exc:
            log.warning(
                "Network error upserting %s (attempt %d/%d): %s",
                cin, attempt, _MAX_SYNC_RETRIES, exc,
            )
        if attempt < _MAX_SYNC_RETRIES:
            time.sleep(3 * attempt)

    log.error("Failed to upsert %s after %d attempts.", cin, _MAX_SYNC_RETRIES)
    return False
