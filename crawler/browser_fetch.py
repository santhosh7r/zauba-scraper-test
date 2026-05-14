import os
import random
from pathlib import Path
from playwright.sync_api import sync_playwright

try:
    from playwright_stealth import Stealth
    _stealth_available = True
except ImportError:
    _stealth_available = False

from config import (
    HEADLESS,
    SLOW_MO,
    PAGE_TIMEOUT,
    PAGE_WAIT_AFTER_LOAD,
    USER_AGENT,
    RAW_HTML_DIR
)
from utils.logger import log

os.makedirs(RAW_HTML_DIR, exist_ok=True)

PROFILE_DIR = Path(__file__).parent.parent / "browser_profile"


class BrowserManager:
    """
    Playwright browser using a persistent profile directory.

    The persistent profile stores cookies, localStorage, IndexedDB and
    Cloudflare fingerprint acceptance — so after running warm_up.py once,
    the bot re-uses the same verified session automatically.
    """

    def __init__(self):
        self._playwright = None
        self._context = None   # launch_persistent_context IS the context
        self.page = None
        self._started = False

    def start(self, headless: bool = HEADLESS):
        if self._started:
            return

        if not PROFILE_DIR.exists():
            log.warning(
                "No browser profile found at %s\n"
                "  → Run:  python warm_up.py\n"
                "  → Then: python bot.py\n"
                "  The warm-up lets you solve Cloudflare once; "
                "the bot reuses that verified session.",
                PROFILE_DIR
            )

        log.info("Starting browser (headless=%s, profile=%s)", headless, PROFILE_DIR)

        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()

        # launch_persistent_context = full Chrome profile, not just cookies
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=headless,
            slow_mo=SLOW_MO,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--window-size=1920,1080",
            ],
            viewport={"width": 1920, "height": 1080},
            user_agent=USER_AGENT,
            locale="en-US",
            timezone_id="Asia/Kolkata",
        )

        # Remove webdriver fingerprint
        self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        # Apply stealth on existing pages + new ones
        if _stealth_available:
            stealth = Stealth()
            for pg in self._context.pages:
                stealth.apply_stealth_sync(pg)
            self._context.on(
                "page",
                lambda pg: stealth.apply_stealth_sync(pg)
            )
            log.debug("Playwright stealth applied")

        # Use first existing page or open a new one
        if self._context.pages:
            self.page = self._context.pages[0]
        else:
            self.page = self._context.new_page()

        self._started = True
        log.info("Browser ready")

    def fetch(self, url: str, save_as: str | None = None) -> str:
        """Navigate to *url*, wait for load, return full HTML."""
        if not self._started:
            raise RuntimeError("Call BrowserManager.start() first")

        log.info("[Browser] → %s", url)

        try:
            self.page.goto(
                url,
                timeout=PAGE_TIMEOUT,
                wait_until="domcontentloaded"
            )

            # Human-like random mouse movement
            try:
                self.page.mouse.move(
                    random.randint(200, 900),
                    random.randint(200, 600)
                )
                self.page.mouse.move(
                    random.randint(300, 800),
                    random.randint(100, 500)
                )
            except Exception:
                pass

            self.page.wait_for_timeout(PAGE_WAIT_AFTER_LOAD)

            html = self.page.content()

            if save_as:
                path = os.path.join(RAW_HTML_DIR, save_as)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(html)
                log.debug("Raw HTML saved → %s", path)

            return html

        except Exception as exc:
            log.error("[Browser] Fetch failed for %s: %s", url, exc)
            return ""

    def close(self):
        if self._started:
            try:
                self._context.close()
                self._playwright.stop()
            except Exception:
                pass
            self._started = False
            log.info("Browser closed")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.close()


# Shared singleton
browser_manager = BrowserManager()