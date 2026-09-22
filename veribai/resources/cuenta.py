"""Account and connectivity: ``GET /v1/cuenta`` on the Invoicing API."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import Recurso


class CuentaRecurso(Recurso):
    """Confirms the key works and reports the account's state.

    The call to wire into setup and CI, and only there. It counts against the
    monthly quota like any other call, so it is not a monitoring poll target.

    It reports **your account**. It makes no request to the AEAT or the foral
    haciendas and says nothing about whether they are up.
    """

    def obtener(self) -> Dict[str, Any]:
        """Key, environment, plan, billing state and quota (``GET /v1/cuenta``).

        ``estadoCuenta`` is ``activa``, ``prueba``, ``pago_pendiente``,
        ``suspendida``, ``cancelada`` or ``desconocido``. **``pago_pendiente`` is a
        grace window, not an outage**: it is the week after a failed payment, during
        which invoicing keeps working and ``facturacionActiva`` stays ``True``. Warn
        on it, do not halt on it. It turns into ``suspendida`` if the debt is not
        settled, and only then do mutating calls answer ``402``; reads and evidence
        never block in any state. ``desconocido`` means the billing state could not
        be read, not that something is wrong with the account.

        ``facturacionActiva`` covers billing only. On LIVE an alta has a second,
        per-emisor gate (the representation mandate must be signed) which this
        endpoint cannot know about because it does not know which emisor you are
        about to invoice for. Check ``estadoRepresentacion`` on the client for that.

        ``consumo`` is **absent**, not zeroed, when no figure has been cached yet
        (a brand-new key). Read the absence as "not known", never as "nothing
        left": ``restantes: 0`` is what "at your cap" looks like.
        """
        return dict(self._get("/v1/cuenta").datos)

    def consumo(self) -> Optional[Dict[str, Any]]:
        """Just the quota block, or ``None`` when no figure is cached yet.

        ``{usadas, restantes, limite, periodo, observadoEn}``. The figure is
        refreshed on a short cycle and the upstream counters lag by minutes on top,
        so it can be roughly ten minutes behind, and ``observadoEn`` says how far.
        Treat it as a good guide to how much is left and not as a live counter: it
        cannot tell you whether one specific next call will succeed. The only
        authoritative signal that you have run out is a ``429``.

        Note the quota is per **API key**, not per account, and a rotated key
        inherits the previous key's consumption, and rotating does not reset it. That
        is also why ``usadas + restantes`` can be *less* than ``limite`` after a
        rotation.
        """
        bloque = self.obtener().get("consumo")
        return dict(bloque) if isinstance(bloque, dict) else None


__all__ = ["CuentaRecurso"]
