"""
Flipkart product-review scraper.

Fetches ALL written reviews (not just the small preview on the main product
page) by paginating through Flipkart's own dedicated "all reviews" page:
    .../product-reviews/{item_id}?pid={pid}&page=N
confirmed by direct inspection to show a genuinely different, larger batch
of reviews per page (~10/page) than the product page's inline preview.

Extraction is TEXT-PATTERN based (see selectors.py) rather than CSS-selector
based, because Flipkart's CSS class names are randomized per-build and are
not stable identifiers — confirmed by direct DOM inspection.
"""
from typing import Optional
from urllib.parse import urlparse, parse_qs

from scrapers.base_scraper import BaseScraper, ScrapedProductStats, ScrapedReview
from scrapers.selectors import FLIPKART as SEL
from utils.logger import get_logger

log = get_logger(__name__)


class FlipkartScraper(BaseScraper):
    source_slug = "flipkart"
    warmup_url = "https://www.flipkart.com/"

    def scrape(self, page) -> tuple[list[ScrapedReview], Optional[ScrapedProductStats]]:
        # Give the page a moment beyond domcontentloaded — the ratings
        # widget is populated by a follow-up XHR, not present at first paint.
        page.wait_for_timeout(2000)

        # The ratings/review widget on Flipkart's product page appears to be
        # lazy-loaded once scrolled into view (confirmed: the page visibly
        # loads fine, but the ratings text is absent from body.inner_text()
        # until this happens) — scroll down a few times, like a real reader
        # would, before reading anything.
        for _ in range(4):
            page.mouse.wheel(0, 1200)
            page.wait_for_timeout(700)
        page.wait_for_timeout(1500)

        body_text = page.locator("body").inner_text()
        stats = self._extract_stats(body_text)

        reviews_page_url = self._build_reviews_page_url(self.product_url)
        if not reviews_page_url:
            log.warning("[flipkart] Could not derive the paginated reviews page URL, "
                        "falling back to the small preview on the main product page.")
            return self._extract_from_window(body_text), stats

        reviews_by_key: dict = {}
        consecutive_empty_pages = 0
        for page_num in range(1, SEL["max_review_pages"] + 1):
            url = f"{reviews_page_url}&page={page_num}"
            page.goto(url, wait_until="domcontentloaded")
            # A single slow page load shouldn't be mistaken for "ran out of
            # pages" — give each page a real chance, and only stop after
            # TWO consecutive empty pages (handles one-off timing hiccups
            # instead of truncating the result set early).
            page.wait_for_timeout(3500)
            page_text = page.locator("body").inner_text()

            found_this_page = 0
            for match in SEL["paginated_review_pattern"].finditer(page_text):
                rating_str, title, text, reviewer_name, date_raw = match.groups()
                try:
                    rating = int(rating_str)
                except ValueError:
                    continue
                key = (reviewer_name.strip(), text.strip()[:60])
                if key in reviews_by_key:
                    continue
                reviews_by_key[key] = ScrapedReview(
                    reviewer_name=reviewer_name.strip() or "Anonymous",
                    rating=rating,
                    review_title=title.strip(),
                    review_text=text.strip(),
                    review_date_raw=date_raw.strip(),
                )
                found_this_page += 1

            log.info(f"[flipkart] Page {page_num}: {found_this_page} new review(s).")
            if found_this_page == 0:
                consecutive_empty_pages += 1
                if consecutive_empty_pages >= 2:
                    break  # ran past the last page
            else:
                consecutive_empty_pages = 0

        reviews = list(reviews_by_key.values())
        if not reviews:
            # Nothing from pagination — try the small inline preview as a
            # last resort before giving up (and retrying via BaseScraper).
            reviews = self._extract_from_window(body_text)

        return reviews, stats

    def _build_reviews_page_url(self, product_url: str) -> Optional[str]:
        parsed = urlparse(product_url)
        if "/p/" not in parsed.path:
            return None
        path = parsed.path.replace("/p/", "/product-reviews/")
        pid = parse_qs(parsed.query).get("pid", [None])[0]
        if not pid:
            return None
        return f"{parsed.scheme}://{parsed.netloc}{path}?pid={pid}"

    def _extract_from_window(self, body_text: str) -> list[ScrapedReview]:
        """Fallback: the ~5-8 review preview embedded on the main product page."""
        anchor_idx = body_text.find(SEL["section_anchor_text"])
        if anchor_idx == -1:
            log.warning("[flipkart] Could not find the reviews section anchor text on the page.")
            return []

        window = body_text[anchor_idx: anchor_idx + SEL["section_window_chars"]]
        reviews = []
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
        return reviews

    def _extract_stats(self, body_text: str) -> Optional[ScrapedProductStats]:
        rating_match = SEL["overall_rating_pattern"].search(body_text)
        total_match = SEL["total_reviews_pattern"].search(body_text)

        if not rating_match:
            log.warning("[flipkart] Could not read overall rating.")
            return None

        overall_rating = float(rating_match.group(1))
        total_reviews = int(total_match.group(1).replace(",", "")) if total_match else 0

        return ScrapedProductStats(overall_rating=overall_rating, total_reviews=total_reviews)
