"""HTTP transport: one session, one retry policy, one error mapping.

The retry rules here are the reason this package exists rather than a page of
``requests`` snippets, so they are worth stating plainly.

**A status response and a network error are not the same evidence.** A ``429``
or a ``503 SHARDING_UNAVAILABLE`` proves the server refused the request *before*
doing anything, so retrying is always *safe*, though not always *useful*: an
exhausted monthly quota is refused just as cleanly as a burst throttle and will
still be exhausted four attempts later, so only the throttle is retried.
A dropped connection proves nothing:
the invoice may already be signed, chained and queued. Therefore network errors
are retried **only** on routes VeriBai makes idempotent by identity: the invoice
routes, where an identical resubmission replays the original record with ``200``
rather than creating a second one.

That is also why this client does not invent an idempotency key: the
idempotency is the API's, keyed on (serie, número, fechaExpedicion), and it is
what makes a retry safe. Change ``importeTotal`` or ``tipoFactura`` between
attempts and you get ``409 INVOICE_IDENTITY_CONFLICT``, correctly, because that
is a different invoice wearing the same number.

Routes that are *not* identity-idempotent (creating a webhook, registering a
device) are never retried after a network error, because a duplicate would be a
real second object.
"""

from __future__ import annotations

import json as _json
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional

import requests

from . import errors
from .config import DEFAULT_TIMEOUT

_JSON = "application/json"


@dataclass(frozen=True)
class RetryPolicy:
    """How hard to try again, and how long to wait.

    Attributes:
        max_attempts: total attempts including the first. ``1`` disables retries.
        backoff_base: seconds for the first wait; doubles each attempt.
        backoff_max: ceiling for a single wait.
        respect_retry_after: honour a ``Retry-After`` header when the server sends one.
        jitter: spread retries so a fleet of workers does not resynchronise on the
            same second after a throttle.
    """

    max_attempts: int = 4
    backoff_base: float = 0.5
    backoff_max: float = 20.0
    respect_retry_after: bool = True
    jitter: bool = True

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise errors.ConfigurationError("max_attempts must be at least 1")
        if self.backoff_base <= 0 or self.backoff_max <= 0:
            raise errors.ConfigurationError("backoff values must be positive")

    def espera_excesiva(self, retry_after: Optional[float]) -> bool:
        """True when the server's own hint is longer than we are willing to block.

        Silently truncating a ``Retry-After`` to ``backoff_max`` is the wrong
        answer: a server asking for 60 seconds gets a 20-second nap and a second
        rejection. When the hint exceeds what this client will sit on, it stops
        retrying and raises instead, leaving a waiting decision that big to the
        caller, who is the only one who knows whether it is worth making.
        """
        if retry_after is None or not self.respect_retry_after:
            return False
        return float(retry_after) > self.backoff_max

    def espera(self, intento: int, retry_after: Optional[float] = None) -> float:
        """Seconds to wait before attempt ``intento + 1`` (1-based ``intento``).

        A server-sent ``retry_after`` is honoured **as sent**, not clamped; use
        :meth:`espera_excesiva` first to decide whether it is worth waiting at all.
        """
        if retry_after is not None and self.respect_retry_after:
            return float(retry_after)
        base = float(min(self.backoff_base * (2.0 ** (intento - 1)), self.backoff_max))
        if self.jitter:
            # nosec B311 / noqa: S311. This spreads retry timing so a fleet of
            # workers does not resynchronise after a throttle. It protects nothing.
            return base * (0.5 + random.random() / 2)  # noqa: S311
        return base


#: Retries deliberately kept short here; ``crear`` is a fiscal write, not a page load.
DEFAULT_RETRY = RetryPolicy()


@dataclass
class Respuesta:
    """A successful response, decoded."""

    status: int
    datos: Any
    headers: Mapping[str, str] = field(default_factory=dict)
    contenido: bytes = b""


def _decodificar(resp: requests.Response) -> Any:
    if not resp.content:
        return {}
    try:
        return resp.json()
    except ValueError:
        return {"_raw": resp.text}


def _request_id(resp: requests.Response) -> Optional[str]:
    for h in ("x-amzn-RequestId", "x-amzn-requestid", "X-Amzn-Trace-Id", "x-request-id"):
        if h in resp.headers:
            return resp.headers[h]
    return None


def _retry_after(resp: requests.Response) -> Optional[float]:
    valor = resp.headers.get("Retry-After")
    if not valor:
        return None
    try:
        return float(valor)
    except ValueError:
        return None  # HTTP-date form; fall back to exponential backoff


def _es_rechazo_de_gateway(status: int, cuerpo: Any) -> bool:
    """API Gateway's own rejections carry ``message`` and no ``code``."""
    return status == 403 and isinstance(cuerpo, dict) and "code" not in cuerpo


#: API Gateway's wording for an exhausted usage-plan quota. Its throttle says
#: "Too Many Requests" instead, and neither carries a ``code``, so the message is
#: the only thing that separates a burst you should retry from a monthly cap you
#: should not. Matched only when no ``code`` is present, so a future VeriBai-coded
#: 429 is never swept up by a string match.
_MARCADORES_CUOTA = ("limit exceeded", "quota exceeded")


def _es_cuota_agotada(codigo: Optional[str], texto: Optional[str]) -> bool:
    if codigo is not None or not texto:
        return False
    minuscula = texto.lower()
    return any(marcador in minuscula for marcador in _MARCADORES_CUOTA)


def construir_error(resp: requests.Response) -> errors.APIError:
    """Map an error response onto the most specific exception available."""
    cuerpo = _decodificar(resp)
    status = resp.status_code
    rid = _request_id(resp)

    if _es_rechazo_de_gateway(status, cuerpo):
        mensaje = str(cuerpo.get("message", "Forbidden"))
        if "Missing Authentication Token" in mensaje:
            return errors.UnknownRouteError(
                status,
                None,
                "this path does not exist on this API (API Gateway answers "
                "'Missing Authentication Token', not 404, for an unknown route)",
                payload=cuerpo,
                request_id=rid,
            )
        return errors.AuthenticationError(
            status,
            None,
            "the API key is missing, unknown or disabled: API Gateway rejected the "
            "request before it reached VeriBai (this is the gateway's 403, which "
            "carries no 'code' field, not an application permission error)",
            payload=cuerpo,
            request_id=rid,
        )

    codigo = cuerpo.get("code") if isinstance(cuerpo, dict) else None
    texto = cuerpo.get("message") if isinstance(cuerpo, dict) else None
    lista = cuerpo.get("errors") if isinstance(cuerpo, dict) else None
    if not isinstance(lista, list):
        lista = None

    clase = errors.error_class(status, codigo)
    kwargs: Dict[str, Any] = {
        "errors": [str(e) for e in lista] if lista else None,
        "payload": cuerpo if isinstance(cuerpo, dict) else {"_raw": cuerpo},
        "request_id": rid,
    }
    if clase is errors.RateLimitError:
        kwargs["retry_after"] = _retry_after(resp)
        kwargs["cuota_agotada"] = _es_cuota_agotada(codigo, texto)
    return clase(  # type: ignore[no-any-return]
        status,
        codigo,
        str(texto or resp.reason or "request failed"),
        **kwargs,
    )


def _reintentable(err: errors.APIError, idempotente: bool) -> bool:
    """Decide whether an error response may be retried.

    See the module docstring. The short version: a refusal is always safe to
    retry; a partial execution is only safe where the API replays by identity.
    """
    if isinstance(err, errors.RateLimitError):
        # Throttled: nothing ran, and the next second clears it. An exhausted
        # monthly quota also ran nothing, but no wait inside a retry budget of a
        # few seconds will clear it either: retrying just spends the remaining
        # attempts to arrive at the same error later.
        return not err.cuota_agotada
    if isinstance(err, errors.EnvironmentNotAvailableError):
        return False  # LIVE is not deployed; waiting will not deploy it
    if isinstance(err, (errors.ShardingUnavailableError, errors.ChainContentionError)):
        return True  # documented retry-safe: nothing signed, nothing recorded
    if isinstance(err, errors.SigningInFlightError):
        return True  # a mid-signature race; the API says retry in a few seconds
    if isinstance(err, errors.XmlPersistError):
        # One code, two outcomes. On `crear` the invoice is already signed and the
        # chain link sealed, and retrying answers 409 INVOICE_SIGNING_IN_FLIGHT for
        # ever, which this client would then dutifully retry too. Only the variant
        # whose message says nothing was sent may be sent again.
        return err.reintentable
    if err.status in (502, 504):
        return idempotente  # the request may well have run to completion
    if err.status >= 500:
        if err.code in errors.NEVER_RETRY_500_CODES:
            return False  # a deployment fault; it will still be there in 20 seconds
        return idempotente or (err.code in errors.RETRY_SAFE_500_CODES)
    return False


class Transport:
    """Owns the ``requests`` session and applies the retry policy."""

    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        retry: RetryPolicy = DEFAULT_RETRY,
        session: Optional[requests.Session] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        if not api_key or not isinstance(api_key, str):
            raise errors.ConfigurationError("api_key is required and must be a string")
        self._api_key = api_key
        self.timeout = timeout
        self.retry = retry
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "x-api-key": api_key,
                "Accept": _JSON,
                "User-Agent": user_agent or _user_agent(),
            }
        )
        self._sleep = time.sleep  # swapped out in tests

    # -- plumbing ---------------------------------------------------------
    def request(
        self,
        metodo: str,
        base_url: str,
        ruta: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json: Any = None,
        idempotente: bool = False,
        accept: str = _JSON,
        binario: bool = False,
    ) -> Respuesta:
        """Send one request, retrying per the policy, and decode the result.

        Args:
            idempotente: True only for routes VeriBai replays by identity. It is
                what licenses a retry after a *network* error; see the module
                docstring.
            binario: return raw bytes instead of decoded JSON (the QR endpoint).
        """
        url = f"{base_url.rstrip('/')}/{ruta.lstrip('/')}"
        cuerpo = _json.dumps(json, ensure_ascii=False).encode("utf-8") if json is not None else None
        cabeceras: Dict[str, str] = {"Accept": accept}
        if cuerpo is not None:
            cabeceras["Content-Type"] = _JSON

        ultimo: Optional[BaseException] = None
        for intento in range(1, self.retry.max_attempts + 1):
            try:
                resp = self.session.request(
                    metodo,
                    url,
                    params=dict(params) if params else None,
                    data=cuerpo,
                    headers=cabeceras,
                    timeout=self.timeout,
                )
            except requests.Timeout as exc:
                ultimo = errors.TimeoutError(f"{metodo} {ruta} timed out after {self.timeout}s")
                if not idempotente or intento == self.retry.max_attempts:
                    raise ultimo from exc
                self._sleep(self.retry.espera(intento))
                continue
            except requests.RequestException as exc:
                ultimo = errors.TransportError(f"{metodo} {ruta} failed: {exc}")
                if not idempotente or intento == self.retry.max_attempts:
                    raise ultimo from exc
                self._sleep(self.retry.espera(intento))
                continue

            if resp.status_code >= 400:
                err = construir_error(resp)
                sugerido = getattr(err, "retry_after", None)
                if (
                    intento < self.retry.max_attempts
                    and _reintentable(err, idempotente)
                    and not self.retry.espera_excesiva(sugerido)
                ):
                    self._sleep(self.retry.espera(intento, sugerido))
                    continue
                raise err

            return Respuesta(
                status=resp.status_code,
                datos=resp.content if binario else _decodificar(resp),
                headers=resp.headers,
                contenido=resp.content,
            )

        # Unreachable: every branch above returns or raises on the last attempt.
        raise ultimo or errors.TransportError(  # pragma: no cover - defensive
            f"{metodo} {ruta} exhausted retries"
        )

    def close(self) -> None:
        self.session.close()

    def __repr__(self) -> str:
        # Never print the key. Showing a tail is only safe once there is enough
        # key for the tail not to BE the key.
        pista = f"***{self._api_key[-4:]}" if len(self._api_key) > 12 else "***"
        return f"<Transport key={pista} timeout={self.timeout}>"


def _user_agent() -> str:
    from . import __version__

    return f"veribai-python/{__version__}"


__all__ = ["DEFAULT_RETRY", "Respuesta", "RetryPolicy", "Transport", "construir_error"]
