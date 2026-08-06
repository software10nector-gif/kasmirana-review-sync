"""
Meesho product-review scraper.

REWRITTEN to use Meesho's own internal review API response instead of
DOM-text scraping. Investigated directly via the browser's network panel:
Meesho's page embeds an initial batch of reviews as server-rendered JSON
(__NEXT_DATA__), then loads more via a real internal endpoint when
"VIEW ALL REVIEWS" is clicked:

    POST https://www.meesho.com/api/v1/products/review_summary

...which returns clean structured JSON (review_id, rating, comments, author,
created date) — no fragile text-pattern parsing needed at all. This is both
more robust AND faster than waiting for/parsing rendered DOM text.

Two independent extraction paths, merged and de-duplicated by review_id:
  1. __NEXT_DATA__ SSR payload — present immediately on page load, before
     any interaction, so it survives even if the click-to-expand step fails.
  2. The review_summary API response — captured by listening for the
     network response Playwright would see anyway when clicking "VIEW ALL
     REVIEWS", giving the full paginated set instead of just the preview.
"""
import json
from typing import Optional

from scrapers.base_scraper import BaseScraper, ScrapedProductStats, ScrapedReview
from scrapers.selectors import MEESHO as SEL
from utils.logger import get_logger

log = get_logger(__name__)

_REVIEW_API_PATTERN = "**/api/v1/products/review_summary*"


class MeeshoScraper(BaseScraper):
    source_slug = "meesho"
    warmup_url = "https://www.meesho.com/"

    def scrape(self, page) -> tuple[list[ScrapedReview], Optional[ScrapedProductStats]]:
        reviews_by_id: dict = {}
        stats: Optional[ScrapedProductStats] = None

        # ---- Path 1: whatever's already embedded in the initial SSR HTML ----
        next_data = self._read_next_data(page)
        if next_data:
            summary_data = self._dig(
                next_data,
                ["props", "pageProps", "initialState", "product", "details", "data", "review_summary", "data"],
            )
            if summary_data:
                stats = self._stats_from_summary(summary_data)
                for r in summary_data.get("reviews", []) or []:
                    self._add_review(reviews_by_id, r)

        # ---- Path 2: capture the real API response when "VIEW ALL REVIEWS" is clicked ----
        try:
            view_all = page.get_by_text(SEL["view_all_reviews_text"], exact=False).first
            if view_all.count() > 0:
                with page.expect_response(_REVIEW_API_PATTERN, timeout=15000) as response_info:
                    view_all.click()
                response = response_info.value
                if response.ok:
                    body = response.json()
                    summary_data = body.get("payload", {}).get("data", body.get("data", {}))
                    if summary_data:
                        stats = self._stats_from_summary(summary_data) or stats
                        for r in summary_data.get("reviews", []) or []:
                            self._add_review(reviews_by_id, r)
        except Exception as exc:  # noqa: BLE001
            log.warning(f"[meesho] Could not capture the review_summary API response: {exc}")

        if not reviews_by_id and not stats:
            # Neither the SSR payload nor the API call yielded anything —
            # genuinely blocked this run. Raise so BaseScraper.run()'s retry
            # gets another attempt at a fresh browser session.
            raise RuntimeError("No review data available from SSR payload or API — page likely blocked.")

        reviews = list(reviews_by_id.values())
        log.info(f"[meesho] Extracted {len(reviews)} review(s) via __NEXT_DATA__/API (not DOM text scraping).")
        return reviews, stats

    def _read_next_data(self, page) -> Optional[dict]:
        try:
            raw = page.locator("#__NEXT_DATA__").inner_text(timeout=5000)
            return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            log.warning(f"[meesho] Could not read __NEXT_DATA__: {exc}")
            return None

    @staticmethod
    def _dig(obj: dict, path: list[str]):
        cur = obj
        for key in path:
            if not isinstance(cur, dict) or key not in cur:
                return None
            cur = cur[key]
        return cur

    def _add_review(self, reviews_by_id: dict, raw: dict) -> None:
        review_id = raw.get("review_id")
        if review_id is None or review_id in reviews_by_id:
            return
        rating = int(raw.get("rating") or 0)
        if not (1 <= rating <= 5):
            return
        author = raw.get("author") or {}
        reviews_by_id[review_id] = ScrapedReview(
            reviewer_name=(author.get("name") or "Anonymous").strip(),
            rating=rating,
            review_title="",
            review_text=(raw.get("comments") or "").strip(),
            review_date_raw=(raw.get("created") or "").strip(),
        )

    def _stats_from_summary(self, summary_data: dict) -> Optional[ScrapedProductStats]:
        avg = summary_data.get("average_rating")
        count = summary_data.get("review_count")
        if avg is None:
            return None
        return ScrapedProductStats(overall_rating=float(avg), total_reviews=int(count or 0))
