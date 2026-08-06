"""
Writes scraped reviews + stats to docs/reviews.json instead of pushing them
to WordPress directly.

WHY: Hostinger's own edge/CDN blocks inbound POST requests from GitHub
Actions' datacenter IPs to kasmirana.com — confirmed by testing the exact
same request from a normal machine (succeeds) vs from a GitHub Actions job
(403, no WordPress-level error, blocked before even reaching WP). There is
no self-service toggle for this in Hostinger's hPanel.

Sidestepping it: instead of GitHub PUSHING to WordPress (the blocked
direction), WordPress PULLS this file from GitHub Pages on its own schedule
via WP-Cron (see wordpress-plugin/.../class-ksm-review-github-puller.php).
Hostinger's edge has no reason to block its own site's outbound requests to
GitHub, so this direction works reliably.

The file is merged (not overwritten) across runs, keyed by a fingerprint, so
a run where only one source succeeds doesn't erase reviews from a previous
run where the other source succeeded.
"""
import hashlib
import json
import os
from datetime import datetime, timezone

from utils.logger import get_logger

log = get_logger(__name__)

_OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "reviews.json")


def _fingerprint(review: dict) -> str:
    # NOT based on review_text: the same review can be scraped twice with
    # different text — once truncated ("...more") from the main product
    # page's small preview, once in full from the paginated all-reviews
    # page — which previously produced two different fingerprints for one
    # real review. reviewer_name + review_date + title is stable across
    # both scrape paths and still distinguishes different reviewers who
    # share Flipkart's generic "Flipkart Customer" display name, since
    # those have different dates/titles.
    raw = (
        f"{review['source_slug']}|{review['reviewer_name'].strip().lower()}|"
        f"{review.get('review_date') or ''}|{(review.get('review_title') or '').strip().lower()}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_existing() -> dict:
    if not os.path.exists(_OUTPUT_PATH):
        return {"reviews": [], "stats": {}}
    try:
        with open(_OUTPUT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("reviews", [])
            data.setdefault("stats", {})
            return data
    except (json.JSONDecodeError, OSError) as exc:
        log.warning(f"Could not read existing {_OUTPUT_PATH}, starting fresh: {exc}")
        return {"reviews": [], "stats": {}}


def merge_and_write(new_reviews: list[dict], new_stats: dict[str, dict]) -> int:
    """
    new_reviews: list of {source_slug, reviewer_name, rating, review_title, review_text, review_date}
    new_stats:   {source_slug: {overall_rating, total_reviews}}
    Returns the count of genuinely NEW reviews added (excluding ones already present).
    """
    data = _load_existing()

    existing_fingerprints = {r["fingerprint"] for r in data["reviews"]}
    added = 0

    for review in new_reviews:
        fp = _fingerprint(review)
        if fp in existing_fingerprints:
            continue
        review_with_fp = {**review, "fingerprint": fp}
        data["reviews"].append(review_with_fp)
        existing_fingerprints.add(fp)
        added += 1

    for source_slug, stat in new_stats.items():
        data["stats"][source_slug] = stat

    data["updated_at"] = datetime.now(timezone.utc).isoformat()

    os.makedirs(os.path.dirname(_OUTPUT_PATH), exist_ok=True)
    with open(_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    log.info(f"Wrote {_OUTPUT_PATH}: {len(data['reviews'])} total review(s), {added} new this run.")
    return added
