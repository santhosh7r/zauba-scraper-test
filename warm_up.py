#!/usr/bin/env python3
"""
warm_up.py — Human-assisted Cloudflare Turnstile solver
=========================================================
Run this ONCE before running the bot. It will:
  1. Open a real visible browser using a persistent profile directory
  2. Navigate to zaubacorp.com
  3. Wait for YOU to solve the Cloudflare challenge (or wait for auto-pass)
  4. Save the FULL browser state (cookies + localStorage + fingerprint data)
     to the ./browser_profile/ directory
  5. The bot reuses this profile for all future scraping

Usage:
    python warm_up.py
"""

from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE_DIR = Path(__file__).parent / "browser_profile"
TARGET_URL   = "https://www.zaubacorp.com"


def run_warmup():
    print("=" * 60)
    print("  Zauba Scraper — Cloudflare Warm-Up Tool")
    print("=" * 60)
    print()
    print("A browser window will open. Please:")
    print("  1. Wait for Cloudflare to verify you (auto or checkbox)")
    print("  2. Once you see the Zauba homepage, press ENTER here")
    print()
    input("Press ENTER to open the browser...")

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        # launch_persistent_context = full Chrome profile (cookies + localStorage + all)
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            slow_mo=100,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--window-size=1280,800",
                "--start-maximized",
            ],
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="Asia/Kolkata",
        )

        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        page = context.new_page()

        print(f"\n[+] Navigating to {TARGET_URL} ...")
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=90_000)

        print()
        print("=" * 60)
        print("  Solve the Cloudflare challenge in the browser window.")
        print("  Once the Zauba homepage loads fully, press ENTER below.")
        print("=" * 60)
        input("\nPress ENTER after Zauba homepage is visible...")

        # Persist state — browser_profile dir now has everything
        context.close()

    print(f"\n[✓] Browser profile saved to: {PROFILE_DIR}")
    print()
    print("=" * 60)
    print("  Warm-up complete! Now run the bot:")
    print("  python bot.py --scrape --limit 500")
    print()
    print("  TIP: If blocked again later, just re-run this warm-up.")
    print("=" * 60)


if __name__ == "__main__":
    run_warmup()
