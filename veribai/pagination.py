"""Cursor pagination.

Every list endpoint uses the same three names (``limite`` in, ``proximaPagina``
out, ``cursor`` back in) so one helper covers them all. ``proximaPagina`` is
``null`` on the last page.

**The cursor is an opaque token: pass it back unmodified, and never build one.**
Its format is not part of the API contract and has already changed once: it was
readable base64 until 2026-09-22 and is an encrypted token now. Code that decoded
or hand-assembled a cursor broke on that change; code that passed it back
untouched did not.

It is bound to the **tenant, the endpoint and the environment** that issued it,
and it **expires 24 hours after issue**. A cursor is therefore good for walking a
list you are reading right now, and for nothing else:

* do not persist one between runs, and do not hand one to a long-lived job. To
  resume a walk later, re-derive the position from a filter you control
  (``fecha_inicio``/``fecha_fin`` on ``facturas.listar``), never from a stored
  cursor;
* do not carry one between list endpoints, between TEST and LIVE, or between
  accounts.

Every one of those is ``400 INVALID_CURSOR``: corrupted, truncated, hand-edited,
**expired**, or minted for a different endpoint, environment or account. One code
covers ``/v1/facturas``, ``/v1/registros``, ``/v1/clientes`` and ``/v1/webhooks``.
Retrying the same cursor never succeeds, so the fix is always to drop it and start
from the first page, never to repair it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterator, List, Optional


@dataclass(frozen=True)
class Pagina:
    """One page of a list response.

    ``total`` counts the rows in **this page**, not the tenant's total, a name
    that has misled people, so it is exposed as ``total_en_pagina``.
    """

    items: List[Dict[str, Any]]
    proxima_pagina: Optional[str]
    bruto: Dict[str, Any]

    @property
    def total_en_pagina(self) -> int:
        return len(self.items)

    @property
    def hay_mas(self) -> bool:
        return bool(self.proxima_pagina)

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)


def construir_pagina(respuesta: Dict[str, Any], clave: str) -> Pagina:
    """Wrap a list response, reading the items from ``clave`` (``facturas``, …)."""
    items = respuesta.get(clave) or []
    if not isinstance(items, list):
        items = []
    return Pagina(
        items=[i for i in items if isinstance(i, dict)],
        proxima_pagina=respuesta.get("proximaPagina"),
        bruto=respuesta,
    )


def iterar_paginas(
    obtener: Callable[[Optional[str]], Pagina],
    *,
    max_paginas: Optional[int] = None,
) -> Iterator[Dict[str, Any]]:
    """Walk every page, yielding items.

    ``max_paginas`` is a guard rail, not a limit you normally need, but an
    unbounded loop over a paginated API is the classic way to burn a monthly
    quota, and the quota here is per API key.
    """
    cursor: Optional[str] = None
    paginas = 0
    vistos = set()
    while True:
        pagina = obtener(cursor)
        yield from pagina.items
        paginas += 1
        if max_paginas is not None and paginas >= max_paginas:
            return
        if not pagina.proxima_pagina:
            return
        if pagina.proxima_pagina in vistos:
            # A cursor that repeats would loop for ever and spend the quota doing it.
            return
        vistos.add(pagina.proxima_pagina)
        cursor = pagina.proxima_pagina


__all__ = ["Pagina", "construir_pagina", "iterar_paginas"]
