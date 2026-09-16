"""The invoice read surface — ``GET /v1/facturas*`` on the Invoicing API."""

from __future__ import annotations

import base64
import binascii
import os
import time
from typing import Any, Dict, Iterator, Optional, Union
from urllib.parse import quote

from ..errors import VerdictTimeout
from ..models import Verdicto
from ..pagination import Pagina, construir_pagina, iterar_paginas
from ..serialization import fecha as _fecha
from ..serialization import limpiar
from ._base import Recurso

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class FacturasRecurso(Recurso):
    """Read registered invoices, their status, their QR and their fiscal XML.

    Every read is emisor-scoped: ``nif_emisor`` is required, and a NIF that is
    not yours answers ``403`` with a body byte-identical to the one you would get
    for a NIF that does not exist. That sameness is deliberate anti-enumeration —
    do not try to tell the cases apart.
    """

    def listar(
        self,
        nif_emisor: str,
        *,
        fecha_inicio: Optional[str] = None,
        fecha_fin: Optional[str] = None,
        estado: Optional[str] = None,
        sistema_fiscal: Optional[str] = None,
        limite: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> Pagina:
        """One page of registered invoices (``GET /v1/facturas``).

        ``fecha_inicio``/``fecha_fin`` are ISO-8601 bounds on the **registration**
        date — not the issue date. A value above the maximum ``limite`` is capped
        rather than refused; a non-integer or non-positive one is a 400.
        """
        params = limpiar(
            {
                "nifEmisor": nif_emisor,
                "fechaInicio": fecha_inicio,
                "fechaFin": fecha_fin,
                "estado": estado,
                "sistemaFiscal": sistema_fiscal,
                "limite": limite,
                "cursor": cursor,
            }
        )
        return construir_pagina(self._get("/v1/facturas", params=params).datos, "facturas")

    def iterar(
        self,
        nif_emisor: str,
        *,
        max_paginas: Optional[int] = None,
        **filtros: Any,
    ) -> Iterator[Dict[str, Any]]:
        """Walk every page of :meth:`listar`, yielding invoices.

        Remember the monthly quota is per API key: one page is one call.
        """
        return iterar_paginas(
            lambda cursor: self.listar(nif_emisor, cursor=cursor, **filtros),
            max_paginas=max_paginas,
        )

    def obtener(self, id_factura: str, *, nif_emisor: str) -> Dict[str, Any]:
        """One invoice with all its submission records (``GET /v1/facturas/{id}``)."""
        return dict(
            self._get(
                f"/v1/facturas/{quote(str(id_factura), safe='')}",
                params={"nifEmisor": nif_emisor},
            ).datos
        )

    def buscar(
        self,
        *,
        nif_emisor: str,
        numero: str,
        fecha_expedicion: Any,
        serie: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Find an invoice from its identity when you no longer hold ``idFactura``.

        Losing ``idFactura`` otherwise locks you out of ``/qr``, ``/xml``,
        ``/estado`` and the records — this is the way back in, and it returns the
        same envelope as :meth:`obtener`.

        Send ``serie`` and ``numero`` separately, never pre-joined: responses
        report ``numeroFactura`` as their concatenation, so ``serie="A", numero="12"``
        and ``serie="A1", numero="2"`` both read as ``A12`` there while addressing
        different invoices.
        """
        params = limpiar(
            {
                "nifEmisor": nif_emisor,
                "numero": numero,
                "fechaExpedicion": _fecha(fecha_expedicion, campo="fecha_expedicion"),
                "serie": serie,
            }
        )
        return dict(self._get("/v1/facturas/buscar", params=params).datos)

    def estado(self, id_factura: str, *, nif_emisor: str) -> Dict[str, Any]:
        """Current status (``GET /v1/facturas/{id}/estado``) — the polling endpoint."""
        return dict(
            self._get(
                f"/v1/facturas/{quote(str(id_factura), safe='')}/estado",
                params={"nifEmisor": nif_emisor},
            ).datos
        )

    def verdicto(self, id_factura: str, *, nif_emisor: str) -> Verdicto:
        """The status, read as an outcome rather than a bag of fields."""
        return Verdicto.desde(self.estado(id_factura, nif_emisor=nif_emisor))

    def esperar_verdicto(
        self,
        id_factura: str,
        *,
        nif_emisor: str,
        timeout: float = 180.0,
        intervalo: float = 5.0,
        con_detalle: bool = False,
    ) -> Verdicto:
        """Poll until the tax authority has answered.

        A ``200`` from ``crear`` means *accepted for processing*. This waits for
        the real outcome: VeriFactu is submitted by a minute-tick pipeline, so
        allow at least a couple of minutes; TicketBAI usually answers in seconds.

        Args:
            timeout: seconds to wait before giving up. Giving up is not a
                failure of the invoice — see :class:`~veribai.errors.VerdictTimeout`.
            intervalo: seconds between polls. Each poll is one API call against
                your monthly quota, so prefer a webhook for volume.
            con_detalle: also fetch the full invoice, so a rejection arrives with
                the authority's own code and description attached
                (``Verdicto.detalle``). Costs one extra call, and only on the
                terminal poll.

        Raises:
            VerdictTimeout: nothing had been decided yet. ``ultimo_estado``
                carries the last payload so you can resume polling later.
        """
        if intervalo <= 0:
            raise ValueError("intervalo must be positive")
        limite = time.monotonic() + timeout
        ultimo: Dict[str, Any] = {}
        while True:
            ultimo = self.estado(id_factura, nif_emisor=nif_emisor)
            verdicto = Verdicto.desde(ultimo)
            if verdicto.terminal:
                if con_detalle:
                    detalle = self.obtener(id_factura, nif_emisor=nif_emisor)
                    return Verdicto.desde(ultimo, detalle=detalle)
                return verdicto
            restante = limite - time.monotonic()
            if restante <= 0:
                raise VerdictTimeout(
                    f"no authority verdict for {id_factura} after {timeout:.0f}s — "
                    f"last seen estadoEnvio={ultimo.get('estadoEnvio')!r}. The invoice "
                    f"is accepted and still in flight; resume polling later.",
                    ultimo_estado=ultimo,
                )
            time.sleep(min(intervalo, restante))

    def qr(self, id_factura: str, *, nif_emisor: str) -> bytes:
        """The invoice QR as PNG **bytes** (``GET /v1/facturas/{id}/qr``).

        There is a trap here that this method exists to absorb. API Gateway only
        decodes the payload back into bytes when the *request* carries
        ``Accept: image/png``; with the ``*/*`` that curl and most HTTP clients
        send by default, the response is still labelled ``image/png`` but the body
        is the **base64 text** of the PNG — write it to a file and you get an
        image that will not open.

        So: the header is always sent, and the body is checked for the PNG magic
        number and base64-decoded if it is not there. Either way you get bytes
        you can write to disk.

        The image is rendered on demand from the invoice's stored validation URL
        and is byte-identical to the ``qrBase64`` returned when the invoice was
        created.
        """
        respuesta = self._get(
            f"/v1/facturas/{quote(str(id_factura), safe='')}/qr",
            params={"nifEmisor": nif_emisor},
            accept="image/png",
            binario=True,
        )
        contenido = respuesta.datos
        if not isinstance(contenido, (bytes, bytearray)):  # pragma: no cover - defensive
            contenido = bytes(str(contenido), "utf-8")
        return _asegurar_png(bytes(contenido))

    def guardar_qr(
        self, id_factura: str, *, nif_emisor: str, ruta: Union[str, os.PathLike[str]]
    ) -> str:
        """Fetch the QR and write it to ``ruta``. Returns the path written."""
        datos = self.qr(id_factura, nif_emisor=nif_emisor)
        with open(ruta, "wb") as fh:
            fh.write(datos)
        return os.fspath(ruta)

    def xml(self, id_factura: str, *, nif_emisor: str) -> str:
        """The fiscal record as the tax authority received it (``GET …/xml``).

        This is the **evidence copy**, with its transport envelope removed and
        nothing else changed — for TicketBAI the signed document including its
        XAdES signature, for VeriFactu this invoice's registro lifted out of the
        SOAP batch. There is deliberately no fallback to the pre-submission
        working copy, so the answer never depends on *when* you ask.

        While a submission is in flight there is nothing to serve yet and the API
        answers ``404 SUBMISSION_IN_PROGRESS``, raised here as
        :class:`~veribai.errors.SubmissionInProgressError` — a distinct class
        precisely because it does not mean the invoice is missing.
        """
        respuesta = self._get(
            f"/v1/facturas/{quote(str(id_factura), safe='')}/xml",
            params={"nifEmisor": nif_emisor},
            accept="application/xml",
            binario=True,
        )
        return bytes(respuesta.datos).decode("utf-8")


def _asegurar_png(contenido: bytes) -> bytes:
    """Return PNG bytes whether the gateway sent bytes or base64 text."""
    if contenido.startswith(_PNG_MAGIC):
        return contenido
    texto = contenido.strip()
    if texto.startswith(b"data:"):  # tolerate a data URI just in case
        _, _, texto = texto.partition(b",")
    try:
        decodificado = base64.b64decode(texto, validate=True)
    except (binascii.Error, ValueError):
        return contenido  # not base64 either — hand back what we got
    return decodificado if decodificado.startswith(_PNG_MAGIC) else contenido


__all__ = ["FacturasRecurso"]
