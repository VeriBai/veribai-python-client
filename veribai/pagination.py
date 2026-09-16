"""Cursor pagination.

Every list endpoint uses the same three names — ``limite`` in, ``proximaPagina``
out, ``cursor`` back in — so one helper covers them all. ``proximaPagina`` is
``null`` on the last page.

The cursor is opaque and tenant-bound: pass it back unmodified. A corrupted,
truncated or hand-edited one is a ``400 INVALID_CURSOR``, and the fix is to drop
it and start from the first page, never to repair it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterator, List, Optional


@dataclass(frozen=True)
class Pagina:
    """One page of a list response.

    ``total`` counts the rows in **this page**, not the tenant's total — a name
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

    ``max_paginas`` is a guard rail, not a limit you normally need — but an
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
