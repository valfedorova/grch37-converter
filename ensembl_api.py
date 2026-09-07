import logging
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import requests

from convert import InputRow

logger = logging.getLogger(__name__)

API_URL = "https://grch37.rest.ensembl.org/variation/homo_sapiens/"

# Ensembl's hard limit on ids per POST request to this endpoint.
BATCH_SIZE = 200

MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = 2
REQUEST_TIMEOUT_SECONDS = 30

# A batch that gives up discards the whole run, so retry anything a later
# attempt could plausibly succeed at.
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

# Ceiling on a single wait, so an implausible Retry-After can't park the run.
MAX_RETRY_DELAY_SECONDS = 60

# Shared across requests (and threads) so repeated calls reuse pooled
# connections instead of paying a new TCP/TLS handshake every batch.
# pool_maxsize is sized generously so concurrent threads don't queue up
# waiting for a free connection (requests' default pool is only 10).
_session = requests.Session()
_adapter = requests.adapters.HTTPAdapter(pool_maxsize=50)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)

# Populated from the last batch's response (see fetch_variants'
# capture_headers arg) so callers can report rate-limit usage at the end of
# a run.
_last_response_headers: dict[str, str] = {}


def get_rate_limit_info() -> dict[str, str]:
    """Return any rate-limit-related headers from the last batch's response,
    e.g. X-RateLimit-Limit/-Remaining/-Reset/-Period."""
    return {
        name: value
        for name, value in _last_response_headers.items()
        if "ratelimit" in name.lower()
    }


def build_batches(rows: list[InputRow], batch_size: int) -> list[list[InputRow]]:
    """Split rows into request-sized chunks. `batch_size` should not exceed
    the Ensembl variation endpoint's limit of 200 ids per POST request."""
    return [rows[i : i + batch_size] for i in range(0, len(rows), batch_size)]


def _parse_retry_after(value: str) -> float | None:
    """Interpret a Retry-After header, which HTTP allows to be either a number
    of seconds or a date. Returns None if it is neither."""
    try:
        return max(0.0, float(value))
    except ValueError:
        pass

    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None

    # A date without a timezone is UTC by HTTP's rules.
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())


def _retry_delay_seconds(attempt: int, response: requests.Response | None) -> float:
    """How long to wait before the next attempt: the server's Retry-After if it
    sent a usable one, otherwise exponential backoff."""
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            seconds = _parse_retry_after(retry_after)
            if seconds is not None:
                return min(seconds, MAX_RETRY_DELAY_SECONDS)

    return min(RETRY_BACKOFF_SECONDS * 2 ** (attempt - 1), MAX_RETRY_DELAY_SECONDS)


def fetch_variants(
    api_url: str, rsids: list[str], capture_headers: bool = False
) -> dict:
    for attempt in range(1, MAX_RETRIES + 1):
        is_last_attempt = attempt == MAX_RETRIES

        try:
            response = _session.post(
                api_url,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={"ids": rsids},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as error:
            # Connection resets, timeouts and the like never produce a status
            # code, so they have to be caught rather than inspected.
            if is_last_attempt:
                raise
            reason: object = error
            response = None
        else:
            if response.status_code not in RETRYABLE_STATUS_CODES or is_last_attempt:
                response.raise_for_status()
                if capture_headers:
                    _last_response_headers.clear()
                    _last_response_headers.update(response.headers)
                logger.debug("Fetched %d variant(s)", len(rsids))
                return response.json()
            reason = f"HTTP {response.status_code}"

        delay = _retry_delay_seconds(attempt, response)
        logger.warning(
            "Request failed (%s) (attempt %d/%d), retrying in %.1fs",
            reason,
            attempt,
            MAX_RETRIES,
            delay,
        )
        time.sleep(delay)

    # Unreachable: on the last attempt every path above returns or raises.
    # Present so the declared return type holds for all paths.
    raise AssertionError("fetch_variants exhausted its retry loop without returning")
