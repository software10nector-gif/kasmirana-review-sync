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
import random
from typing import Optional
from urllib.parse import urlparse, parse_qs

try:
    from playwright_stealth import stealth_sync
    _STEALTH_AVAILABLE = True
except ImportError:
    _STEALTH_AVAILABLE = False

from scrapers.base_scraper import BaseScraper, ScrapedProductStats, ScrapedReview
from scrapers.selectors import FLIPKART as SEL
from utils.logger import get_logger

log = get_logger(__name__)

# Same rotation base_scraper.py uses, kept local so this module doesn't
# depend on base_scraper's private constant.
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
]


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

        # NOTE: we deliberately visit every page up to max_review_pages and
        # never break early on "0 new reviews" — confirmed by direct manual
        # inspection that Flipkart's review ordering on this "all reviews"
        # page is NOT stable/chronological across page numbers (a review
        # dated "4 months ago" can appear on a later page than one dated
        # "1 month ago"). An early break on a couple of empty pages was
        # silently skipping genuinely new reviews that just happened to be
        # reshuffled onto a later page in this run's ordering.
        reviews_by_key: dict = {}
        # Confirmed by repeated live runs: pages 1-4 consistently succeed,
        # pages 5+ consistently time out waiting for review content — same
        # boundary every time, regardless of the inter-page delay. That's a
        # per-session page-count signal, not a speed one: a 3-6s delay alone
        # never got past page 4. So every RESTART_EVERY pages we throw away
        # the browser context entirely and open a brand new one (new UA,
        # fresh cookies/storage, re-run the homepage warm-up) before
        # continuing — to Flipkart this looks like a new visitor arriving,
        # not the same session requesting a 5th/6th/7th page in a row.
        RESTART_EVERY = 4
        for page_num in range(1, SEL["max_review_pages"] + 1):
            if page_num > 1:
                # A human clicking through pages doesn't do it every ~1.4s
                # flat — hitting 10 pages back-to-back with no variance is
                # itself a bot signal. A randomized pause between page loads
                # was added after a run got soft-blocked (empty page,
                # missing rating/anchor text) immediately following a prior
                # run that hammered all 10 pages with no gaps.
                page.wait_for_timeout(random.randint(3000, 6000))

            if page_num > 1 and (page_num - 1) % RESTART_EVERY == 0:
                page = self._fresh_session(page)

            url = f"{reviews_page_url}&page={page_num}"
            page.goto(url, wait_until="domcontentloaded")

            # Confirmed via manual testing: page N genuinely has different
            # reviews from page N-1 (this is NOT a "ran out of pages"
            # situation) — but the scraper was sometimes reading stale
            # content before the new page's reviews had rendered, causing
            # false "0 new" reports. Wait for the review pattern to actually
            # appear (up to 8s) instead of a blind fixed delay, which is
            # more reliable across a range of real network/render speeds.
            try:
                page.wait_for_function(
                    "document.body.innerText.includes('Verified Purchase')",
                    timeout=8000,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning(f"[flipkart] Page {page_num}: reviews never appeared within 8s: {exc}")
            page.wait_for_timeout(1000)  # let the rest of the list finish rendering

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

        reviews = list(reviews_by_key.values())
        if not reviews:
            # Nothing from pagination — try the small inline preview as a
            # last resort before giving up (and retrying via BaseScraper).
            reviews = self._extract_from_window(body_text)

        return reviews, stats

    def _fresh_session(self, old_page):
        """Closes the current browser context and opens a brand new one
        (new context = new cookies/storage/UA), then does a quick homepage
        warm-up — so the next paginated-page request looks like a fresh
        visitor arriving, not the same session's 5th+ consecutive request."""
        old_context = old_page.context
        browser = old_context.browser
        old_context.close()

        new_context = browser.new_context(
            user_agent=random.choice(_USER_AGENTS),
            viewport={"width": 1366, "height": 900},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
        )
        new_context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-IN', 'en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            window.chrome = { runtime: {} };
            """
        )
        new_page = new_context.new_page()
        if _STEALTH_AVAILABLE:
            stealth_sync(new_page)

        try:
            new_page.goto(self.warmup_url, wait_until="domcontentloaded")
            new_page.mouse.wheel(0, random.randint(300, 700))
            new_page.wait_for_timeout(random.uniform(1500, 3000))
        except Exception as exc:  # noqa: BLE001
            log.warning(f"[flipkart] Fresh-session warm-up failed, continuing anyway: {exc}")

        log.info("[flipkart] Started a fresh browser session for the next batch of pages.")
        return new_page

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
