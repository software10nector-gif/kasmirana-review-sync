"""
Flipkart product-review scraper.

Extraction is TEXT-PATTERN based (see selectors.py) rather than CSS-selector
based, because Flipkart's CSS class names are randomized per-build and are
not stable identifiers — confirmed by direct DOM inspection.
"""
from typing import Optional

from scrapers.base_scraper import BaseScraper, ScrapedProductStats, ScrapedReview
from scrapers.selectors import FLIPKART as SEL
from utils.logger import get_logger

log = get_logger(__name__)


class FlipkartScraper(BaseScraper):
    source_slug = "flipkart"

    def scrape(self, page) -> tuple[list[ScrapedReview], Optional[ScrapedProductStats]]:
        # Give the page a moment beyond domcontentloaded — the ratings
        # widget is populated by a follow-up XHR, not present at first paint.
        page.wait_for_timeout(2000)

        body_text = page.locator("body").inner_text()

        stats = self._extract_stats(body_text)

        anchor_idx = body_text.find(SEL["section_anchor_text"])
        if anchor_idx == -1:
            log.warning("[flipkart] Could not find the reviews section anchor text on the page.")
            return [], stats

        window = body_text[anchor_idx: anchor_idx + SEL["section_window_chars"]]

        reviews: list[ScrapedReview] = []
        for match in SEL["review_pattern"].finditer(window):
            rating_str, title, date_raw, text, reviewer_name = match.group(1, 2, 3, 4, 5)
            try:
                rating = int(rating_str)
            except ValueError:
                continue
            reviews.append(
                ScrapedReview(
                    reviewer_name=reviewer_name.strip() or "Anonymous",
                    rating=rating,
                    review_title=title.strip(),
                    review_text=text.strip(),
                    review_date_raw=date_raw.strip(),
                )
            )

        return reviews, stats

    def _extract_stats(self, body_text: str) -> Optional[ScrapedProductStats]:
        rating_match = SEL["overall_rating_pattern"].search(body_text)
        total_match = SEL["total_reviews_pattern"].search(body_text)

        if not rating_match:
            log.warning("[flipkart] Could not read overall rating.")
            return None

        overall_rating = float(rating_match.group(1))
        total_reviews = int(total_match.group(1).replace(",", "")) if total_match else 0

        return ScrapedProductStats(overall_rating=overall_rating, total_reviews=total_reviews)
