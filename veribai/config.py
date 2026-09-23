"""Environments and base URLs.

There are two physical APIs behind one API key:

* the **Invoicing API**, where the base URL *is* the environment
  (``sandbox.veribai.com`` = TEST, ``api.veribai.com`` = LIVE);
* the **Management API**, a single URL that resolves the environment from
  the key itself, which is why no management call takes an ``entorno``
  parameter.

Both are wired from one :class:`~veribai.client.Client`.
"""

from __future__ import annotations

from typing import Dict

#: The API's own vocabulary for the two environments (the ``entorno`` field).
TEST = "test"
LIVE = "live"

#: Accepted aliases, so ``environment="sandbox"`` works as people expect.
_ALIASES: Dict[str, str] = {
    "test": TEST,
    "sandbox": TEST,
    "pruebas": TEST,
    "live": LIVE,
    "prod": LIVE,
    "production": LIVE,
    "produccion": LIVE,
}

INVOICING_URLS: Dict[str, str] = {
    TEST: "https://sandbox.veribai.com",
    LIVE: "https://api.veribai.com",
}

#: One URL for both environments.
MANAGEMENT_URL = "https://manage-api.veribai.com"

DEFAULT_TIMEOUT = 30.0
"""Seconds. Generous because TicketBAI signs and seals the hash chain
synchronously at ingress: ``crear`` is not a cheap write."""


def normalize_environment(environment: str) -> str:
    """Map a user-supplied environment name onto ``test`` or ``live``.

    Raises:
        ValueError: if the name is not recognised. Deliberately strict, because a typo
            must not silently fall back to LIVE, nor to TEST.
    """
    if not isinstance(environment, str):
        raise ValueError(f"environment must be a string, got {type(environment).__name__}")
    key = environment.strip().lower()
    try:
        return _ALIASES[key]
    except KeyError:
        raise ValueError(
            f"unknown environment {environment!r}; use 'test' (alias 'sandbox') or 'live'"
        ) from None
