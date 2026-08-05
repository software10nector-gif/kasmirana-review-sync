"""
Pushes cleaned reviews to the WordPress REST endpoint registered by the
ksm-review-sync plugin. WordPress itself is the ONLY persistent store in
this architecture (no database on the scraper side) — its fingerprint
uniqueness check makes repeated pushes of the same review a safe no-op.
"""
from typing import Optional

import requests
from requests.auth import HTTPBasicAuth
from tenacity import retry, stop_after_attempt, wait_exponential

from config import config
from utils.logger import get_logger

log = get_logger(__name__)


class WPSyncError(Exception):
    pass


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=3, max=20))
def push_review(review: dict) -> Optional[int]:
    headers = {"X-KSM-Sync-Secret": config.wp_sync_shared_secret}
    auth = HTTPBasicAuth(config.wp_api_username, config.wp_api_app_password)

    resp = requests.post(config.wp_sync_url, json=review, headers=headers, auth=auth, timeout=20)

    if resp.status_code == 401:
        raise WPSyncError("Unauthorized — check WP_API_APP_PASSWORD / WP_SYNC_SHARED_SECRET")
    if resp.status_code >= 500:
        raise WPSyncError(f"WordPress server error {resp.status_code}: {resp.text[:200]}")
    if resp.status_code >= 400:
        log.error(f"WordPress rejected review (client error {resp.status_code}): {resp.text[:200]}")
        return None

    return resp.json().get("id")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=3, max=20))
def push_stats(source_slug: str, overall_rating: float, total_reviews: int) -> bool:
    headers = {"X-KSM-Sync-Secret": config.wp_sync_shared_secret}
    auth = HTTPBasicAuth(config.wp_api_username, config.wp_api_app_password)

    resp = requests.post(
        config.wp_stats_url,
        json={"source_slug": source_slug, "overall_rating": overall_rating, "total_reviews": total_reviews},
        headers=headers,
        auth=auth,
        timeout=20,
    )
    if resp.status_code >= 500:
        raise WPSyncError(f"WordPress server error {resp.status_code}")
    return resp.status_code < 300
