"""Shared fixtures.

Everything is mocked at the HTTP boundary with ``responses``. Nothing in the
default suite talks to a VeriBai environment, and nothing anywhere talks to a tax
authority: a real submission signs a document and permanently advances a
taxpayer's hash chain, which is not something a test suite may do by accident.
"""

from __future__ import annotations

import pytest
import responses as responses_lib

import veribai

SANDBOX = "https://sandbox.veribai.com"
MANAGE = "https://manage-api.veribai.com"
API_KEY = "test-key-0000"


@pytest.fixture(autouse=True)
def entorno_limpio(monkeypatch):
    """Unset the VERIBAI_* variables for every test.

    Without this the suite reads the developer's own shell: exporting
    ``VERIBAI_ENVIRONMENT=live`` (which anyone integrating against production
    eventually does) silently turned ``Client(api_key="k")`` into a LIVE client
    and failed four construction tests for a reason nothing in them mentions.
    A test that asserts a default must own the environment that default is read
    from; tests needing a variable set it themselves.
    """
    monkeypatch.delenv("VERIBAI_API_KEY", raising=False)
    monkeypatch.delenv("VERIBAI_ENVIRONMENT", raising=False)


@pytest.fixture
def mock_http():
    """Activate ``responses`` for one test."""
    with responses_lib.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        yield rsps


@pytest.fixture
def client(mock_http):
    """A sandbox client with retries disabled, so tests assert one call at a time."""
    c = veribai.Client(api_key=API_KEY, retry=veribai.RetryPolicy(max_attempts=1))
    yield c
    c.close()


@pytest.fixture
def client_con_reintentos(mock_http, sin_dormir):
    """A client that retries, with the sleeps removed."""
    c = veribai.Client(
        api_key=API_KEY,
        retry=veribai.RetryPolicy(max_attempts=3, backoff_base=0.01, jitter=False),
    )
    c._transport._sleep = sin_dormir
    yield c
    c.close()


@pytest.fixture
def sin_dormir():
    """A ``sleep`` that records what it was asked to wait, without waiting."""
    esperas = []

    def _dormir(segundos):
        esperas.append(segundos)

    _dormir.esperas = esperas  # type: ignore[attr-defined]
    return _dormir


def error(code: str, message: str = "boom", **extra):
    """An application error body."""
    return {"code": code, "message": message, **extra}
