"""
Shared HTTP helper: fetches a URL, caches the raw HTML to disk, and is
polite about request pacing. All scrapers should go through get_html()
instead of calling requests directly, so caching/rate-limiting stay
consistent in one place.
"""

import hashlib
import time

import requests

from config import CACHE_DIR, REQUEST_DELAY_SECONDS, REQUEST_HEADERS, USE_CACHE

_last_request_time = 0.0


def _cache_path(url: str):
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return CACHE_DIR / f"{digest}.html"


def get_html(url: str, force_refresh: bool = False) -> str:
    """Fetch a URL's HTML, using an on-disk cache keyed by URL hash.

    Set force_refresh=True or config.USE_CACHE=False to bypass the cache
    and re-download.
    """
    global _last_request_time

    path = _cache_path(url)
    if USE_CACHE and not force_refresh and path.exists():
        return path.read_text(encoding="utf-8")

    # Simple rate limiter -- don't hammer the source site.
    elapsed = time.time() - _last_request_time
    if elapsed < REQUEST_DELAY_SECONDS:
        time.sleep(REQUEST_DELAY_SECONDS - elapsed)

    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    _last_request_time = time.time()
    resp.raise_for_status()
    resp.encoding = "utf-8"

    path.write_text(resp.text, encoding="utf-8")
    return resp.text


def strip_comments(html: str) -> str:
    """Basketball-Reference hides some tables inside HTML comments to
    thwart naive scrapers/copy-paste. Un-commenting before parsing is the
    standard workaround. Safe to call even if a page has no comments.
    """
    return html.replace("<!--", "").replace("-->", "")
