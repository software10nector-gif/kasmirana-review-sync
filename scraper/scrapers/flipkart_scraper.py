"""
Flipkart product-review scraper. All CSS selectors live in selectors.py —
edit that file, not this one, when Flipkart changes their page layout.
"""
import re
from typing import Optional

from scrapers.base_scraper import BaseScraper, ScrapedProductStats, ScrapedReview
from scrapers.selectors import FLIPKART as SEL
from utils.logger import get_logger

log = get_logger(__name__)


class FlipkartScraper(BaseScraper):
    source_slug = "flipkart"

    def scrape(self, page) -> tuple[list[ScrapedReview], Optional[ScrapedProductStats]]:
        reviews: list[ScrapedReview] = []

        try:
            if page.locator(SEL["all_reviews_link"]).count() > 0:
                with page.expect_navigation(wait_until="domcontentloaded"):
                    page.locator(SEL["all_reviews_link"]).first.click()
        except Exception as exc:  # noqa: BLE001
            log.warning(f"[flipkart] Could not open the full reviews page, using product page as-is: {exc}")

        stats = self._extract_stats(page)

        cards = page.locator(SEL["review_card"])
        count = min(cards.count(), 100)
        for i in range(count):
            card = cards.nth(i)
            try:
                rating_text = card.locator(SEL["rating_badge"]).first.inner_text(timeout=2000)
                rating = int(re.search(r"\d", rating_text).group())
            except Exception:
                continue

            def _safe_text(selector: str) -> str:
                try:
                    return card.locator(selector).first.inner_text(timeout=1500).strip()
                except Exception:
                    return ""

            reviews.append(
                ScrapedReview(
                    reviewer_name=_safe_text(SEL["reviewer_name"]) or "Anonymous",
                    rating=rating,
                    review_title=_safe_text(SEL["review_title"]),
                    review_text=_safe_text(SEL["review_text"]),
                    review_date_raw=_safe_text(SEL["review_date"]),
                )
            )

        return reviews, stats

    def _extract_stats(self, page) -> Optional[ScrapedProductStats]:
        try:
            rating_text = page.locator(SEL["overall_rating"]).first.inner_text(timeout=3000)
            overall_rating = float(rating_text.strip())
        except Exception:
            log.warning("[flipkart] Could not read overall rating.")
            return None

        try:
            total_text = page.locator(SEL["total_reviews"]).first.inner_text(timeout=3000)
            digits = re.sub(r"[^\d]", "", total_text)
            total_reviews = int(digits) if digits else 0
        except Exception:
            total_reviews = 0

        return ScrapedProductStats(overall_rating=overall_rating, total_reviews=total_reviews)
