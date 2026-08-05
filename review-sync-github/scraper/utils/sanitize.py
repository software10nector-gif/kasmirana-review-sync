"""
Cleans, validates and fingerprints raw scraped review data before it's sent
to WordPress. The fingerprint is what WordPress uses to silently ignore a
review it has already stored — so re-running the scraper (every 12 hours,
forever) never creates duplicate cards on the site.
"""
import hashlib
import html
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from better_profanity import profanity
from dateutil import parser as dateparser

profanity.load_censor_words()

_PHONE_RE = re.compile(r"(\+?\d[\d\-\s]{8,}\d)")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL_RE = re.compile(r"https?://\S+|www\.\S+")


@dataclass
class CleanReview:
    source_slug: str
    reviewer_name: str
    rating: int
    review_title: Optional[str]
    review_text: Optional[str]
    review_date_raw: Optional[str]
    review_date_parsed: Optional[date]
    fingerprint: str
    is_valid: bool = True
    reject_reason: Optional[str] = None
    warnings: list[str] = field(default_factory=list)


def _strip_html(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _mask_pii(text: str) -> tuple[str, list[str]]:
    warnings = []
    if _PHONE_RE.search(text):
        text = _PHONE_RE.sub("[redacted phone]", text)
        warnings.append("phone_number_redacted")
    if _EMAIL_RE.search(text):
        text = _EMAIL_RE.sub("[redacted email]", text)
        warnings.append("email_redacted")
    if _URL_RE.search(text):
        text = _URL_RE.sub("[redacted link]", text)
        warnings.append("url_redacted")
    return text, warnings


def _parse_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    try:
        return dateparser.parse(raw, fuzzy=True).date()
    except (ValueError, OverflowError):
        return None


def make_fingerprint(source_slug: str, reviewer_name: str, review_text: str, date_raw: str) -> str:
    raw = f"{source_slug}|{reviewer_name.strip().lower()}|{review_text.strip().lower()}|{date_raw.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def clean_review(
    *,
    source_slug: str,
    reviewer_name: str,
    rating: int,
    review_title: str = "",
    review_text: str = "",
    review_date_raw: str = "",
) -> CleanReview:
    reviewer_name = _strip_html(reviewer_name) or "Anonymous"
    review_title = _strip_html(review_title)
    review_text = _strip_html(review_text)

    review_text, pii_warnings = _mask_pii(review_text)
    review_title, title_pii_warnings = _mask_pii(review_title)
    warnings = pii_warnings + title_pii_warnings

    is_valid = True
    reject_reason = None

    if not (1 <= rating <= 5):
        is_valid = False
        reject_reason = f"invalid_rating:{rating}"

    if not review_text or len(review_text) < 3:
        is_valid = False
        reject_reason = (reject_reason + ";empty_text") if reject_reason else "empty_or_too_short_text"

    if profanity.contains_profanity(review_text) or profanity.contains_profanity(review_title):
        is_valid = False
        reject_reason = (reject_reason + ";profanity") if reject_reason else "profanity_detected"

    if len(review_text) > 3000:
        review_text = review_text[:3000].rsplit(" ", 1)[0] + "…"
        warnings.append("truncated_to_3000_chars")

    fingerprint = make_fingerprint(source_slug, reviewer_name, review_text, review_date_raw)

    return CleanReview(
        source_slug=source_slug,
        reviewer_name=reviewer_name,
        rating=max(1, min(5, rating)),
        review_title=review_title or None,
        review_text=review_text or None,
        review_date_raw=review_date_raw or None,
        review_date_parsed=_parse_date(review_date_raw),
        fingerprint=fingerprint,
        is_valid=is_valid,
        reject_reason=reject_reason,
        warnings=warnings,
    )
