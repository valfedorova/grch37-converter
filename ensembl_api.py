import logging
import time

import requests

from convert import InputRow

logger = logging.getLogger(__name__)

API_URL = "https://grch37.rest.ensembl.org/variation/homo_sapiens/"

# Ensembl's hard limit on ids per POST request to this endpoint.
BATCH_SIZE = 200

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2
REQUEST_TIMEOUT_SECONDS = 30

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


def fetch_variants(api_url: str, rsids: list[str], capture_headers: bool = False) -> dict:
    for attempt in range(1, MAX_RETRIES + 1):
        response = _session.post(
            api_url,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            json={"ids": rsids},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

        if response.status_code == 429 and attempt < MAX_RETRIES:
            retry_after = int(
                response.headers.get("Retry-After", RETRY_BACKOFF_SECONDS)
            )
            logger.warning(
                "Rate limited (attempt %d/%d), retrying in %ds",
                attempt,
                MAX_RETRIES,
                retry_after,
            )
            time.sleep(retry_after)
            continue

        response.raise_for_status()
        if capture_headers:
            _last_response_headers.clear()
            _last_response_headers.update(response.headers)
        logger.debug("Fetched %d variant(s)", len(rsids))
        return response.json()
