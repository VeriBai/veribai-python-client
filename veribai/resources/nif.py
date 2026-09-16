"""AEAT census validation — ``POST /v1/nif/validar`` on the Management API."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Union

from ._base import Recurso

Entrada = Union[str, Mapping[str, Any]]


class NifRecurso(Recurso):
    """Check NIFs against the AEAT census before you invoice against them.

    Worth knowing how the census actually behaves, because it shapes what a
    verdict means: for a **persona física** the AEAT checks the name as well as
    the number, and for a CIF it ignores the name entirely. So ``identificado``
    for a company says the number exists, not that the name you hold is right.

    The whole batch — up to 100 entries — costs one AEAT call, and results are
    cached, so validating a list is far cheaper than validating one at a time.
    Environment-agnostic: no ``entorno`` anywhere.
    """

    def validar(self, nifs: Iterable[Entrada], *, forzar: bool = False) -> Dict[str, Any]:
        """Validate 1–100 NIFs (``POST /v1/nif/validar``).

        Args:
            nifs: NIF strings, or mappings with ``nif`` and an optional ``nombre``.
                Supply ``nombre`` for personas físicas — without it the check is
                weaker for exactly the identities where the AEAT would check it.
            forzar: bypass the cache read (it still writes back), forcing a fresh
                AEAT call. This is what a "Revalidar" button does. There is no
                cache-hit flag in the response; freshness is ``validadoEn``.

        Returns:
            ``{"resultados": [...]}``, one verdict per entry in order.

        Raises:
            AeatUnavailableError: the census was unreachable. Its ``payload`` may
                still carry the subset that was served from cache.
        """
        entradas: List[Dict[str, Any]] = []
        for entrada in nifs:
            if isinstance(entrada, str):
                entradas.append({"nif": entrada})
            elif isinstance(entrada, Mapping):
                entradas.append(dict(entrada))
            else:
                raise TypeError(
                    f"each entry must be a NIF string or a mapping, got {type(entrada).__name__}"
                )
        if not entradas:
            raise ValueError("at least one NIF is required")

        cuerpo: Dict[str, Any] = {"nifs": entradas}
        if forzar:
            cuerpo["forzar"] = True
        return dict(self._post("/v1/nif/validar", json=cuerpo, idempotente=True).datos)


__all__ = ["NifRecurso"]
