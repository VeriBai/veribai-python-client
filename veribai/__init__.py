"""VeriBai — official Python client.

VeriBai files invoices under Spain's two electronic-invoicing regimes: VeriFactu
(AEAT, state-wide) and TicketBAI (the three Basque foral haciendas). This package
is the programmatic surface of that service.

One thing is worth internalising before anything else. **A 200 from ``crear``
means accepted, not filed.** VeriBai has taken the invoice, validated it, and —
for TicketBAI — already signed it and advanced the taxpayer's hash chain. The tax
authority answers afterwards, and that answer is the one with legal weight. Read
it from :meth:`~veribai.resources.facturas.FacturasRecurso.esperar_verdicto` or,
at volume, from a webhook.

    import veribai

    client = veribai.Client(api_key="...", environment="test")   # sandbox
    respuesta = client.verifactu.crear(factura)
    verdicto = client.facturas.esperar_verdicto(
        respuesta["idFactura"], nif_emisor="B12345674"
    )
    if verdicto.rechazada:
        ...                                          # not filed; correct and resubmit

The environment resolves in one order: the ``environment=`` argument, then the
``VERIBAI_ENVIRONMENT`` variable, then ``"test"``. TEST last-resort is deliberate,
but note the middle step — a bare ``Client(api_key=...)`` is sandbox only while
that variable is unset, so on a surface this dangerous, say which one you mean.
An explicit argument always wins, which is what makes it worth writing.
"""

from __future__ import annotations

try:  # pragma: no cover - trivial
    from importlib.metadata import version

    __version__ = version("veribai")
except Exception:  # pragma: no cover - source checkout without install
    __version__ = "0.0.0.dev0"

from . import webhooks
from ._transport import RetryPolicy
from .client import VAR_API_KEY, VAR_ENTORNO, Client, LiveEnvironmentWarning
from .errors import (
    AeatUnavailableError,
    AlreadyCancelledError,
    APIError,
    AuthenticationError,
    CertificateError,
    ChainContentionError,
    ClientLimitReachedError,
    ConfigurationError,
    ConflictError,
    EnvironmentNotAvailableError,
    FechaError,
    ForbiddenError,
    IdentityConflictError,
    ImporteError,
    NotFoundError,
    PaymentRequiredError,
    RateLimitError,
    RepresentationSigningError,
    SerializationError,
    ServerError,
    ServiceUnavailableError,
    ShardingConflictError,
    ShardingUnavailableError,
    SignatureVerificationError,
    SigningInFlightError,
    SubmissionInProgressError,
    TimeoutError,
    TransportError,
    UnknownRouteError,
    ValidationError,
    VerdictTimeout,
    VeriBaiError,
    WebhookSignatureError,
    XmlPersistError,
)
from .models import Verdicto
from .pagination import Pagina
from .serialization import cantidad, fecha, hora, importe, preparar, tipo

__all__ = [
    "__version__",
    "Client",
    "LiveEnvironmentWarning",
    "RetryPolicy",
    "Verdicto",
    "Pagina",
    "webhooks",
    "VAR_API_KEY",
    "VAR_ENTORNO",
    # serialization helpers
    "importe",
    "cantidad",
    "tipo",
    "fecha",
    "hora",
    "preparar",
    # errors
    "VeriBaiError",
    "ConfigurationError",
    "SerializationError",
    "ImporteError",
    "FechaError",
    "WebhookSignatureError",
    "VerdictTimeout",
    "TransportError",
    "TimeoutError",
    "APIError",
    "ValidationError",
    "SignatureVerificationError",
    "CertificateError",
    "AuthenticationError",
    "UnknownRouteError",
    "PaymentRequiredError",
    "ForbiddenError",
    "NotFoundError",
    "SubmissionInProgressError",
    "ConflictError",
    "IdentityConflictError",
    "SigningInFlightError",
    "AlreadyCancelledError",
    "ShardingConflictError",
    "ClientLimitReachedError",
    "RepresentationSigningError",
    "RateLimitError",
    "ServerError",
    "XmlPersistError",
    "ServiceUnavailableError",
    "ShardingUnavailableError",
    "ChainContentionError",
    "EnvironmentNotAvailableError",
    "AeatUnavailableError",
]
