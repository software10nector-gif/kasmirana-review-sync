"""
Shared Playwright browser setup + retry policy for every marketplace scraper.

Meesho specifically runs Akamai Bot Manager (confirmed: block page comes
from errors.edgesuite.net, Akamai's own edge network) — an industrial-grade
anti-bot system that fingerprints far beyond IP reputation: TLS/HTTP2
handshake shape, headless-Chromium-specific gaps (missing proprietary
codecs/Widevine that only real Chrome has), full browser API surface, and
behavioural signals. The levers below are the legitimate, free things that
measurably reduce that fingerprint surface:

  1. Launch real Google Chrome (channel="chrome") instead of bundled
     Chromium when available — bundled Chromium is missing pieces (codecs,
     Widevine DRM) that headless-detection scripts specifically probe for.
  2. playwright-stealth — a maintained community patch set covering many
     more fingerprint leaks (WebGL vendor/renderer, permissions API,
     iframe.contentWindow, hairline feature detection, etc.) than a
     hand-rolled init script can realistically cover.
  3. A "warm-up" visit to the site's homepage before deep-linking straight
     to the product page — arriving cold with no session/referrer history
     is itself a suspicious pattern to these systems.

None of this can defeat Akamai outright (nothing free reliably does), but
each measurably shrinks the fingerprint surface, which is what's actually
achievable without paying for a specialized unblocking proxy.
"""
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from playwright.sync_api import BrowserContext, sync_playwright
from tenacity import retry, stop_after_attempt, wait_exponential

from config import config
from utils.logger import get_logger

log = get_logger(__name__)

try:
    from playwright_stealth import stealth_sync
    _STEALTH_AVAILABLE = True
except ImportError:
    _STEALTH_AVAILABLE = False

# Rotate between a few real, current desktop Chrome UAs instead of always
# sending the exact same one every run.
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
]


@dataclass
class ScrapedReview:
    reviewer_name: str
    rating: int
    review_title: str
    review_text: str
    review_date_raw: str


@dataclass
class ScrapedProductStats:
    overall_rating: float
    total_reviews: int


class BaseScraper(ABC):
    source_slug: str = "base"
    # Subclasses (e.g. MeeshoScraper) can set this to the site's plain
    # homepage — visited first, briefly, before the real product URL, so
    # the deep-link doesn't arrive as the very first request of the session.
    warmup_url: Optional[str] = None

    def __init__(self, product_url: str):
        self.product_url = product_url

    @abstractmethod
    def scrape(self, page) -> tuple[list[ScrapedReview], Optional[ScrapedProductStats]]:
        raise NotImplementedError

    def _launch_browser(self, p):
        """Prefer real Google Chrome (closer fingerprint to a genuine user
        install than bundled Chromium); fall back cleanly if it isn't
        installed on this runner."""
        try:
            return p.chromium.launch(
                headless=config.headless,
                channel="chrome",
                args=["--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"],
            )
        except Exception as exc:  # noqa: BLE001
            log.info(f"[{self.source_slug}] Real Chrome channel unavailable ({exc}), using bundled Chromium.")
            return p.chromium.launch(
                headless=config.headless,
                args=["--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"],
            )

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=3, min=5, max=60))
    def run(self) -> tuple[list[ScrapedReview], Optional[ScrapedProductStats]]:
        if not self.product_url:
            log.warning(f"[{self.source_slug}] No product URL configured, skipping.")
            return [], None

        # A short randomized pause before even launching the browser — real
        # traffic doesn't arrive in perfectly regular, instant bursts.
        page_ready_jitter = random.uniform(0.5, 2.5)

        with sync_playwright() as p:
            browser = self._launch_browser(p)
            context: BrowserContext = browser.new_context(
                user_agent=random.choice(_USER_AGENTS),
                viewport={"width": 1366, "height": 900},
                locale="en-IN",
                timezone_id="Asia/Kolkata",
                extra_http_headers={
                    "Accept-Language": "en-IN,en;q=0.9",
                },
            )
            # Reduce the most obvious automation fingerprints.
            context.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-IN', 'en']});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                window.chrome = { runtime: {} };
                """
            )
            page = context.new_page()
            page.set_default_timeout(config.request_timeout_ms)

            if _STEALTH_AVAILABLE:
                stealth_sync(page)

            try:
                page.wait_for_timeout(page_ready_jitter * 1000)

                if self.warmup_url:
                    try:
                        log.info(f"[{self.source_slug}] Warming up at {self.warmup_url}")
                        page.goto(self.warmup_url, wait_until="domcontentloaded")
                        page.mouse.wheel(0, random.randint(300, 700))
                        page.wait_for_timeout(random.uniform(1500, 3000))
                    except Exception as exc:  # noqa: BLE001
                        log.warning(f"[{self.source_slug}] Warm-up navigation failed, continuing anyway: {exc}")

                log.info(f"[{self.source_slug}] Opening {self.product_url}")
                page.goto(self.product_url, wait_until="domcontentloaded")
                # A brief human-like pause + tiny scroll before reading
                # anything, rather than scraping the instant the DOM exists.
                page.mouse.wheel(0, random.randint(200, 600))
                page.wait_for_timeout(random.uniform(800, 1800))
                reviews, stats = self.scrape(page)
                log.info(f"[{self.source_slug}] Scraped {len(reviews)} review(s).")
                return reviews, stats
            finally:
                context.close()
                browser.close()
