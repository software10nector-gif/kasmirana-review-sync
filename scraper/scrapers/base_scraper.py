"""
Shared Playwright browser setup + retry policy for every marketplace scraper.

Flipkart/Meesho intermittently block or serve empty pages to GitHub Actions'
datacenter IPs. A single job keeps the SAME IP for its whole run (retrying
within one run doesn't get a new IP), so the two levers that actually help
without paying for a proxy are: (1) look as close to a real browser as
practical, and (2) run often enough that across many runs/days, some land
on an IP that isn't currently flagged.
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

    def __init__(self, product_url: str):
        self.product_url = product_url

    @abstractmethod
    def scrape(self, page) -> tuple[list[ScrapedReview], Optional[ScrapedProductStats]]:
        raise NotImplementedError

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=3, min=5, max=60))
    def run(self) -> tuple[list[ScrapedReview], Optional[ScrapedProductStats]]:
        if not self.product_url:
            log.warning(f"[{self.source_slug}] No product URL configured, skipping.")
            return [], None

        # A short randomized pause before even launching the browser — real
        # traffic doesn't arrive in perfectly regular, instant bursts.
        page_ready_jitter = random.uniform(0.5, 2.5)

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=config.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ],
            )
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

            try:
                page.wait_for_timeout(page_ready_jitter * 1000)
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
