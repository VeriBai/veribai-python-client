"""Submission records — ``GET /v1/registros*`` on the Invoicing API."""

from __future__ import annotations

from typing import Any, Dict, Iterator, Optional
from urllib.parse import quote

from ..pagination import Pagina, construir_pagina, iterar_paginas
from ..serialization import limpiar
from ._base import Recurso


class RegistrosRecurso(Recurso):
    """The per-submission ledger: one record per alta, subsanación or anulación.

    This is where the authority's own verdict lives — ``codigoRespuestaAeat`` and
    its description for VeriFactu, ``codigoRespuestaTbai``/``mensajeRespuestaTbai``
    for TicketBAI. The invoice's ``estado`` tells you *that* something was
    rejected; the record tells you *why*.
    """

    def listar(
        self,
        nif_emisor: str,
        *,
        limite: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> Pagina:
        """One page of records, most recent first (``GET /v1/registros``)."""
        params = limpiar({"nifEmisor": nif_emisor, "limite": limite, "cursor": cursor})
        return construir_pagina(self._get("/v1/registros", params=params).datos, "registros")

    def iterar(
        self,
        nif_emisor: str,
        *,
        limite: Optional[int] = None,
        max_paginas: Optional[int] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Walk every page of :meth:`listar`."""
        return iterar_paginas(
            lambda cursor: self.listar(nif_emisor, limite=limite, cursor=cursor),
            max_paginas=max_paginas,
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


__all__ = ["RegistrosRecurso"]
