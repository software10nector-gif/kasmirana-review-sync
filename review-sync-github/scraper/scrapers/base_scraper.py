"""
Shared Playwright browser setup + retry policy for every marketplace scraper.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from playwright.sync_api import BrowserContext, sync_playwright
from tenacity import retry, stop_after_attempt, wait_exponential

from config import config
from utils.logger import get_logger

log = get_logger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


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

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=30))
    def run(self) -> tuple[list[ScrapedReview], Optional[ScrapedProductStats]]:
        if not self.product_url:
            log.warning(f"[{self.source_slug}] No product URL configured, skipping.")
            return [], None

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=config.headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context: BrowserContext = browser.new_context(
                user_agent=_USER_AGENT,
                viewport={"width": 1366, "height": 900},
                locale="en-IN",
            )
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            page = context.new_page()
            page.set_default_timeout(config.request_timeout_ms)

            try:
                log.info(f"[{self.source_slug}] Opening {self.product_url}")
                page.goto(self.product_url, wait_until="domcontentloaded")
                reviews, stats = self.scrape(page)
                log.info(f"[{self.source_slug}] Scraped {len(reviews)} review(s).")
                return reviews, stats
            finally:
                context.close()
                browser.close()
