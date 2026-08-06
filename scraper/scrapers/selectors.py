"""
Extraction patterns for both marketplaces, in ONE place — edit this file,
not the scraper logic, when Flipkart or Meesho changes their page.

Both sites use randomized/hashed CSS class names that change on nearly
every deploy (confirmed by direct inspection: Flipkart classes like
"_1psv1zeb9", Meesho classes like "sc-kFkjun ghANen" are reused across
completely unrelated components and are NOT stable selectors). Because of
that, extraction here is TEXT-PATTERN based (regex over the rendered page
text) rather than CSS-selector based — this is more resilient to internal
markup/class churn, since it only breaks when the actual VISIBLE wording of
a review card changes, not when a build hash changes.

HOW TO UPDATE WHEN SCRAPING BREAKS:
1. Open the real product page in Chrome, scroll to the reviews section.
2. Look at the plain text (Ctrl+A, Ctrl+C the reviews section, or just read
   it) and compare it to the regex pattern below — the pattern is written
   to match line-by-line, in the order the fields actually appear.
3. Adjust the regex to match the new wording/order.
4. Test with: HEADLESS=false python main.py --source flipkart
"""
import re

FLIPKART = {
    # Text used to locate the reviews section on the page (search page body text for this)
    "section_anchor_text": "ratings by",

    # One match per review card. Groups: rating, title, date, text, reviewer_name
    # Real example line-by-line:
    #   5
    #   Highly recommended
    #   2 months ago
    #   Pure 💯
    #   Flipkart Customer
    #   Verified Buyer
    #   3          <- helpful count
    #   1          <- not-helpful count
    "review_pattern": re.compile(
        r"(\d)\n([^\n]+)\n([^\n]*ago)\n([^\n]+)\n([^\n]+)\nVerified Buyer\n(\d+)\n(\d+)"
    ),

    # Overall rating + total count, e.g. "4.1 ... based on 212 ratings by"
    "overall_rating_pattern": re.compile(r"(\d\.\d)\s*\n[^\n]*\nbased on"),
    "total_reviews_pattern": re.compile(r"based on ([\d,]+) ratings"),

    # How far past the section anchor to search for review cards (page text is long)
    "section_window_chars": 6000,

    # ---- Dedicated "all reviews" page (paginated, ~10 reviews/page) ----
    # URL pattern: the product page URL's "/p/" segment becomes
    # "/product-reviews/", keeping only the "pid" query param, then
    # "&page=N" for N = 1, 2, 3... Confirmed by direct inspection: this
    # page shows a genuinely different, larger set of reviews per page
    # than the small preview embedded on the main product page.
    #
    # Real example line-by-line (note: "Verified Purchase" here, NOT
    # "Verified Buyer" like the main product page's preview cards):
    #   5.0
    #   •
    #   Highly recommended
    #   Review for: Quantity 0.5 g
    #   Pure 💯
    #   Flipkart Customer
    #   , Deoband
    #   Helpful for 3        <- "Helpful for N" if it HAS votes, or just
    #   1                       bare "Helpful" (no number) if it has zero —
    #   Verified Purchase       both forms confirmed live; regex below
    #   · 1 month ago           accepts either.
    "paginated_review_pattern": re.compile(
        r"(\d)\.0\n•\n([^\n]+)\nReview for:[^\n]*\n([^\n]+)\n([^\n]+)\n,\s*[^\n]+\n"
        r"Helpful(?: for \d+)?\n(?:\d+\n)?Verified Purchase\n·\s*([^\n]+)"
    ),
    "max_review_pages": 10,
}

MEESHO = {
    "section_anchor_text": "Product Ratings",

    # Real example line-by-line:
    #   Saniya Bablu
    #   5.0
    #   Posted on 6 Feb 2026
    #   बहुत-बहुत bahut achcha hai...
    #   (blank line)
    #   Helpful (10)
    "review_pattern": re.compile(
        r"([^\n]+)\n(\d(?:\.\d)?)\nPosted on ([^\n]+)\n([\s\S]*?)\n\nHelpful \((\d+)\)"
    ),

    # e.g. "4.0\n1709  Ratings,\n829  Reviews"
    "overall_rating_pattern": re.compile(r"(\d\.\d)\n[\d,]+\s*Ratings,"),
    "total_reviews_pattern": re.compile(r"([\d,]+)\s*Ratings,\s*([\d,]+)\s*Reviews"),

    # Button that expands the 2-review preview into the full review list
    "view_all_reviews_text": "VIEW ALL REVIEWS",

    "section_window_chars": 8000,
}
