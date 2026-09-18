"""Alta capacidad (mega-tenant) device registry: ``/v1/clientes/{nif}/dispositivos*``.

A high-volume taxpayer can run one hash chain **per device** instead of one per
NIF, which is what lets tills, branches and back-office systems invoice in
parallel without serialising on a single chain. These routes are how the devices
get registered.

Three facts shape every call here:

* a device id **is the key of its own hash chain**: it is never renamed and
  never reused, and deregistering only tombstones it;
* the routes are gated on the **contract phase**, not the chain mode. While the
  account is in ``preparacion`` you register devices and nothing changes about
  how invoices are routed, and that inertness is the point of the window;
* the flip to ``activa`` is staff-driven. You signal readiness with
  :meth:`DispositivosRecurso.solicitar_activacion`.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote

from ..serialization import limpiar
from ._base import Recurso

#: The central sender: invoices submitted with no ``idMaquina`` at all.
CENTRAL = "__SHARD0__"


class DispositivosRecurso(Recurso):
    """Devices and serie claims for one emisor, on the API key's environment."""

    def listar(self, nif: str) -> Dict[str, Any]:
        """Devices, serie claims and the account's Alta capacidad state.

        Always ``200``: an account that has not contracted the feature answers
        ``faseAltaCapacidad: "no_contratada"`` with empty arrays. Retired devices
        are listed with ``activo: false``, never hidden.

        While the account is in ``preparacion`` the response also carries
        ``idsMaquinaVistos``: the device tags actually seen on invoices since the
        window opened, so you can reconcile what your systems send against what is
        registered before the flip.

        An empty sightings list is **not** proof that nothing sends a tag: a
        nightly batch may not have run. Read it against ``observandoDesde``, which
        says how long anyone has been watching.
        """
        return dict(self._get(f"/v1/clientes/{_nif(nif)}/dispositivos").datos)

    def registrar(
        self, nif: str, id_maquina: str, *, etiqueta: Optional[str] = None
    ) -> Dict[str, Any]:
        """Register a device (``201``), or reactivate a retired one (``200``).

        ``id_maquina`` is at most 64 characters of ``[A-Za-z0-9._-]``. Re-registering
        an id that was retired resumes the **same chain** and keeps its AEAT
        installation number, which is why ids are never recycled between machines.

        An id that is currently active answers ``409 MACHINE_ALREADY_REGISTERED``;
        an account that has not contracted the feature answers
        ``409 SHARDING_NOT_ENABLED``.
        """
        cuerpo = limpiar({"idMaquina": id_maquina, "etiqueta": etiqueta})
        return dict(self._post(f"/v1/clientes/{_nif(nif)}/dispositivos", json=cuerpo).datos)

    def dar_de_baja(self, nif: str, id_maquina: str) -> Dict[str, Any]:
        """Retire a device (``DELETE …/dispositivos/{idMaquina}``).

        Nothing is deleted: its signed history, its serie claims and its AEAT
        installation all stay. Only new invoices stop routing to it. Idempotent.
        """
        return dict(
            self._delete(
                f"/v1/clientes/{_nif(nif)}/dispositivos/{quote(str(id_maquina), safe='')}"
            ).datos
        )

    def promover(self, nif: str, ids_maquina: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        """Copy the TEST device set-up to LIVE (``POST …/dispositivos/promover``).

        Copies id and ``etiqueta`` only, and deliberately nothing else: the AEAT
        installation number and the queue lane are per-environment identities that
        LIVE mints at its first real invoice, and serie claims are formed by real
        invoices rather than declared. Idempotent.

        The client must already exist on LIVE (``409 CLIENT_NOT_IN_LIVE``).
        """
        cuerpo: Optional[Dict[str, Any]] = None
        if ids_maquina is not None:
            lista: List[str] = [str(i) for i in ids_maquina]
            if not lista:
                raise ValueError("ids_maquina cannot be empty; omit it to promote every device")
            cuerpo = {"idsMaquina": lista}
        return dict(
            self._post(
                f"/v1/clientes/{_nif(nif)}/dispositivos/promover", json=cuerpo, idempotente=True
            ).datos
        )

    def solicitar_activacion(self, nif: str) -> Dict[str, Any]:
        """Tell VeriBai the preparation is finished: «ya estamos listos».

        This is the customer half of the activation protocol: it records the
        request on the shared registry, where it is a precondition staff check
        before flipping the account to ``activa``, and raises one ops alert.

        Idempotent, and deliberately so: the **first** request stands, so pressing
        it again never resets the clock the operator is reading.

        Only valid while the phase is ``preparacion`` (else ``409 NOT_IN_PREPARATION``).
        """
        return dict(
            self._post(
                f"/v1/clientes/{_nif(nif)}/dispositivos/solicitar-activacion", idempotente=True
            ).datos
        )

    def reservar_series_centralizadas(self, nif: str, series: Iterable[str]) -> Dict[str, Any]:
        """Bind series to the central sender before any device can claim them.

        The one pre-claim Alta capacidad allows. Everything else about serie
        ownership is discovered from real invoices; this is the head office
        writing its name on its own series first.

        Idempotent, and it never steals: a serie a device already owns is left
        alone and reported in ``omitidas``.
        """
        lista = [str(s) for s in series]
        if not lista:
            raise ValueError("at least one serie is required")
        return dict(
            self._post(
                f"/v1/clientes/{_nif(nif)}/dispositivos/series-centralizadas",
                json={"series": lista},
                idempotente=True,
            ).datos
        )

    def liberar_serie_centralizada(self, nif: str, serie: str) -> Dict[str, Any]:
        """Release a central-sender reservation, **``preparacion`` only**.

        Once the account is ``activa`` a reservation is permanent
        (``409 RESERVATION_LOCKED``): the central sender may already have chained
        under that serie, and freeing it would let a device claim a serie the main
        flow is using.
        """
        return dict(
            self._delete(
                f"/v1/clientes/{_nif(nif)}/dispositivos/series-centralizadas/"
                f"{quote(str(serie), safe='')}"
            ).datos
        )


def _nif(nif: str) -> str:
    return quote(str(nif), safe="")


__all__ = ["CENTRAL", "DispositivosRecurso"]
