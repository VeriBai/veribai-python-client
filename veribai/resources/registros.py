"""Submission records: ``GET /v1/registros*`` on the Invoicing API."""

from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, Iterator, MutableMapping, Optional, Tuple, Union
from urllib.parse import quote

from ..pagination import Pagina, construir_pagina, iterar_paginas
from ..serialization import instante, limpiar
from ._base import Recurso

Instante = Union[_dt.datetime, str]

#: The answered states a filtered list accepts. ``pendiente``/``procesando`` are
#: a ``400``: unanswered records are not in a filtered list at all.
ESTADOS_VEREDICTO = ("aceptada", "aceptada_con_errores", "rechazada")

ClaveCambio = Tuple[Any, Any, Any]
#: What ``vistos`` holds between polls: each key and the ``envioCompletadoEn``
#: that dates it, so it can be pruned without the records.
Vistos = MutableMapping[ClaveCambio, _dt.datetime]


def clave_cambio(registro: Dict[str, Any]) -> ClaveCambio:
    """The dedup key for the verdict feed: ``(idFactura, idRegistro, estado)``.

    ``idRegistro`` alone is **not** unique: it is unique only within one invoice,
    and invoices of the same emisor created in the same second share it.
    Deduping on it alone silently drops real records.
    """
    return (registro.get("idFactura"), registro.get("idRegistro"), registro.get("estado"))


def _parsear_instante(texto: Any) -> Optional[_dt.datetime]:
    if not isinstance(texto, str) or not texto:
        return None
    try:
        valor = _dt.datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return None
    return valor if valor.tzinfo is not None else None


class CambiosRegistros:
    """One poll of the verdict change feed; see :meth:`RegistrosRecurso.cambios_desde`.

    Iterate it to get the records, then read :attr:`proximo_desde` for the next
    poll. Iterate it once: it is a single walk of the list, not a container.

    :attr:`vistos` maps the :func:`clave_cambio` of each record yielded to its
    ``envioCompletadoEn``, on top of whatever was passed in, so passing it to the
    next poll skips the overlap. When the walk ends it is **pruned** of every key
    dated before :attr:`proximo_desde`: the next poll starts after those, so they
    cannot come back. It therefore holds about one overlap's worth of records,
    however long the poller runs.
    """

    def __init__(
        self,
        paginas: Iterator[Dict[str, Any]],
        desde: _dt.datetime,
        solapamiento: _dt.timedelta,
        vistos: Optional[Vistos] = None,
    ) -> None:
        self._paginas = paginas
        self._desde = desde
        self._solapamiento = solapamiento
        self._maximo: Optional[_dt.datetime] = None
        self.vistos: Vistos = {} if vistos is None else vistos

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        try:
            for registro in self._paginas:
                clave = clave_cambio(registro)
                if clave in self.vistos:
                    continue
                completado = _parsear_instante(registro.get("envioCompletadoEn"))
                if completado is not None and (self._maximo is None or completado > self._maximo):
                    self._maximo = completado
                # A record with no readable timestamp is dated at this poll's bound,
                # so it is still pruned once the feed moves past it.
                self.vistos[clave] = completado if completado is not None else self._desde
                yield registro
        finally:
            self._podar()

    def _podar(self) -> None:
        limite = self.proximo_desde
        for clave in [c for c, instante_ in self.vistos.items() if instante_ < limite]:
            del self.vistos[clave]

    @property
    def proximo_desde(self) -> _dt.datetime:
        """The bound for the next poll: the latest ``envioCompletadoEn`` seen,
        minus the overlap. Unchanged from this poll's bound if nothing came back.

        Never earlier than this poll's bound, so an empty feed does not drift back.
        """
        if self._maximo is None:
            return self._desde
        return max(self._desde, self._maximo - self._solapamiento)


class RegistrosRecurso(Recurso):
    """The per-submission ledger: one record per alta, subsanación or anulación.

    This is where the authority's own verdict lives: ``codigoRespuestaAeat`` and
    its description for VeriFactu, ``codigoRespuestaTbai``/``mensajeRespuestaTbai``
    for TicketBAI. The invoice's ``estado`` tells you *that* something was
    rejected; the record tells you *why*.
    """

    def listar(
        self,
        nif_emisor: str,
        *,
        veredicto_desde: Optional[Instante] = None,
        estado: Optional[str] = None,
        limite: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> Pagina:
        """One page of records (``GET /v1/registros``).

        Plain, it is every record, most recently **created** first. The two
        filters switch it to records by when the authority **answered**, and then
        only answered records appear:

        * ``veredicto_desde``: answers at or after that instant, **oldest answer
          first**. An aware ``datetime`` (a naive one raises
          :class:`~veribai.errors.FechaError`) or an ISO-8601 string with a zone.
          Whole-second precision, inclusive bound.
        * ``estado``: one of :data:`ESTADOS_VEREDICTO`. Alone, newest answer first.

        With ``estado`` a page can hold fewer than ``limite`` records, **even
        zero**, and still carry ``proximaPagina``: only a ``None`` cursor means
        the end. The cursor is bound to the filters that produced it, so send the
        same ones with every page (``400 INVALID_CURSOR`` otherwise).
        """
        params = limpiar(
            {
                "nifEmisor": nif_emisor,
                "veredictoDesde": (
                    None
                    if veredicto_desde is None
                    else instante(veredicto_desde, campo="veredicto_desde")
                ),
                "estado": estado,
                "limite": limite,
                "cursor": cursor,
            }
        )
        return construir_pagina(self._get("/v1/registros", params=params).datos, "registros")

    def iterar(
        self,
        nif_emisor: str,
        *,
        veredicto_desde: Optional[Instante] = None,
        estado: Optional[str] = None,
        limite: Optional[int] = None,
        max_paginas: Optional[int] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Walk every page of :meth:`listar`, resending the same filters each time.

        Short and empty pages do not stop it; only ``proximaPagina: null`` does.
        """
        return iterar_paginas(
            lambda cursor: self.listar(
                nif_emisor,
                veredicto_desde=veredicto_desde,
                estado=estado,
                limite=limite,
                cursor=cursor,
            ),
            max_paginas=max_paginas,
        )

    def cambios_desde(
        self,
        nif_emisor: str,
        desde: _dt.datetime,
        *,
        estado: Optional[str] = None,
        solapamiento: _dt.timedelta = _dt.timedelta(seconds=60),
        limite: Optional[int] = None,
        max_paginas: Optional[int] = None,
        vistos: Optional[Vistos] = None,
    ) -> CambiosRegistros:
        """One poll of the verdict change feed: every answer since ``desde``.

        The pull-side safety net for a missed webhook, not a replacement for
        them. Iterate the result, then keep its :attr:`~CambiosRegistros.proximo_desde`
        for the next poll::

            desde = datetime.now(timezone.utc) - timedelta(hours=1)
            vistos = {}
            while True:
                cambios = client.registros.cambios_desde("B00000000", desde, vistos=vistos)
                for registro in cambios:
                    procesar(registro)
                desde = cambios.proximo_desde
                time.sleep(300)

        ``proximo_desde`` is the latest ``envioCompletadoEn`` seen minus
        ``solapamiento`` (60 s by default, the API's recommendation: an answer
        can be written a moment before it becomes visible). The overlap and the
        inclusive bound mean **records from the end of one poll come back at the
        start of the next**, so dedup has to span polls, not just one.

        Dedup is by :func:`clave_cambio`, ``(idFactura, idRegistro, estado)``:
        ``idRegistro`` is unique only within one invoice. Without ``vistos`` it
        covers this poll only; pass the same dict to every poll, as above, to
        cover the overlap too. It is updated in place and pruned after each poll
        to the keys that can still repeat, so it stays bounded (about one
        overlap's worth of records) however long the poller runs. It lives in
        memory: across restarts, make ``procesar`` idempotent on the same key. A record
        may legitimately reappear with a new ``estado`` (VeriFactu's
        ``aceptada_con_errores`` followed by a final verdict): a new key, so it
        is yielded.

        ``desde`` must be an aware ``datetime``. Keep it, not a cursor, between
        runs: cursors expire after 24 hours.
        """
        if not isinstance(desde, _dt.datetime):
            raise TypeError("desde: pass an aware datetime.datetime")
        instante(desde, campo="desde")  # refuse a naive one before any request
        return CambiosRegistros(
            self.iterar(
                nif_emisor,
                veredicto_desde=desde,
                estado=estado,
                limite=limite,
                max_paginas=max_paginas,
            ),
            desde,
            solapamiento,
            vistos,
        )

    def obtener(self, id_registro: str, *, nif_emisor: str, id_factura: str) -> Dict[str, Any]:
        """One record (``GET /v1/registros/{idRegistro}``).

        ``idRegistro`` is an **opaque token**. Pass back exactly what the API gave
        you: do not parse it, split it, construct one, or depend on its length or
        alphabet. An unrecognised token is a ``400``.
        """
        params = {"nifEmisor": nif_emisor, "idFactura": id_factura}
        return dict(
            self._get(f"/v1/registros/{quote(str(id_registro), safe='')}", params=params).datos
        )


__all__ = [
    "CambiosRegistros",
    "ESTADOS_VEREDICTO",
    "RegistrosRecurso",
    "Vistos",
    "clave_cambio",
]
