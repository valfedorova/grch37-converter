import logging
import time

import requests

from convert import InputRow

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2
REQUEST_TIMEOUT_SECONDS = 30

# Shared across requests (and threads) so repeated calls reuse pooled
# connections instead of paying a new TCP/TLS handshake every batch.
_session = requests.Session()


def build_batches(rows: list[InputRow], batch_size: int) -> list[list[InputRow]]:
    """Split rows into request-sized chunks. `batch_size` should not exceed
    the Ensembl variation endpoint's limit of 200 ids per POST request."""
    return [rows[i : i + batch_size] for i in range(0, len(rows), batch_size)]


def fetch_variants(api_url: str, rsids: list[str]) -> dict:
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
        logger.debug("Fetched %d variant(s)", len(rsids))
        return response.json()
