"""Small typed views over the parts of the API whose semantics are easy to misread.

Everything else is returned as the plain decoded JSON dict. That is deliberate:
the API adds fields (``consumo``, ``modoCadena``, ``idsMaquinaVistos`` all arrived
within one week), and a rigid model would turn an additive server change into a
client-side breakage. Dicts absorb new fields; the classes here exist only where
a wrong reading has a cost.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

#: Lifecycle values that mean the invoice reached a settled state.
ESTADOS_FACTURA_TERMINALES = frozenset({"registrada", "anulada", "rectificada"})

#: Pipeline values that mean the authority has answered, one way or another.
#: ``aceptada_con_errores`` belongs here even though it looks like progress:
#: the record IS filed but carries errors, and it will never change on its own —
#: only a subsanación you send supersedes it.
ESTADOS_ENVIO_TERMINALES = frozenset({"registrada", "rechazada", "aceptada_con_errores"})

#: Still moving. ``desconocido`` is included: it means a verdict we could not
#: parse, not a verdict of "no".
ESTADOS_EN_VUELO = frozenset(
    {
        "pendiente_proceso",
        "pendiente_envio",
        "en_lote",
        "en_cola",
        "procesando",
        "desconocido",
    }
)


@dataclass(frozen=True)
class Verdicto:
    """The outcome of a submission, as read from ``GET /v1/facturas/{id}/estado``.

    🚨 An HTTP ``200`` from ``crear`` means **accepted for processing**, not
    **filed with the tax authority**. The authority answers later — seconds for
    TicketBAI, up to the next minute-tick batch for VeriFactu — and this object is
    that answer. Ground truth is the authority's own response; nothing else.
    """

    id_factura: str
    estado_factura: Optional[str]
    estado_envio: Optional[str]
    sistema_fiscal: Optional[str]
    csv_aeat: Optional[str]
    bruto: Dict[str, Any]
    detalle: Optional[Dict[str, Any]] = None

    @property
    def terminal(self) -> bool:
        """The authority has answered; polling further will not change this."""
        if self.estado_factura in ESTADOS_FACTURA_TERMINALES:
            return True
        return self.estado_envio in ESTADOS_ENVIO_TERMINALES

    @property
    def registrada(self) -> bool:
        """Filed and accepted."""
        return self.estado_factura == "registrada" or self.estado_envio == "registrada"

    @property
    def rechazada(self) -> bool:
        """Rejected. The record is **not** filed; the obligation remains open."""
        return self.estado_envio == "rechazada"

    @property
    def requiere_subsanacion(self) -> bool:
        """Filed, but with errors the authority wants corrected.

        ``aceptada_con_errores``: the record IS on file and will not change by
        itself. Send a subsanación — do not poll for it to resolve.
        """
        return self.estado_envio == "aceptada_con_errores"

    @property
    def anulada(self) -> bool:
        return self.estado_factura == "anulada"

    @classmethod
    def desde(cls, datos: Dict[str, Any], *, detalle: Optional[Dict[str, Any]] = None) -> Verdicto:
        return cls(
            id_factura=str(datos.get("idFactura", "")),
            estado_factura=datos.get("estadoFactura"),
            estado_envio=datos.get("estadoEnvio"),
            sistema_fiscal=datos.get("sistemaFiscal"),
            csv_aeat=datos.get("csvAeat"),
            bruto=datos,
            detalle=detalle,
        )


__all__ = [
    "ESTADOS_ENVIO_TERMINALES",
    "ESTADOS_EN_VUELO",
    "ESTADOS_FACTURA_TERMINALES",
    "Verdicto",
]
