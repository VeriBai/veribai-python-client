"""AEAT census validation — ``POST /v1/nif/validar`` on the Management API."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Union

from ._base import Recurso

Entrada = Union[str, Mapping[str, Any]]


class NifRecurso(Recurso):
    """Check NIFs against the AEAT census before you invoice against them.

    🚨 **``identificado`` means the NIF exists in the census. It does not mean the
    name you sent is right.** For a **CIF** the AEAT ignores the queried name
    entirely: send ``B26682641`` with ``nombre="Pepita SL"`` and you still get
    ``identificado``, with the real razón social in ``nombreCenso``. Comparing the
    two is *your* check. For a **DNI/NIE** the name is part of the verdict, so a
    wrong one answers ``no_identificado``. The same status therefore carries
    different weight depending on the kind of NIF.

    The whole batch — up to 100 entries — costs one AEAT call, and results are
    cached, so validating a list is far cheaper than validating one at a time.
    Environment-agnostic: no ``entorno`` anywhere.
    """

    def validar(self, nifs: Iterable[Entrada]) -> Dict[str, Any]:
        """Validate 1–100 NIFs (``POST /v1/nif/validar``).

        Args:
            nifs: mappings with ``nif`` and ``nombre``. **Both are required** — see
                below — so a bare NIF string is refused here rather than spending a
                call to be told the same thing.

        Returns:
            ``{"resultados": [...]}``, one verdict per entry in order. Freshness is
            ``validadoEn``; there is no cache-hit flag.

        Raises:
            ValueError: an entry is missing ``nif`` or ``nombre``, or the list is
                empty.
            AeatUnavailableError: the census could not be **reached**. Its
                ``payload`` may still carry the subset served from cache.

        ``nombre`` is mandatory even though the AEAT ignores it for a CIF, because
        the census cache is keyed on ``(nif, nameHash)``: an entry cached under an
        empty name would later serve ``identificado`` for a DNI/NIE queried with the
        *wrong* name — the one verdict that must never be wrong.

        A NIF the census answers nothing about comes back as an ordinary result with
        ``estado: no_procesado``, not as an error for the whole batch. Those are
        never cached, so simply calling again asks the census again.

            >>> client.nif.validar([
            ...     {"nif": "B26682641", "nombre": "SKY CLOUD INFRASTRUCTURE SL"},
            ...     {"nif": "12345678Z", "nombre": "NOMBRE APELLIDO"},
            ... ])
        """
        entradas: List[Dict[str, Any]] = []
        for indice, entrada in enumerate(nifs):
            if isinstance(entrada, str):
                raise ValueError(
                    f"nifs[{indice}]: a bare NIF string is not enough — the API requires "
                    f"'nombre' on every entry. Pass "
                    f"{{'nif': {entrada!r}, 'nombre': 'RAZÓN SOCIAL'}}. It is required even "
                    f"for a CIF, whose name the AEAT ignores, because the census cache is "
                    f"keyed on (nif, nombre)."
                )
            if not isinstance(entrada, Mapping):
                raise TypeError(
                    f"nifs[{indice}]: each entry must be a mapping with 'nif' and 'nombre', "
                    f"got {type(entrada).__name__}"
                )
            datos = dict(entrada)
            for campo in ("nif", "nombre"):
                if not str(datos.get(campo) or "").strip():
                    raise ValueError(f"nifs[{indice}]: {campo!r} is required and cannot be empty")
            entradas.append(datos)

        if not entradas:
            raise ValueError("at least one NIF is required")

        return dict(self._post("/v1/nif/validar", json={"nifs": entradas}, idempotente=True).datos)


__all__ = ["NifRecurso"]
