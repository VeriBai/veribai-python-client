"""Webhook subscriptions: ``/v1/webhooks*`` on the Management API.

Registering an endpoint is only half of it: deliveries do not start until you
also **link secondary clients** to the webhook with :meth:`WebhooksRecurso.vincular_clientes`.
A webhook with no linked clients is silent, and that is the commonest reason a
new integration sees nothing arrive.

To verify and parse what lands on your endpoint, see :mod:`veribai.webhooks`.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote

from ..serialization import limpiar
from ._base import Recurso

EVENTOS = ("factura.registrada", "factura.rechazada", "factura.anulada")


class WebhooksRecurso(Recurso):
    """Manage delivery endpoints and which clients feed them."""

    def listar(self) -> Dict[str, Any]:
        """Every webhook on this environment."""
        return dict(self._get("/v1/webhooks").datos)

    def crear(
        self,
        *,
        nombre: str,
        url: str,
        secreto: str,
        eventos: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        """Register an endpoint (``POST /v1/webhooks``).

        Args:
            url: must be ``https`` and a public host. Loopback, private ranges,
                ``.local``/``.internal`` and link-local addresses are refused,
                including ``169.254.169.254``, which is how a webhook becomes an
                SSRF primitive against cloud metadata.
            secreto: 16–512 characters, yours to choose. It keys the HMAC over the
                raw delivery body; store it where your handler can reach it.
            eventos: omit to receive everything, which is the default and what
                most integrations want. ``factura.rechazada`` **cannot** be
                excluded: a rejected record was not filed, and the filing
                obligation is the taxpayer's, so a list without it is refused.

        This call is **not** retried after a network error: a second attempt
        would create a second webhook, and the API has no identity to replay on.
        """
        cuerpo = limpiar(
            {
                "nombre": nombre,
                "url": url,
                "secreto": secreto,
                "eventos": list(eventos) if eventos is not None else None,
            }
        )
        return dict(self._post("/v1/webhooks", json=cuerpo).datos)

    def obtener(self, id_webhook: str) -> Dict[str, Any]:
        """One webhook, wrapped as ``{"webhook": …, "entorno": …}``.

        The envelope is not noise: ``entorno`` is how an API-key caller learns
        which environment the key resolved to, which the webhook object alone
        cannot say.
        """
        return dict(self._get(f"/v1/webhooks/{_id(id_webhook)}").datos)

    def modificar(self, id_webhook: str, cambios: Dict[str, Any]) -> Dict[str, Any]:
        """Partial update (``PATCH /v1/webhooks/{id}``).

        ``estado: "activo"`` is also how you re-enable a webhook the circuit
        breaker suspended after 20 consecutive failures; it resets the counter.

        Passing ``eventos: None`` **clears** the subscription, restoring delivery
        of every event.

        A ``500 PROPAGATION_INCOMPLETE`` means the webhook was updated but some
        client links did not get the change, so deliveries do not yet match what
        ``GET`` reports. Retry the identical PATCH: it re-propagates.
        """
        return dict(
            self._patch(
                f"/v1/webhooks/{_id(id_webhook)}", json=dict(cambios), idempotente=True
            ).datos
        )

    def eliminar(self, id_webhook: str) -> Dict[str, Any]:
        """Delete a webhook."""
        return dict(self._delete(f"/v1/webhooks/{_id(id_webhook)}").datos)

    def listar_clientes(self, id_webhook: str) -> Dict[str, Any]:
        """Which secondary clients feed this webhook."""
        return dict(self._get(f"/v1/webhooks/{_id(id_webhook)}/clientes").datos)

    def vincular_clientes(self, id_webhook: str, nifs: Iterable[str]) -> Dict[str, Any]:
        """Link secondary clients, so their invoices start producing deliveries."""
        lista: List[str] = [str(n) for n in nifs]
        if not lista:
            raise ValueError("at least one NIF is required")
        return dict(
            self._post(f"/v1/webhooks/{_id(id_webhook)}/clientes", json={"clientes": lista}).datos
        )

    def desvincular_cliente(self, id_webhook: str, nif: str) -> Dict[str, Any]:
        """Stop a secondary client's invoices from reaching this webhook."""
        return dict(
            self._delete(
                f"/v1/webhooks/{_id(id_webhook)}/clientes/{quote(str(nif), safe='')}"
            ).datos
        )


def _id(valor: str) -> str:
    return quote(str(valor), safe="")


__all__ = ["EVENTOS", "WebhooksRecurso"]
