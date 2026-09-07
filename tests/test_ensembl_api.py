from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import pytest
import requests

import ensembl_api
from ensembl_api import (
    MAX_RETRIES,
    _parse_retry_after,
    _retry_delay_seconds,
    build_batches,
    fetch_variants,
)


def test_build_batches_splits_rows_into_fixed_size_chunks():
    rows = [{"rsid": f"rs{i}"} for i in range(5)]

    batches = build_batches(rows, batch_size=2)

    assert batches == [
        [{"rsid": "rs0"}, {"rsid": "rs1"}],
        [{"rsid": "rs2"}, {"rsid": "rs3"}],
        [{"rsid": "rs4"}],
    ]


def test_build_batches_empty_input():
    assert build_batches([], batch_size=200) == []


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload if payload is not None else {"rs1": {"mappings": []}}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


@pytest.fixture
def fake_post(monkeypatch):
    """Replace the shared session's post() with a scripted sequence of
    responses/exceptions, and make retry sleeps instant. Returns the list of
    delays that were slept, so backoff is observable."""
    slept = []
    monkeypatch.setattr(ensembl_api.time, "sleep", slept.append)

    def install(*results):
        calls = []
        remaining = list(results)

        def post(*args, **kwargs):
            calls.append(kwargs)
            result = remaining.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(ensembl_api._session, "post", post)
        return calls, slept

    return install


def test_fetch_variants_returns_payload_without_retrying(fake_post):
    payload = {"rs1": {"mappings": [{"assembly_name": "GRCh37"}]}}
    calls, slept = fake_post(FakeResponse(payload=payload))

    assert fetch_variants("https://example.test/", ["rs1"]) == payload
    assert len(calls) == 1
    assert slept == []


@pytest.mark.parametrize("status_code", [429, 500, 502, 503, 504])
def test_fetch_variants_retries_retryable_statuses_then_succeeds(
    fake_post, status_code
):
    payload = {"rs1": {"mappings": []}}
    calls, _ = fake_post(
        FakeResponse(status_code=status_code), FakeResponse(payload=payload)
    )

    assert fetch_variants("https://example.test/", ["rs1"]) == payload
    assert len(calls) == 2


@pytest.mark.parametrize(
    "error",
    [
        requests.ConnectionError("connection reset"),
        requests.Timeout("read timed out"),
    ],
)
def test_fetch_variants_retries_transport_errors_then_succeeds(fake_post, error):
    payload = {"rs1": {"mappings": []}}
    calls, _ = fake_post(error, FakeResponse(payload=payload))

    assert fetch_variants("https://example.test/", ["rs1"]) == payload
    assert len(calls) == 2


def test_fetch_variants_does_not_retry_client_errors(fake_post):
    # A 400 means the request itself is wrong; repeating it can only fail again.
    calls, slept = fake_post(FakeResponse(status_code=400))

    with pytest.raises(requests.HTTPError):
        fetch_variants("https://example.test/", ["rs1"])
    assert len(calls) == 1
    assert slept == []


def test_fetch_variants_gives_up_after_max_retries(fake_post):
    calls, slept = fake_post(*[FakeResponse(status_code=503)] * MAX_RETRIES)

    with pytest.raises(requests.HTTPError):
        fetch_variants("https://example.test/", ["rs1"])
    assert len(calls) == MAX_RETRIES
    assert len(slept) == MAX_RETRIES - 1


def test_fetch_variants_reraises_transport_error_on_last_attempt(fake_post):
    calls, _ = fake_post(*[requests.ConnectionError("down")] * MAX_RETRIES)

    with pytest.raises(requests.ConnectionError):
        fetch_variants("https://example.test/", ["rs1"])
    assert len(calls) == MAX_RETRIES


def test_fetch_variants_backs_off_exponentially(fake_post):
    _, slept = fake_post(*[FakeResponse(status_code=503)] * 3, FakeResponse(payload={}))

    fetch_variants("https://example.test/", ["rs1"])

    assert slept == [2, 4, 8]


def test_fetch_variants_honours_retry_after(fake_post):
    _, slept = fake_post(
        FakeResponse(status_code=429, headers={"Retry-After": "7"}),
        FakeResponse(payload={}),
    )

    fetch_variants("https://example.test/", ["rs1"])

    assert slept == [7]


def test_fetch_variants_captures_headers_only_when_asked(fake_post):
    fake_post(FakeResponse(headers={"X-RateLimit-Remaining": "42", "Server": "nginx"}))

    fetch_variants("https://example.test/", ["rs1"], capture_headers=True)

    assert ensembl_api.get_rate_limit_info() == {"X-RateLimit-Remaining": "42"}


def test_parse_retry_after_accepts_seconds():
    assert _parse_retry_after("7") == 7.0
    assert _parse_retry_after("0") == 0.0


def test_parse_retry_after_accepts_http_date():
    # HTTP allows Retry-After to be a date; parsing it as an int used to raise
    # ValueError and take the whole run down with it.
    retry_at = datetime.now(UTC) + timedelta(seconds=30)

    seconds = _parse_retry_after(format_datetime(retry_at))

    assert seconds == pytest.approx(30, abs=5)


def test_parse_retry_after_treats_a_past_date_as_no_wait():
    past = datetime.now(UTC) - timedelta(hours=1)
    assert _parse_retry_after(format_datetime(past)) == 0.0


def test_parse_retry_after_returns_none_for_garbage():
    assert _parse_retry_after("soon") is None
    assert _parse_retry_after("") is None


def test_retry_delay_falls_back_to_backoff_when_retry_after_is_unusable():
    response = FakeResponse(status_code=429, headers={"Retry-After": "soon"})
    assert _retry_delay_seconds(1, response) == 2
    assert _retry_delay_seconds(3, response) == 8


def test_retry_delay_is_capped():
    response = FakeResponse(status_code=429, headers={"Retry-After": "99999"})
    assert _retry_delay_seconds(1, response) == ensembl_api.MAX_RETRY_DELAY_SECONDS
    # ...and so is plain exponential backoff, at a high attempt number.
    assert _retry_delay_seconds(20, None) == ensembl_api.MAX_RETRY_DELAY_SECONDS
