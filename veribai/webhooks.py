"""Verifying and parsing the webhook deliveries VeriBai POSTs to your endpoint.

This is the part integrators most often get wrong, and the failure is silent:
the signature is computed over the **raw request bytes**, so deserializing the
JSON and re-serializing it — which almost every framework tempts you into —
produces a different byte string and a signature that will never match.

Delivery is **at-least-once**, and duplicates are normal rather than
exceptional: an endpoint that answers after the 10-second timeout is scored as
failed and retried, up to 3 attempts, then a dead-letter queue; 20 consecutive
failures suspend the webhook. Every retry carries a byte-identical body and the
same ``idEntrega``, which is a deterministic UUIDv5 of (webhook, invoice, event)
— never random. So ``idEntrega`` is a sound deduplication key, and the only one
you need.

Typical use, framework-agnostic::

    entrega = veribai.webhooks.parse_entrega(
        cuerpo=request.body,          # RAW bytes, before any JSON parsing
        cabeceras=request.headers,
        secreto=os.environ["VERIBAI_WEBHOOK_SECRET"],
    )
    if ya_procesado(entrega.id_entrega):   # at-least-once: dedup is your job
        return 200
    ...
"""

from __future__ import annotations

import hmac
import json as _json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Dict, Mapping, Optional, Tuple, Union

from .errors import WebhookSignatureError

CABECERA_FIRMA = "X-VeriBai-Signature"
CABECERA_EVENTO = "X-VeriBai-Event"
CABECERA_ENTREGA = "X-VeriBai-Delivery-Id"
CABECERA_TIMESTAMP = "X-VeriBai-Timestamp"
CABECERA_IDEMPOTENCIA = "Idempotency-Key"

PREFIJO_FIRMA = "sha256="

EVENTOS = ("factura.registrada", "factura.rechazada", "factura.anulada")


@dataclass(frozen=True)
class MotivoRechazo:
    """The tax authority's own verdict on a rejected record — not VeriBai's.

    Act on ``codigo``: fix the data and resubmit through ``subsanar``. VeriBai
    never auto-retries a rejected record, because the correction is a fiscal
    decision.
    """

    codigo: str
    descripcion: str
    motivos_adicionales: Tuple[MotivoRechazo, ...] = ()

    @classmethod
    def desde(cls, datos: Mapping[str, Any]) -> MotivoRechazo:
        adicionales = datos.get("motivosAdicionales") or []
        return cls(
            codigo=str(datos.get("codigo", "")),
            descripcion=str(datos.get("descripcion", "")),
            motivos_adicionales=tuple(
                cls(codigo=str(m.get("codigo", "")), descripcion=str(m.get("descripcion", "")))
                for m in adicionales
                if isinstance(m, Mapping)
            ),
        )


@dataclass(frozen=True)
class Entrega:
    """One verified webhook delivery."""

    evento: str
    id_entrega: str
    timestamp: str
    datos: Dict[str, Any]
    cuerpo: bytes

    @property
    def clave_dedup(self) -> str:
        """The key to deduplicate on. Identical across every retry of this delivery."""
        return self.id_entrega

    @property
    def nif_emisor(self) -> Optional[str]:
        valor = self.datos.get("nifEmisor")
        return str(valor) if valor is not None else None

    @property
    def id_factura(self) -> Optional[str]:
        valor = self.datos.get("idFactura")
        return str(valor) if valor is not None else None

    @property
    def sistema_fiscal(self) -> Optional[str]:
        valor = self.datos.get("sistemaFiscal")
        return str(valor) if valor is not None else None

    @property
    def registrada(self) -> bool:
        """The authority accepted the invoice."""
        return self.evento == "factura.registrada"

    @property
    def rechazada(self) -> bool:
        """The authority REJECTED the record terminally — it is **not** filed.

        The filing obligation is the taxpayer's, which is why this event cannot
        be excluded from a webhook subscription.
        """
        return self.evento == "factura.rechazada"

    @property
    def anulada(self) -> bool:
        """A cancellation was accepted."""
        return self.evento == "factura.anulada"

    @property
    def motivo_rechazo(self) -> Optional[MotivoRechazo]:
        """Why the authority rejected it — present on ``factura.rechazada`` only."""
        crudo = self.datos.get("motivoRechazo")
        if isinstance(crudo, Mapping):
            return MotivoRechazo.desde(crudo)
        return None


def _a_bytes(cuerpo: Union[bytes, bytearray, str]) -> bytes:
    if isinstance(cuerpo, (bytes, bytearray)):
        return bytes(cuerpo)
    if isinstance(cuerpo, str):
        # Accepted as a convenience, but only the bytes your framework received
        # are guaranteed to verify: a JSON round-trip changes them.
        return cuerpo.encode("utf-8")
    raise WebhookSignatureError(
        f"the body must be the raw bytes of the request, got {type(cuerpo).__name__}"
    )


def firma_esperada(secreto: str, cuerpo: Union[bytes, str]) -> str:
    """Compute the signature VeriBai would send for this body.

    Exposed mainly so tests can build a valid delivery without hand-rolling HMAC.
    """
    digest = hmac.new(secreto.encode("utf-8"), _a_bytes(cuerpo), sha256).hexdigest()
    return f"{PREFIJO_FIRMA}{digest}"


def verificar_firma(secreto: str, cuerpo: Union[bytes, str], firma: Optional[str]) -> None:
    """Verify ``X-VeriBai-Signature`` over the raw body.

    Raises:
        WebhookSignatureError: if the header is absent, malformed, or does not
            match. Comparison is constant-time.
    """
    if not secreto:
        raise WebhookSignatureError("a webhook secret is required to verify a delivery")
    if not firma:
        raise WebhookSignatureError(f"missing {CABECERA_FIRMA} header")
    if not firma.startswith(PREFIJO_FIRMA):
        raise WebhookSignatureError(
            f"malformed signature {firma!r}: expected '{PREFIJO_FIRMA}<64 hex chars>'"
        )
    if not hmac.compare_digest(firma_esperada(secreto, cuerpo), firma):
        raise WebhookSignatureError(
            "signature mismatch — either the secret is wrong, or the body was "
            "re-serialized before verification (the HMAC covers the RAW bytes, so a "
            "json.loads/json.dumps round-trip invalidates it)"
        )


def _buscar(cabeceras: Mapping[str, Any], nombre: str) -> Optional[str]:
    """Case-insensitive header lookup that works with plain dicts too."""
    obtener = getattr(cabeceras, "get", None)
    if obtener is not None:
        valor = obtener(nombre)
        if valor is not None:
            return str(valor)
    objetivo = nombre.lower()
    for clave, valor in cabeceras.items():
        if str(clave).lower() == objetivo:
            return str(valor)
    return None


def parse_entrega(
    cuerpo: Union[bytes, str],
    cabeceras: Mapping[str, Any],
    *,
    secreto: str,
) -> Entrega:
    """Verify a delivery and return it parsed.

    Args:
        cuerpo: the **raw** request body. Pass the bytes your framework received,
            not a re-serialized dict.
        cabeceras: the request headers (any case-insensitive or plain mapping).
        secreto: the ``secreto`` you set on the webhook.

    Raises:
        WebhookSignatureError: verification failed, or the body is not the JSON
            object VeriBai sends. Nothing is parsed before the signature is
            checked.
    """
    crudo = _a_bytes(cuerpo)
    verificar_firma(secreto, crudo, _buscar(cabeceras, CABECERA_FIRMA))

    try:
        datos = _json.loads(crudo.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise WebhookSignatureError(f"delivery body is not valid JSON: {exc}") from exc
    if not isinstance(datos, dict):
        raise WebhookSignatureError("delivery body is not a JSON object")

    return Entrega(
        evento=str(datos.get("evento", "")),
        id_entrega=str(datos.get("idEntrega", "")),
        timestamp=str(datos.get("timestamp", "")),
        datos=dict(datos.get("datos") or {}),
        cuerpo=crudo,
    )


__all__ = [
    "CABECERA_ENTREGA",
    "CABECERA_EVENTO",
    "CABECERA_FIRMA",
    "CABECERA_IDEMPOTENCIA",
    "CABECERA_TIMESTAMP",
    "EVENTOS",
    "Entrega",
    "MotivoRechazo",
    "firma_esperada",
    "parse_entrega",
    "verificar_firma",
]
