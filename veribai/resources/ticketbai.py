"""TicketBAI submission: ``POST/PUT /v1/ticketbai/*`` on the Invoicing API."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from ..serialization import preparar
from ._base import Recurso

PROVINCIAS = ("araba", "bizkaia", "gipuzkoa")


class TicketbaiRecurso(Recurso):
    """Alta, subsanación and anulación of TicketBAI records.

    TicketBAI differs from VeriFactu in a way that matters to a caller:
    **it signs at ingress**. By the time ``crear`` returns, the invoice has been
    signed with the taxpayer's certificate, the hash chain has permanently
    advanced, and the response already carries the official ``idTbai`` and its
    QR. Only the submission to the foral hacienda is asynchronous.

    Two consequences. First, the payload is flatter than VeriFactu's: ``serie``,
    ``numero``, ``fechaExpedicion``, ``tipoFactura`` and ``importeTotal`` sit at
    the top level, with no ``cabecera``/``totales`` nesting. Flatter, not flat:
    :meth:`crear` still requires a nested ``emisor`` object (``nif`` and
    ``nombre``) and a ``desglose`` list, whose lines are ``baseImponible`` /
    ``tipoImpositivo`` / ``cuota``, not VeriFactu's ``detalleDesglose`` /
    ``cuotaRepercutida``. Only :meth:`anular` is genuinely flat, with
    ``nifEmisor`` at the top level. Second, ``provincia`` is
    mandatory and must match the emisor's registered hacienda, or the call is a
    ``400 PROVINCE_MISMATCH``.
    """

    def crear(self, factura: Mapping[str, Any]) -> Dict[str, Any]:
        """Sign and register an invoice (``POST /v1/ticketbai/crear``).

        Returns ``estado: en_cola`` with ``idTbai``, ``urlValidacion`` and
        ``qrBase64`` already populated, and those are final and stable across
        retries, because a duplicate is replayed rather than re-signed.

        A replay of an in-flight duplicate carries ``yaExistente: true`` and no
        QR: the stored identity was returned and nothing was signed again.

        Note ``lineas`` is **required for Araba**, whose hacienda rejects altas
        without detail lines, and optional elsewhere.
        """
        return dict(
            self._post("/v1/ticketbai/crear", json=preparar(factura), idempotente=True).datos
        )

    def subsanar(self, factura: Mapping[str, Any]) -> Dict[str, Any]:
        """Correct a record (``PUT /v1/ticketbai/subsanar``).

        Same flat body as :meth:`crear`, with ``subsanacion: True``.

        Gipuzkoa is the special case, and the difference is visible in the
        response. Where the hacienda rejected the record for its **content**, the
        correction goes through their ZUZENDU service as an unsigned file
        referencing the original, so the reply carries ``viaZuzendu: true`` and
        keeps the **original** ``idTbai``, validation URL and QR. That is
        deliberate: the customer already has that QR on their invoice, and
        re-signing would invalidate a document already in their hands.

        Where the rejection was about the certificate or the service instead, the
        correct action is to resend unmodified, and the API says so with
        ``409 RESEND_UNMODIFIED_REQUIRED`` rather than guessing.
        """
        return dict(
            self._put("/v1/ticketbai/subsanar", json=preparar(factura), idempotente=True).datos
        )

    def anular(self, anulacion: Mapping[str, Any]) -> Dict[str, Any]:
        """Cancel an invoice (``POST /v1/ticketbai/anular``).

        Flat body: ``nifEmisor``, ``serie``/``numero``/``fechaExpedicion`` and
        ``provincia`` at the top level. Signed and chain-sealed at ingress like an
        alta.

        An already-registered or in-flight cancellation replays with ``200`` and
        ``yaAnulada: true``. TicketBAI is idempotent here where VeriFactu answers
        ``409 ALREADY_CANCELLED``.
        """
        return dict(
            self._post("/v1/ticketbai/anular", json=preparar(anulacion), idempotente=True).datos
        )


__all__ = ["PROVINCIAS", "TicketbaiRecurso"]
