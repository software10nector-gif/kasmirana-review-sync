"""
Meesho product-review scraper. All CSS selectors live in selectors.py —
edit that file, not this one, when Meesho changes their page layout.
"""
import re
from typing import Optional

from scrapers.base_scraper import BaseScraper, ScrapedProductStats, ScrapedReview
from scrapers.selectors import MEESHO as SEL
from utils.logger import get_logger

log = get_logger(__name__)


class MeeshoScraper(BaseScraper):
    source_slug = "meesho"

    def scrape(self, page) -> tuple[list[ScrapedReview], Optional[ScrapedProductStats]]:
        reviews: list[ScrapedReview] = []

        try:
            if page.locator(SEL["reviews_tab"]).count() > 0:
                page.locator(SEL["reviews_tab"]).first.click()
                page.wait_for_timeout(1500)
        except Exception as exc:  # noqa: BLE001
            log.warning(f"[meesho] Could not click the reviews tab: {exc}")

        stats = self._extract_stats(page)

        for _ in range(SEL["scroll_iterations"]):
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(800)

        cards = page.locator(SEL["review_card"])
        count = min(cards.count(), 100)
        for i in range(count):
            card = cards.nth(i)
            try:
                rating = card.locator(SEL["rating_stars"]).count()
                if not (1 <= rating <= 5):
                    continue
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
                    review_title="",
                    review_text=_safe_text(SEL["review_text"]),
                    review_date_raw=_safe_text(SEL["review_date"]),
                )
            )

        return reviews, stats

    def _extract_stats(self, page) -> Optional[ScrapedProductStats]:
        try:
            rating_text = page.locator(SEL["overall_rating"]).first.inner_text(timeout=3000)
            overall_rating = float(re.search(r"[\d.]+", rating_text).group())
        except Exception:
            log.warning("[meesho] Could not read overall rating.")
            return None

        try:
            total_text = page.locator(SEL["total_reviews"]).first.inner_text(timeout=3000)
            digits = re.sub(r"[^\d]", "", total_text)
            total_reviews = int(digits) if digits else 0
        except Exception:
            total_reviews = 0

        return ScrapedProductStats(overall_rating=overall_rating, total_reviews=total_reviews)
