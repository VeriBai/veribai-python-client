"""Exception hierarchy.

Every failure the API can return is raised as a subclass of :class:`VeriBaiError`,
carrying the machine-readable ``code`` — **branch on ``code``, never on the HTTP
status alone**: several statuses multiplex codes that mean completely different
things (a 409 on ``crear`` is a sharding conflict, on ``anular`` it can be
``ALREADY_CANCELLED``, and on ``clientes/crear`` it is a plan-limit or
self-client conflict).

Two shapes exist on the wire and this module tells them apart:

* an **application error** — JSON with ``code`` and ``message``;
* a **gateway rejection** — API Gateway answers ``403 {"message": "Forbidden"}``
  with *no* ``code`` when the API key is missing, unknown or disabled, and
  ``403 {"message": "Missing Authentication Token"}`` for an unknown path. Those
  are surfaced as :class:`AuthenticationError` and :class:`UnknownRouteError`,
  because reading them as an ordinary permission problem sends people hunting
  for the wrong bug.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class VeriBaiError(Exception):
    """Base class for everything this library raises."""


# --------------------------------------------------------------------------
# Local (no HTTP involved)
# --------------------------------------------------------------------------
class ConfigurationError(VeriBaiError):
    """The client was constructed or used incorrectly."""


class SerializationError(VeriBaiError):
    """A Python value cannot be expressed in the wire format the API demands."""


class ImporteError(SerializationError):
    """An amount cannot be represented as the API's decimal-string format."""


class FechaError(SerializationError):
    """A date or time cannot be represented in the API's format."""


class WebhookSignatureError(VeriBaiError):
    """An inbound webhook delivery failed HMAC verification.

    Treat it as hostile input: do not process the body, and do not log it back
    to the sender.
    """


class VerdictTimeout(VeriBaiError):
    """The authority verdict did not arrive within the time allowed.

    This is **not** a failure of the invoice. The record was accepted by VeriBai;
    the tax authority simply had not answered yet. ``ultimo_estado`` carries the
    last status payload seen, so polling can be resumed later.
    """

    def __init__(self, message: str, ultimo_estado: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.ultimo_estado = ultimo_estado or {}


# --------------------------------------------------------------------------
# Transport (a request was attempted; no usable HTTP response came back)
# --------------------------------------------------------------------------
class TransportError(VeriBaiError):
    """The request could not be completed — DNS, TLS, connection, timeout.

    🚨 A transport error proves **nothing** about whether the server acted. For
    the invoice routes that is survivable, because VeriBai replays an identical
    submission idempotently by (serie, número, fecha); for routes that are not
    identity-idempotent the client deliberately does not retry these.
    """


class TimeoutError(TransportError):
    """The request timed out."""


# --------------------------------------------------------------------------
# API (the server answered)
# --------------------------------------------------------------------------
class APIError(VeriBaiError):
    """An error response from the API.

    Attributes:
        status: HTTP status code.
        code: the API's machine-readable code (``VALIDATION_ERROR``, …), or
            ``None`` for a gateway rejection that carries no ``code`` field.
        message: the API's human-readable message.
        errors: field-named violation strings, present on ``VALIDATION_ERROR``.
            These are human-readable prose — **do not parse them**; branch on
            ``code``.
        payload: the full decoded body, for anything not modelled here.
        request_id: the API Gateway request id, worth quoting to support.
    """

    def __init__(
        self,
        status: int,
        code: Optional[str],
        message: str,
        *,
        errors: Optional[List[str]] = None,
        payload: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ) -> None:
        detail = f"[{status}"
        if code:
            detail += f" {code}"
        detail += f"] {message}"
        super().__init__(detail)
        self.status = status
        self.code = code
        self.message = message
        self.errors = errors or []
        self.payload = payload or {}
        self.request_id = request_id


class ValidationError(APIError):
    """400 — the request body or a parameter was rejected.

    ``errors`` names the offending fields. Note this also covers rules the tax
    authority imposes (AEAT codes appear inside ``errors``), so a 400 can mean
    "your invoice is not legal", not merely "your JSON is wrong".
    """


class AuthenticationError(APIError):
    """The API key is missing, unknown or disabled.

    API Gateway rejects the call before any application code runs, so this
    arrives as a ``403`` with no ``code`` — not the ``401`` you might expect.
    """


class UnknownRouteError(APIError):
    """The path does not exist on this API (gateway ``Missing Authentication Token``)."""


class PaymentRequiredError(APIError):
    """402 — the organisation's billing is suspended. Mutating routes only."""


class ForbiddenError(APIError):
    """403 — the emisor is not yours, or the environment is not in your plan.

    🚨 The body is byte-identical whether the NIF is not yours, does not exist,
    or is inactive. That is deliberate anti-enumeration: do not try to tell the
    cases apart from the response.

    On LIVE it also covers ``REPRESENTATION_PENDING`` — the emisor has not
    signed its representation mandate yet.
    """


class NotFoundError(APIError):
    """404 — the resource does not exist."""


class SubmissionInProgressError(NotFoundError):
    """404 ``SUBMISSION_IN_PROGRESS`` on ``GET …/xml``.

    The invoice exists and is being sent to the authority (or is awaiting its
    answer). The evidence copy served by that endpoint is the document the
    authority actually received, so there is nothing to serve yet. Poll
    ``…/estado`` or retry in a few seconds — this is the machinery working, not
    a missing invoice.
    """


class ConflictError(APIError):
    """409 — the request is well-formed but conflicts with current state."""


class IdentityConflictError(ConflictError):
    """409 ``INVOICE_IDENTITY_CONFLICT``.

    The same (serie, número, fechaExpedicion) was already submitted with a
    *different* ``importeTotal`` or ``tipoFactura``. A retry must be byte-identical;
    a genuinely different invoice needs a new number. ``errors`` names the fields
    that diverged.
    """


class SigningInFlightError(ConflictError):
    """409 ``INVOICE_SIGNING_IN_FLIGHT`` — a rare TicketBAI mid-signature race.

    Transient: the client retries it automatically.
    """


class AlreadyCancelledError(ConflictError):
    """409 ``ALREADY_CANCELLED`` / ``ALREADY_EXISTS`` — a cancellation already exists."""


class ShardingConflictError(ConflictError):
    """409 from Alta capacidad (mega-tenant) routing.

    ``MACHINE_NOT_REGISTERED`` — the ``idMaquina`` sent is not registered for this
    emisor. ``SERIE_OWNED_BY_OTHER_MACHINE`` — the serie is permanently bound to a
    different device. Never raised by ordinary single-chain accounts.
    """


class ClientLimitReachedError(ConflictError):
    """409 ``CLIENT_LIMIT_REACHED`` — the plan's secondary-client cap is full."""


class RateLimitError(APIError):
    """429 — usage-plan throttle or monthly quota exhausted.

    The quota is **per API key**, not per account, and API Gateway sends no
    ``X-RateLimit-*`` headers on success, so this is the only signal. The client
    backs off and retries automatically; ``retry_after`` carries the server's
    hint when it sent one.
    """

    def __init__(self, *args: Any, retry_after: Optional[float] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.retry_after = retry_after


class ServerError(APIError):
    """5xx — something failed on our side."""


class ServiceUnavailableError(ServerError):
    """503 — temporarily unavailable."""


class ShardingUnavailableError(ServiceUnavailableError):
    """503 ``SHARDING_UNAVAILABLE`` — the sharding configuration could not be read.

    Retry-safe by construction: the request is never routed unverified, so
    nothing was signed or recorded.
    """


class ChainContentionError(ServiceUnavailableError):
    """503 ``CHAIN_CONTENTION`` — the emisor's hash chain was under concurrent write.

    Retry-safe: nothing was signed or recorded.
    """


class EnvironmentNotAvailableError(ServiceUnavailableError):
    """503 ``ENVIRONMENT_NOT_AVAILABLE`` — the addressed environment is not deployed.

    Not retryable. As of this release LIVE has never been deployed, so a LIVE
    call can legitimately answer this.
    """


class AeatUnavailableError(ServiceUnavailableError):
    """503 ``AEAT_UNAVAILABLE`` — the AEAT census service is unreachable.

    ``payload`` may still carry a cache-served ``resultados`` subset.
    """


# --------------------------------------------------------------------------
# Mapping
# --------------------------------------------------------------------------

#: Codes on a 500 the API documents as retry-safe: the record was rolled back or
#: never written, so the identical request can be sent again.
RETRY_SAFE_500_CODES = frozenset(
    {
        "RECORD_PERSIST_ERROR",
        "ENQUEUE_ERROR",
        "AWS_SERVICE_ERROR",
        "QR_GENERATION_ERROR",
        "INTERNAL_ERROR",
    }
)

_CODE_MAP: Dict[str, type] = {
    "INVOICE_IDENTITY_CONFLICT": IdentityConflictError,
    "INVOICE_SIGNING_IN_FLIGHT": SigningInFlightError,
    "ALREADY_CANCELLED": AlreadyCancelledError,
    "ALREADY_EXISTS": AlreadyCancelledError,
    "MACHINE_NOT_REGISTERED": ShardingConflictError,
    "SERIE_OWNED_BY_OTHER_MACHINE": ShardingConflictError,
    "CLIENT_LIMIT_REACHED": ClientLimitReachedError,
    "SHARDING_UNAVAILABLE": ShardingUnavailableError,
    "CHAIN_CONTENTION": ChainContentionError,
    "ENVIRONMENT_NOT_AVAILABLE": EnvironmentNotAvailableError,
    "AEAT_UNAVAILABLE": AeatUnavailableError,
    "SUBMISSION_IN_PROGRESS": SubmissionInProgressError,
}

_STATUS_MAP: Dict[int, type] = {
    400: ValidationError,
    401: AuthenticationError,
    402: PaymentRequiredError,
    403: ForbiddenError,
    404: NotFoundError,
    409: ConflictError,
    429: RateLimitError,
}


def error_class(status: int, code: Optional[str]) -> type:
    """Pick the most specific exception class for a (status, code) pair."""
    if code and code in _CODE_MAP:
        return _CODE_MAP[code]
    if status in _STATUS_MAP:
        return _STATUS_MAP[status]
    if status == 503:
        return ServiceUnavailableError
    if status >= 500:
        return ServerError
    return APIError
