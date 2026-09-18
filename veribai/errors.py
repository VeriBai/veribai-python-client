"""Exception hierarchy.

Every failure the API can return is raised as a subclass of :class:`VeriBaiError`,
carrying the machine-readable ``code``. **Branch on ``code``, never on the HTTP
status alone**: several statuses multiplex codes that mean completely different
things (a 409 on ``crear`` is a sharding conflict, on ``anular`` it can be
``ALREADY_CANCELLED``, and on ``clientes/crear`` it is a plan-limit or
self-client conflict).

Two shapes exist on the wire and this module tells them apart:

* an **application error**: JSON with ``code`` and ``message``;
* a **gateway rejection**: API Gateway answers ``403 {"message": "Forbidden"}``
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
    """The request could not be completed: DNS, TLS, connection, timeout.

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
            These are human-readable prose, so **do not parse them**; branch on
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
    """400: the request body or a parameter was rejected.

    ``errors`` names the offending fields. Note this also covers rules the tax
    authority imposes (AEAT codes appear inside ``errors``), so a 400 can mean
    "your invoice is not legal", not merely "your JSON is wrong".
    """


class SignatureVerificationError(ValidationError):
    """400 ``SIGNATURE_*``: an uploaded representation PDF did not verify.

    Raised by :meth:`~veribai.resources.representacion.RepresentacionRecurso.verificar`.
    Branch on ``code`` for the reason, because they call for different actions:

    * ``SIGNATURE_CRYPTO_INVALID``: the signature does not validate, the document
      was modified after signing, or it carries no digital signature at all;
    * ``SIGNATURE_UNTRUSTED_CA``: not from a recognised Spanish qualified CA;
    * ``SIGNATURE_REVOKED``: the signing certificate is revoked;
    * ``SIGNATURE_CONTENT_MISMATCH``: the signed text is not the document we
      generated (or no text could be extracted);
    * ``SIGNATURE_COMPANY_NIF_MISMATCH`` / ``SIGNATURE_REP_NIF_MISMATCH``: the
      certificate identifies a different company or representative;
    * ``SIGNATURE_INVALID``: the family's fallback, when nothing more specific fits.
    """


class CertificateError(ValidationError):
    """400 ``CERT_ERROR``: the PKCS#12 could not be loaded.

    Wrong file or wrong password; the API does not distinguish them, on purpose.
    """


class AuthenticationError(APIError):
    """The API key is missing, unknown or disabled.

    API Gateway rejects the call before any application code runs, so this
    arrives as a ``403`` with no ``code``, not the ``401`` you might expect.
    """


class UnknownRouteError(APIError):
    """The path does not exist on this API (gateway ``Missing Authentication Token``)."""


class PaymentRequiredError(APIError):
    """402: the organisation's billing is suspended. Mutating routes only."""


class ForbiddenError(APIError):
    """403: the emisor is not yours, or the environment is not in your plan.

    🚨 The body is byte-identical whether the NIF is not yours, does not exist,
    or is inactive. That is deliberate anti-enumeration: do not try to tell the
    cases apart from the response.

    On LIVE it also covers ``REPRESENTATION_PENDING``: the emisor has not
    signed its representation mandate yet.
    """


class NotFoundError(APIError):
    """404: the resource does not exist."""


class SubmissionInProgressError(NotFoundError):
    """404 ``SUBMISSION_IN_PROGRESS`` on ``GET …/xml``.

    The invoice exists and is being sent to the authority (or is awaiting its
    answer). The evidence copy served by that endpoint is the document the
    authority actually received, so there is nothing to serve yet. Poll
    ``…/estado`` or retry in a few seconds. This is the machinery working, not
    a missing invoice.
    """


class ConflictError(APIError):
    """409: the request is well-formed but conflicts with current state."""


class IdentityConflictError(ConflictError):
    """409 ``INVOICE_IDENTITY_CONFLICT``.

    The same (serie, número, fechaExpedicion) was already submitted with a
    *different* ``importeTotal`` or ``tipoFactura``. A retry must be byte-identical;
    a genuinely different invoice needs a new number. ``errors`` names the fields
    that diverged.
    """


class SigningInFlightError(ConflictError):
    """409 ``INVOICE_SIGNING_IN_FLIGHT``: a rare TicketBAI mid-signature race.

    Transient: the client retries it automatically.
    """


class AlreadyCancelledError(ConflictError):
    """409 ``ALREADY_CANCELLED`` / ``ALREADY_EXISTS``: a cancellation already exists."""


class ShardingConflictError(ConflictError):
    """409 from Alta capacidad (mega-tenant) routing.

    ``MACHINE_NOT_REGISTERED`` means the ``idMaquina`` sent is not registered for this
    emisor. ``SERIE_OWNED_BY_OTHER_MACHINE`` means the serie is permanently bound to a
    different device. Never raised by ordinary single-chain accounts.
    """


class ClientLimitReachedError(ConflictError):
    """409 ``CLIENT_LIMIT_REACHED``: the plan's secondary-client cap is full."""


class RepresentationSigningError(ConflictError):
    """409 ``SIGNING_IN_PROGRESS``: the client cannot be edited mid-signature.

    A representation document has been generated and is out in the world waiting
    for its ``verificar``; editing the row would make the document no longer match
    it. Either wait, or abandon the signing with
    :meth:`~veribai.resources.representacion.RepresentacionRecurso.cancelar_firma`.

    Distinct from :class:`SigningInFlightError`, which is a transient *invoice*
    signing race that this client retries for you. This one needs a decision, so
    it is never retried.
    """


class RateLimitError(APIError):
    """429: usage-plan throttle or monthly quota exhausted.

    The quota is **per API key**, not per account, and API Gateway sends no
    ``X-RateLimit-*`` headers on success, so this is the only signal. The client
    backs off and retries automatically; ``retry_after`` carries the server's
    hint when it sent one.
    """

    def __init__(self, *args: Any, retry_after: Optional[float] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.retry_after = retry_after


class ServerError(APIError):
    """5xx: something failed on our side."""


class ServiceUnavailableError(ServerError):
    """503: temporarily unavailable."""


class ShardingUnavailableError(ServiceUnavailableError):
    """503 ``SHARDING_UNAVAILABLE``: the sharding configuration could not be read.

    Retry-safe by construction: the request is never routed unverified, so
    nothing was signed or recorded.
    """


class ChainContentionError(ServiceUnavailableError):
    """503 ``CHAIN_CONTENTION``: the emisor's hash chain was under concurrent write.

    Retry-safe: nothing was signed or recorded.
    """


class EnvironmentNotAvailableError(ServiceUnavailableError):
    """503 ``ENVIRONMENT_NOT_AVAILABLE``: the addressed environment is not deployed.

    Not retryable. As of this release LIVE has never been deployed, so a LIVE
    call can legitimately answer this.
    """


class AeatUnavailableError(ServiceUnavailableError):
    """503 ``AEAT_UNAVAILABLE``: the AEAT census could not be **reached**.

    ``payload`` may still carry a cache-served ``resultados`` subset.

    Since 2026-09-16 this is scoped to a genuine transport failure, which is what
    makes retrying it meaningful. A NIF the census simply answers *nothing* about
    (the call succeeded, the entry is just absent from the reply) is no longer
    a 503 for the whole batch: it comes back as an ordinary ``200`` with
    ``estado: no_procesado`` for that entry and real verdicts for the rest. Those
    are never cached, so the next call asks again by itself.
    """


class XmlPersistError(ServerError):
    """500 ``XML_PERSIST_ERROR`` (TicketBAI): the signed XML could not be stored.

    🚨 **One code, two very different situations, and only the message separates
    them**, so this class reads the message so you do not have to:

    * on ``subsanar`` / ``anular`` (the ZUZENDU corrected-document paths) nothing
      was signed, sealed or enqueued. The identical retry is safe and is the right
      action; :attr:`reintentable` is ``True`` and the client retries it for you;
    * on ``crear`` the invoice **was** signed and **the hash chain link is sealed**.
      The signature now exists only in the chain row. Retrying does not fix it:
      it answers ``409 INVOICE_SIGNING_IN_FLIGHT`` indefinitely, and the account
      needs operator repair. :attr:`reintentable` is ``False``; contact support
      rather than looping.

    The API team tracks the one-code-for-two-outcomes weakness as ``CERTIFY_LIVE``
    M-32. When it is split into two codes, this heuristic should be replaced by
    the codes themselves.
    """

    #: The API's own wording for the recoverable variant.
    _MARCA_REINTENTABLE = "reintente"

    @property
    def reintentable(self) -> bool:
        """Whether an identical retry can help. See the class docstring."""
        return self._MARCA_REINTENTABLE in (self.message or "").lower()


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
        # Both documented "Retryable" in API_GENERAL.md as of 2026-09-16.
        # DATABASE_ERROR is the most widely raised of the family: 13 handlers
        # across the invoicing read surface and the clients surface.
        "DATABASE_ERROR",
        "AUTH_ERROR",
    }
)

#: Codes on a 500 that no retry can resolve, because the fault is not transient.
#: Retrying these only spends quota to be told the same thing again.
NEVER_RETRY_500_CODES = frozenset(
    {
        # The CloudFront domain is not wired on the Lambda: a deployment fault,
        # not a client one, and it will still be there in 20 seconds.
        "CF_NOT_CONFIGURED",
    }
)

_CODE_MAP: Dict[str, type] = {
    "INVOICE_IDENTITY_CONFLICT": IdentityConflictError,
    "INVOICE_SIGNING_IN_FLIGHT": SigningInFlightError,
    "ALREADY_CANCELLED": AlreadyCancelledError,
    "ALREADY_EXISTS": AlreadyCancelledError,
    "SIGNING_IN_PROGRESS": RepresentationSigningError,
    "XML_PERSIST_ERROR": XmlPersistError,
    "CERT_ERROR": CertificateError,
    "SIGNATURE_INVALID": SignatureVerificationError,
    "SIGNATURE_CRYPTO_INVALID": SignatureVerificationError,
    "SIGNATURE_UNTRUSTED_CA": SignatureVerificationError,
    "SIGNATURE_REVOKED": SignatureVerificationError,
    "SIGNATURE_CONTENT_MISMATCH": SignatureVerificationError,
    "SIGNATURE_COMPANY_NIF_MISMATCH": SignatureVerificationError,
    "SIGNATURE_REP_NIF_MISMATCH": SignatureVerificationError,
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
