"""
Entry point run by GitHub Actions. One invocation = one full sync cycle:

    1. Scrape Flipkart + Meesho (fresh headless browser each time)
    2. Clean / validate each review
    3. Write every valid 4-5 star review + updated stats to docs/reviews.json
       (merged with whatever was already there from previous runs)
    4. The GitHub Actions workflow commits that file back to the repo, where
       GitHub Pages serves it publicly; WordPress PULLS it on its own
       schedule (see wordpress-plugin/.../class-ksm-review-github-puller.php)
       — this sidesteps Hostinger's edge blocking inbound POSTs from GitHub
       Actions IPs, since WordPress is now the one making the request.
    5. Exit non-zero on failure so the GitHub Actions run shows red/failed

Usage:
    python main.py                  # run both sources
    python main.py --source flipkart
    python main.py --source meesho
"""
import argparse
import sys

from config import config, validate_config
from json_export import merge_and_write
from scrapers.flipkart_scraper import FlipkartScraper
from scrapers.meesho_scraper import MeeshoScraper
from utils.logger import get_logger
from utils.sanitize import clean_review

log = get_logger(__name__)

SCRAPERS = {
    "flipkart": lambda: FlipkartScraper(config.flipkart_product_url),
    "meesho": lambda: MeeshoScraper(config.meesho_product_url),
}


def run_source(source_slug: str, all_reviews: list, all_stats: dict) -> dict:
    """Scrape one source, clean its reviews, append valid ones to all_reviews."""
    summary = {"source": source_slug, "found": 0, "valid": 0, "rejected": 0}

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
            log.warning(f"[{source_slug}] Review rejected ({cleaned.reject_reason}).")
            continue

        if cleaned.rating < config.min_rating_to_sync:
            continue  # only 4-5 star reviews are ever kept, per requirement

        summary["valid"] += 1
        all_reviews.append({
            "source_slug": cleaned.source_slug,
            "reviewer_name": cleaned.reviewer_name,
            "rating": cleaned.rating,
            "review_title": cleaned.review_title or "",
            "review_text": cleaned.review_text or "",
            "review_date": cleaned.review_date_parsed.isoformat() if cleaned.review_date_parsed else None,
        })

    if stats:
        all_stats[source_slug] = {
            "overall_rating": stats.overall_rating,
            "total_reviews": stats.total_reviews,
        }

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
    all_reviews: list[dict] = []
    all_stats: dict[str, dict] = {}

    for source_slug in sources:
        try:
            summaries.append(run_source(source_slug, all_reviews, all_stats))
        except Exception:  # noqa: BLE001 — one source failing shouldn't stop the other
            log.exception(f"[{source_slug}] Sync failed entirely for this source.")
            overall_ok = False
            summaries.append({"source": source_slug, "found": 0, "valid": 0, "rejected": 0, "error": True})

    added = merge_and_write(all_reviews, all_stats)

    log.info("========== RUN SUMMARY ==========")
    for s in summaries:
        log.info(
            f"{s['source']:10} | found={s['found']:3} valid={s['valid']:3} rejected={s['rejected']:3}"
        )
    log.info(f"new reviews added to docs/reviews.json this run: {added}")
    log.info("==================================")

    return 0 if overall_ok else 2


if __name__ == "__main__":
    sys.exit(main())
