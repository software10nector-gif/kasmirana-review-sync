"""
Entry point run by GitHub Actions. One invocation = one full sync cycle:

    1. Scrape Flipkart + Meesho (fresh headless browser each time)
    2. Clean / validate each review
    3. Push every valid 4-5 star review straight to WordPress
       (WordPress's own fingerprint check silently skips ones it already has —
       there is no local database here, GitHub Actions runners are thrown
       away after every run, so WordPress is the single source of truth)
    4. Push updated overall-rating / review-count stats
    5. Exit non-zero on failure so the GitHub Actions run shows red/failed
       and (if you set it up) emails you

Usage:
    python main.py                  # run both sources
    python main.py --source flipkart
    python main.py --source meesho
"""
import argparse
import sys

from config import config, validate_config
from scrapers.flipkart_scraper import FlipkartScraper
from scrapers.meesho_scraper import MeeshoScraper
from utils.logger import get_logger
from utils.sanitize import clean_review
from wp_sync import push_review, push_stats

log = get_logger(__name__)

SCRAPERS = {
    "flipkart": lambda: FlipkartScraper(config.flipkart_product_url),
    "meesho": lambda: MeeshoScraper(config.meesho_product_url),
}


def run_source(source_slug: str) -> dict:
    """Scrape one source, clean + push its reviews. Returns a summary dict."""
    summary = {"source": source_slug, "found": 0, "valid": 0, "synced": 0, "rejected": 0}

    scraper = SCRAPERS[source_slug]()
    raw_reviews, stats = scraper.run()
    summary["found"] = len(raw_reviews)

    for raw in raw_reviews[: config.max_reviews_per_run]:
        cleaned = clean_review(
            source_slug=source_slug,
            reviewer_name=raw.reviewer_name,
            rating=raw.rating,
            review_title=raw.review_title,
            review_text=raw.review_text,
            review_date_raw=raw.review_date_raw,
        )

        if not cleaned.is_valid:
            summary["rejected"] += 1
            log.warning(f"[{source_slug}] Review rejected ({cleaned.reject_reason}), not sent to WordPress.")
            continue

        if cleaned.rating < config.min_rating_to_sync:
            continue  # only 4-5 star reviews are ever sent, per requirement

        summary["valid"] += 1

        payload = {
            "source_slug": cleaned.source_slug,
            "reviewer_name": cleaned.reviewer_name,
            "rating": cleaned.rating,
            "review_title": cleaned.review_title,
            "review_text": cleaned.review_text,
            "review_date": cleaned.review_date_parsed.isoformat() if cleaned.review_date_parsed else None,
        }
        wp_id = push_review(payload)
        if wp_id is not None:
            summary["synced"] += 1
        else:
            log.error(f"[{source_slug}] WordPress rejected a valid review — see log above.")

    if stats:
        try:
            push_stats(source_slug, stats.overall_rating, stats.total_reviews)
        except Exception as exc:  # noqa: BLE001
            log.error(f"[{source_slug}] Failed to push stats: {exc}")

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Kasmirana review sync (GitHub Actions edition)")
    parser.add_argument("--source", choices=["flipkart", "meesho", "all"], default="all")
    args = parser.parse_args()

    problems = validate_config()
    if problems:
        for p in problems:
            log.error(f"Config problem: {p}")
        return 1

    sources = ["flipkart", "meesho"] if args.source == "all" else [args.source]

    overall_ok = True
    summaries = []
    for source_slug in sources:
        try:
            summaries.append(run_source(source_slug))
        except Exception:  # noqa: BLE001 — one source failing shouldn't stop the other
            log.exception(f"[{source_slug}] Sync failed entirely for this source.")
            overall_ok = False
            summaries.append({"source": source_slug, "found": 0, "valid": 0, "synced": 0, "rejected": 0, "error": True})

    log.info("========== RUN SUMMARY ==========")
    for s in summaries:
        log.info(
            f"{s['source']:10} | found={s['found']:3} valid={s['valid']:3} "
            f"synced={s['synced']:3} rejected={s['rejected']:3}"
        )
    log.info("==================================")

    return 0 if overall_ok else 2


if __name__ == "__main__":
    sys.exit(main())
