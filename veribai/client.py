"""The client façade — one object, both APIs."""

from __future__ import annotations

import os
import warnings
from types import TracebackType
from typing import Any, Optional, Type

import requests

from ._transport import DEFAULT_RETRY, RetryPolicy, Transport
from .config import (
    DEFAULT_TIMEOUT,
    INVOICING_URLS,
    LIVE,
    MANAGEMENT_URL,
    normalize_environment,
)
from .errors import ConfigurationError
from .resources import (
    ClientesRecurso,
    CuentaRecurso,
    CumplimientoRecurso,
    DispositivosRecurso,
    FacturasRecurso,
    NifRecurso,
    RegistrosRecurso,
    RepresentacionRecurso,
    TicketbaiRecurso,
    VerifactuRecurso,
    WebhooksRecurso,
)

VAR_API_KEY = "VERIBAI_API_KEY"
VAR_ENTORNO = "VERIBAI_ENVIRONMENT"


class LiveEnvironmentWarning(UserWarning):
    """Raised once when a client is pointed at LIVE.

    LIVE has never been deployed as of this release, so the production base URL
    is present but unexercised. Silence it with::

        warnings.filterwarnings("ignore", category=veribai.LiveEnvironmentWarning)

    It will be removed in 1.0.0, which is reserved for the first release made
    after LIVE has actually run.
    """


class Client:
    """A VeriBai API client.

    One API key authenticates both physical APIs, and this object wires both:
    the **Invoicing API**, where the base URL *is* the environment, and the
    **Management API**, one gateway that resolves the environment from the key.

    The environment defaults to TEST. That is deliberate — the cost of
    accidentally invoicing in the sandbox is a wasted test, and the cost of
    accidentally invoicing in production is a legally filed tax record.

        >>> import veribai
        >>> client = veribai.Client(api_key="...")              # sandbox
        >>> client = veribai.Client(api_key="...", environment="live")

    With no ``api_key`` the ``VERIBAI_API_KEY`` environment variable is used, and
    ``VERIBAI_ENVIRONMENT`` sets the environment — so the same code moves between
    sandbox and production without an edit.

    Usable as a context manager to close the underlying connection pool::

        with veribai.Client() as client:
            client.cuenta.obtener()
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        environment: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        retry: RetryPolicy = DEFAULT_RETRY,
        session: Optional[requests.Session] = None,
        user_agent: Optional[str] = None,
        invoicing_url: Optional[str] = None,
        management_url: Optional[str] = None,
    ) -> None:
        clave = api_key or os.environ.get(VAR_API_KEY)
        if not clave:
            raise ConfigurationError(
                f"an API key is required: pass api_key=... or set {VAR_API_KEY}"
            )

        nombre_entorno = environment or os.environ.get(VAR_ENTORNO) or "test"
        self._entorno = normalize_environment(nombre_entorno)
        if self._entorno == LIVE:
            warnings.warn(
                "VeriBai LIVE selected. As of this release the production "
                "environment has never been deployed, so calls to api.veribai.com "
                "may answer 503 ENVIRONMENT_NOT_AVAILABLE. Confirm with "
                "client.cuenta.obtener() before invoicing.",
                LiveEnvironmentWarning,
                stacklevel=2,
            )

        self._transport = Transport(
            clave, timeout=timeout, retry=retry, session=session, user_agent=user_agent
        )
        self._invoicing = invoicing_url or INVOICING_URLS[self._entorno]
        self._management = management_url or MANAGEMENT_URL

        # Invoicing API
        self.verifactu = VerifactuRecurso(self._transport, self._invoicing)
        """VeriFactu alta / subsanación / anulación."""
        self.ticketbai = TicketbaiRecurso(self._transport, self._invoicing)
        """TicketBAI alta / subsanación / anulación (signs at ingress)."""
        self.facturas = FacturasRecurso(self._transport, self._invoicing)
        """Registered invoices: list, detail, status, QR, fiscal XML."""
        self.registros = RegistrosRecurso(self._transport, self._invoicing)
        """Submission records — where the authority's own verdict lives."""
        self.cuenta = CuentaRecurso(self._transport, self._invoicing)
        """Key check, plan, billing state and monthly quota."""

        # Management API
        self.nif = NifRecurso(self._transport, self._management)
        """AEAT census validation."""
        self.clientes = ClientesRecurso(self._transport, self._management)
        """Secondary clients — the businesses you invoice for."""
        self.dispositivos = DispositivosRecurso(self._transport, self._management)
        """Alta capacidad device registry."""
        self.representacion = RepresentacionRecurso(self._transport, self._management)
        """Representation mandates (a LIVE gate on invoicing)."""
        self.webhooks = WebhooksRecurso(self._transport, self._management)
        """Webhook subscriptions and client links."""
        self.cumplimiento = CumplimientoRecurso(self._transport, self._management)
        """VeriBai's own compliance documents."""

    # -- introspection ----------------------------------------------------
    @property
    def entorno(self) -> str:
        """``"test"`` or ``"live"`` — the API's own vocabulary."""
        return self._entorno

    @property
    def es_live(self) -> bool:
        return self._entorno == LIVE

    @property
    def invoicing_url(self) -> str:
        return self._invoicing

    @property
    def management_url(self) -> str:
        return self._management

    def comprobar(self) -> Any:
        """One round trip that proves the key, the network and the plan.

        Equivalent to ``client.cuenta.obtener()``; worth running in CI, and not
        worth running on a timer — it spends quota like any other call.
        """
        return self.cuenta.obtener()

    # -- lifecycle --------------------------------------------------------
    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._transport.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"<veribai.Client entorno={self._entorno!r} invoicing={self._invoicing!r}>"


__all__ = ["VAR_API_KEY", "VAR_ENTORNO", "Client", "LiveEnvironmentWarning"]
