from playwright.sync_api import (
    sync_playwright
)

from playwright_stealth import (
    Stealth
)


class BrowserManager:

    def __init__(self):

        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def start(self):

        self.playwright = (
            sync_playwright().start()
        )

        self.browser = (
            self.playwright.chromium.launch(

                headless=False,

                slow_mo=300,

                args=[

                    "--disable-blink-features=AutomationControlled",

                    "--disable-dev-shm-usage",

                    "--no-sandbox",

                    "--disable-setuid-sandbox",

                    "--disable-infobars",

                    "--window-size=1920,1080"
                ]
            )
        )

        self.context = (
            self.browser.new_context(

                viewport={
                    "width": 1920,
                    "height": 1080
                },

                user_agent=(

                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),

                locale="en-US",

                timezone_id="Asia/Kolkata"
            )
        )

        self.page = (
            self.context.new_page()
        )

        stealth = Stealth()

        stealth.apply_stealth_sync(
            self.page
        )

        self.page.add_init_script("""
        Object.defineProperty(
            navigator,
            'webdriver',
            {
                get: () => undefined
            }
        );
        """)

    def fetch(self, url):

        try:

            print(
                f"[Browser] Opening: {url}"
            )

            self.page.goto(
                url,
                timeout=120000,
                wait_until="domcontentloaded"
            )

            self.page.wait_for_timeout(
                15000
            )

            html = self.page.content()

            with open(
                "raw_html/browser_page.html",
                "w",
                encoding="utf-8"
            ) as f:

                f.write(html)

            return html

        except Exception as e:

            print(
                f"[Browser Error] {e}"
            )

            return ""

    def close(self):

        self.browser.close()

        self.playwright.stop()


browser_manager = BrowserManager()