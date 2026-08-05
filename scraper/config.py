"""
Central configuration loader.

In GitHub Actions, all of these come from repository Secrets (Settings ->
Secrets and variables -> Actions), injected as environment variables by the
workflow file — see .github/workflows/review-sync.yml.

For local testing, copy .env.example to .env and fill it in; python-dotenv
loads it automatically.
"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()  # no-op in GitHub Actions (no .env file there); loads local .env for testing


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Config:
    # WordPress
    wp_base_url: str = os.getenv("WP_BASE_URL", "").rstrip("/")
    wp_rest_endpoint: str = os.getenv("WP_REST_ENDPOINT", "/wp-json/ksm-reviews/v1/sync")
    wp_api_username: str = os.getenv("WP_API_USERNAME", "")
    wp_api_app_password: str = os.getenv("WP_API_APP_PASSWORD", "")
    wp_sync_shared_secret: str = os.getenv("WP_SYNC_SHARED_SECRET", "")

    # Marketplaces
    flipkart_product_url: str = os.getenv("FLIPKART_PRODUCT_URL", "")
    meesho_product_url: str = os.getenv("MEESHO_PRODUCT_URL", "")

    # Behaviour
    min_rating_to_sync: int = int(os.getenv("MIN_RATING_TO_SYNC", "4"))
    headless: bool = _bool("HEADLESS", True)
    request_timeout_ms: int = int(os.getenv("REQUEST_TIMEOUT_MS", "30000"))
    max_reviews_per_run: int = int(os.getenv("MAX_REVIEWS_PER_RUN", "50"))

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_dir: str = os.getenv("LOG_DIR", "./logs")

    @property
    def wp_sync_url(self) -> str:
        return f"{self.wp_base_url}{self.wp_rest_endpoint}"

    @property
    def wp_stats_url(self) -> str:
        return f"{self.wp_base_url}/wp-json/ksm-reviews/v1/stats"


config = Config()


def validate_config() -> list[str]:
    """Returns a list of human-readable problems; empty list = OK to run."""
    problems = []
    if not config.wp_base_url:
        problems.append("WP_BASE_URL not set")
    if not config.wp_api_username:
        problems.append("WP_API_USERNAME not set")
    if not config.wp_api_app_password:
        problems.append("WP_API_APP_PASSWORD not set")
    if not config.wp_sync_shared_secret:
        problems.append("WP_SYNC_SHARED_SECRET not set")
    if not config.flipkart_product_url and not config.meesho_product_url:
        problems.append("Neither FLIPKART_PRODUCT_URL nor MEESHO_PRODUCT_URL is set")
    return problems
