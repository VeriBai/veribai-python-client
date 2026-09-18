"""Secondary clients: ``/v1/clientes*`` on the Management API."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional
from urllib.parse import quote

from ..serialization import limpiar, preparar
from ._base import Recurso


class ClientesRecurso(Recurso):
    """The businesses you issue invoices for.

    Two fields are worth reading twice before you create one, because neither is
    recoverable through the API: ``hacienda`` is **immutable**, and a self-emisor
    (a client whose NIF is your own) can be neither deleted nor deactivated. Pick
    the tax authority deliberately.
    """

    def listar(self, *, incluir_eliminados: bool = False) -> Dict[str, Any]:
        """All your secondary clients plus the plan's seat figures.

        ``clientesUsados`` counts **active** clients, not rows: deactivating or
        soft-deleting one decrements it. So an account with inactive rows reports
        fewer used seats than the list has entries, and that is correct.

        The three seat fields are all-or-nothing and **absent** (never ``0``)
        when the org has no cap or the figure could not be read. Treat a missing
        ``limitePlan`` as "no cap known", because ``0`` means "you are at your cap"
        and would hide a create button from an account that has none.
        """
        params = limpiar({"incluirEliminados": _bool(incluir_eliminados)})
        return dict(self._get("/v1/clientes", params=params).datos)

    def asientos(self) -> Dict[str, Optional[int]]:
        """Just the seat figures, as ``{limite, usados, disponibles}``.

        Each is ``None`` when the API omitted it. Never derive the cap from the
        plan tier: it is overridable per organisation.
        """
        datos = self.listar()
        return {
            "limite": datos.get("limitePlan"),
            "usados": datos.get("clientesUsados"),
            "disponibles": datos.get("clientesDisponibles"),
        }

    def crear(self, cliente: Mapping[str, Any]) -> Dict[str, Any]:
        """Register a secondary client (``POST /v1/clientes/crear``).

        Returns ``201`` normally. Two special cases involve your **own** NIF:
        re-creating your own existing emisor returns ``200`` with the existing row
        (an idempotent replay), and your own NIF held by another account is
        ``409 SELF_CLIENT_CONFLICT``. A third-party NIF that is taken stays an
        opaque ``400`` in both cases, and that opacity is what stops this endpoint
        being an ownership oracle, so do not read a 400 here as "already exists".

        ``representante`` is required for ``tipoUsuario="empresa"``;
        ``epigrafeIAE`` for an autónomo under ``tbai-bizkaia``.
        """
        return dict(self._post("/v1/clientes/crear", json=preparar(cliente)).datos)

    def obtener(self, nif: str, *, incluir_eliminados: bool = False) -> Dict[str, Any]:
        """One client (``GET /v1/clientes/{nif}``), wrapped as ``{"cliente": …}``."""
        params = limpiar({"incluirEliminados": _bool(incluir_eliminados)})
        return dict(self._get(f"/v1/clientes/{_nif(nif)}", params=params).datos)

    def modificar(self, nif: str, cambios: Mapping[str, Any]) -> Dict[str, Any]:
        """Partial update (``PATCH /v1/clientes/{nif}``).

        ``nombre``, ``direccion``, ``representante``, ``epigrafeIAE`` and
        ``portalHabilitado`` only. Touching ``hacienda`` answers ``409`` with
        ``camposBloqueados``.
        """
        return dict(
            self._patch(f"/v1/clientes/{_nif(nif)}", json=preparar(cambios), idempotente=True).datos
        )

    def cambiar_estado(self, nif: str, estado: str) -> Dict[str, Any]:
        """Activate or deactivate (``PATCH /v1/clientes/{nif}/estado``).

        Adjusts the org's seat counter atomically, so reactivation can be refused
        with ``409 CLIENT_LIMIT_REACHED`` if the plan is now full.

        It does **not** undelete: a soft-deleted client answers
        ``409 CLIENT_DELETED``, because only the restore path checks the 30-day
        window and clears the deletion markers.

        Note ``entorno`` is present on a real state change and absent when the
        call was a no-op, so do not read it unconditionally.
        """
        if estado not in ("activo", "inactivo"):
            raise ValueError(f"estado must be 'activo' or 'inactivo', got {estado!r}")
        return dict(
            self._patch(
                f"/v1/clientes/{_nif(nif)}/estado", json={"estado": estado}, idempotente=True
            ).datos
        )

    def activar(self, nif: str) -> Dict[str, Any]:
        """Shorthand for :meth:`cambiar_estado` with ``activo``."""
        return self.cambiar_estado(nif, "activo")

    def desactivar(self, nif: str) -> Dict[str, Any]:
        """Shorthand for :meth:`cambiar_estado` with ``inactivo``."""
        return self.cambiar_estado(nif, "inactivo")


def _nif(nif: str) -> str:
    return quote(str(nif), safe="")


def _bool(valor: bool) -> Optional[str]:
    return "true" if valor else None


__all__ = ["ClientesRecurso"]
