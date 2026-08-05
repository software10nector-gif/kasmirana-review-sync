"""
ALL CSS selectors for both marketplaces live here, in one place, so that
when Flipkart or Meesho changes their page layout (which happens often),
you only need to edit this ONE file — not touch any scraper logic.

HOW TO UPDATE A SELECTOR WHEN SCRAPING BREAKS:
1. Open the real product page in Chrome.
2. Right-click the piece of text you want (e.g. a reviewer's name) -> Inspect.
3. In DevTools, right-click the highlighted HTML element -> Copy -> Copy selector.
4. Paste it into the matching constant below.
5. Test with:  HEADLESS=false python main.py --source flipkart
"""

FLIPKART = {
    # Link that opens the full "all reviews" page (product page only shows 2-3 samples)
    "all_reviews_link": "a:has-text('All') >> nth=0",

    # One review card, repeated for every review on the page
    "review_card": "div._27M-vq, div.col.EPCmJX",

    # Inside a review card:
    "rating_badge": "div._3LWZlK",          # small green pill showing "5"
    "review_title": "p._2-N8zT",
    "review_text": "div.t-ZTKy div div",
    "reviewer_name": "p._2sc7ZR._2V5EHH",
    "review_date": "p._2sc7ZR",

    # Page-level (not inside a card):
    "overall_rating": "div._3LWZlK._3uYEd6",   # big number e.g. "4.3" near the top
    "total_reviews": "span._2_R_DZ span",       # "12,345 Ratings & 1,234 Reviews"
}

MEESHO = {
    "reviews_tab": "text=Ratings & Reviews",

    "review_card": "div[class*='ReviewCard']",

    "rating_stars": "div[class*='StarRating'] svg[class*='filled']",
    "review_text": "p[class*='review-text'], span[class*='ReviewText']",
    "reviewer_name": "span[class*='reviewer-name'], p[class*='UserName']",
    "review_date": "span[class*='review-date'], p[class*='ReviewDate']",

    "overall_rating": "div[class*='OverallRating'] span",
    "total_reviews": "span[class*='TotalRatingCount']",

    # Meesho lazy-loads more reviews as you scroll down
    "scroll_iterations": 8,
}
