#!/usr/bin/env python3
"""
warm_up.py — Human-assisted Cloudflare Turnstile solver
=========================================================
Run this ONCE before starting the bot on a fresh VPS (or after being blocked).
It will:
  1. Open a real, fully visible Chrome browser using the persistent profile
     directory (./browser_profile/) so any previously saved cookies are loaded.
  2. Navigate to zaubacorp.com.
  3. Wait for YOU to solve the Cloudflare challenge (or wait for auto-pass).
  4. After you press ENTER, save the FULL browser state (cookies, localStorage,
     IndexedDB, cache, fingerprint data) permanently to ./browser_profile/.
  5. The bot reuses this profile for all future scraping sessions, so
     Cloudflare sees a returning user rather than a fresh browser.

Usage:
    python warm_up.py

After running this, start the bot with:
    python bot.py
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from config import BROWSER_ARGS, get_random_user_agent, get_random_viewport

PROFILE_DIR = Path(__file__).parent / "browser_profile"
TARGET_URL  = "https://www.zaubacorp.com"


def _banner(title: str):
    print()
    print("=" * 64)
    print(f"  {title}")
    print("=" * 64)


def run_warmup():
    _banner("Zauba Scraper — Cloudflare Warm-Up Tool")
    print()
    print("This will open a real Chrome browser window.")
    print()
    print("What to do:")
    print("  1. Look at the browser window that opens.")
    print("  2. If you see a Cloudflare challenge, solve it (click the")
    print("     checkbox, complete the CAPTCHA, or just wait for auto-pass).")
    print("  3. Once the Zauba homepage is fully visible, come back here")
    print("     and press ENTER.")
    print()

    try:
        input("Press ENTER to open the browser (Ctrl+C to cancel)...")
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    ua       = get_random_user_agent()
    viewport = get_random_viewport()

    print(f"\n[+] Profile directory : {PROFILE_DIR}")
    print(f"[+] Viewport          : {viewport['width']}×{viewport['height']}")
    print(f"[+] User-Agent        : {ua[:60]}...")
    print()

    with sync_playwright() as p:
        # launch_persistent_context = full Chrome profile (cookies + localStorage + all)
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,      # Must be visible for human interaction
            slow_mo=80,
            args=BROWSER_ARGS + [
                f"--window-size={viewport['width']},{viewport['height']}",
                "--start-maximized",
            ],
            viewport=viewport,
            user_agent=ua,
            locale="en-US",
            timezone_id="Asia/Kolkata",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Upgrade-Insecure-Requests": "1",
            },
        )

        # Patch automation fingerprints before any page loads.
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        """)

        page = context.new_page()

        print(f"[+] Navigating to {TARGET_URL} ...")
        try:
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=120_000)
        except Exception as exc:
            print(f"[!] Navigation warning (browser may still be open): {exc}")

        print()
        _banner("ACTION REQUIRED")
        print()
        print("  The browser is now open. If you see a Cloudflare challenge:")
        print("    ✓ Tick the checkbox  OR")
        print("    ✓ Wait for it to pass automatically")
        print()
        print("  Once the ZAUBA HOMEPAGE is fully visible, press ENTER below.")
        print()

        try:
            input("Press ENTER after the Zauba homepage is visible...")
        except KeyboardInterrupt:
            print("\n[!] Interrupted — closing browser without saving full session.")
            context.close()
            sys.exit(1)

        # Closing the persistent context flushes cookies/localStorage to disk.
        print("\n[+] Saving session to disk...")
        context.close()

    _banner("Warm-Up Complete!")
    print()
    print(f"  ✓ Profile saved to: {PROFILE_DIR}")
    print()
    print("  You can now start the bot:")
    print("    python bot.py")
    print()
    print("  TIP: If blocked again later, just re-run this warm-up:")
    print("    python warm_up.py")
    print()
    print("  TIP: To rotate the profile entirely (fresh start):")
    print(f"    rm -rf {PROFILE_DIR} && python warm_up.py")
    print("=" * 64)
    print()


if __name__ == "__main__":
    run_warmup()
