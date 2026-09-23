"""Shared plumbing for the resource groups."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from .._transport import Respuesta, Transport


class Recurso:
    """A group of endpoints sharing one base URL.

    Two exist: the Invoicing API (where the base URL *is* the environment) and
    the Management API (one URL for both, resolving the environment from the
    key).
    """

    def __init__(self, transport: Transport, base_url: str) -> None:
        self._t = transport
        self._base = base_url

    def _get(
        self,
        ruta: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        accept: str = "application/json",
        binario: bool = False,
    ) -> Respuesta:
        return self._t.request(
            "GET", self._base, ruta, params=params, idempotente=True, accept=accept, binario=binario
        )

    def _post(
        self,
        ruta: str,
        *,
        json: Any = None,
        params: Optional[Mapping[str, Any]] = None,
        idempotente: bool = False,
    ) -> Respuesta:
        return self._t.request(
            "POST", self._base, ruta, json=json, params=params, idempotente=idempotente
        )

    def _put(self, ruta: str, *, json: Any = None, idempotente: bool = False) -> Respuesta:
        return self._t.request("PUT", self._base, ruta, json=json, idempotente=idempotente)

    def _patch(self, ruta: str, *, json: Any = None, idempotente: bool = False) -> Respuesta:
        return self._t.request("PATCH", self._base, ruta, json=json, idempotente=idempotente)

    def _delete(
        self, ruta: str, *, params: Optional[Mapping[str, Any]] = None, idempotente: bool = True
    ) -> Respuesta:
        return self._t.request("DELETE", self._base, ruta, params=params, idempotente=idempotente)


__all__ = ["Recurso"]
