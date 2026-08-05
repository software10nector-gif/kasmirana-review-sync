"""
Meesho product-review scraper.

Extraction is TEXT-PATTERN based (see selectors.py) — Meesho's styled-
components CSS classes are hash-suffixed and get reused across unrelated
elements between builds, confirmed by direct DOM inspection, so they are
not usable as stable selectors.
"""
from typing import Optional

from scrapers.base_scraper import BaseScraper, ScrapedProductStats, ScrapedReview
from scrapers.selectors import MEESHO as SEL
from utils.logger import get_logger

log = get_logger(__name__)


class MeeshoScraper(BaseScraper):
    source_slug = "meesho"

    def scrape(self, page) -> tuple[list[ScrapedReview], Optional[ScrapedProductStats]]:
        # Meesho is a React SPA — a fixed sleep is unreliable (CI machines can
        # be slower than a local browser), so wait for real content to
        # actually appear instead of guessing a duration.
        try:
            page.get_by_text(SEL["section_anchor_text"], exact=False).first.wait_for(
                state="attached", timeout=20000
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(f"[meesho] Reviews section never appeared within 20s: {exc}")

        # Give any late-arriving XHR-populated numbers (rating/review count)
        # a little extra time to settle even after the anchor text shows up.
        page.wait_for_timeout(1500)

        body_text = page.locator("body").inner_text()
        stats = self._extract_stats(body_text)

        # The product page only shows a 2-review preview until this button
        # is clicked, which expands the full list in place (same URL).
        try:
            view_all = page.get_by_text(SEL["view_all_reviews_text"], exact=False).first
            if view_all.count() > 0:
                view_all.click()
                page.wait_for_timeout(2000)
                body_text = page.locator("body").inner_text()
        except Exception as exc:  # noqa: BLE001
            log.warning(f"[meesho] Could not expand full review list, using preview only: {exc}")

        anchor_idx = body_text.find(SEL["section_anchor_text"])
        if anchor_idx == -1:
            log.warning("[meesho] Could not find the reviews section anchor text on the page.")
            return [], stats

        window = body_text[anchor_idx: anchor_idx + SEL["section_window_chars"]]

        reviews: list[ScrapedReview] = []
        seen_in_this_run = set()  # the expand-in-place UI duplicates the 2 preview cards
        for match in SEL["review_pattern"].finditer(window):
            reviewer_name, rating_str, date_raw, text = match.group(1, 2, 3, 4)
            dedup_key = (reviewer_name.strip(), text.strip()[:50])
            if dedup_key in seen_in_this_run:
                continue
            seen_in_this_run.add(dedup_key)

            try:
                rating = round(float(rating_str))
            except ValueError:
                continue

            reviews.append(
                ScrapedReview(
                    reviewer_name=reviewer_name.strip() or "Anonymous",
                    rating=rating,
                    review_title="",
                    review_text=text.strip(),
                    review_date_raw=date_raw.strip(),
                )
            )

        return reviews, stats

    def _extract_stats(self, body_text: str) -> Optional[ScrapedProductStats]:
        rating_match = SEL["overall_rating_pattern"].search(body_text)
        total_match = SEL["total_reviews_pattern"].search(body_text)

        if not rating_match:
            log.warning("[meesho] Could not read overall rating.")
            return None

        overall_rating = float(rating_match.group(1))
        total_reviews = int(total_match.group(2).replace(",", "")) if total_match else 0

        return ScrapedProductStats(overall_rating=overall_rating, total_reviews=total_reviews)
