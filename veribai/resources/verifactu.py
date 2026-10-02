"""VeriFactu submission: ``POST/PUT /v1/verifactu/*`` on the Invoicing API."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from ..serialization import preparar
from ._base import Recurso


class VerifactuRecurso(Recurso):
    """Alta, subsanación and anulación of VeriFactu records.

    An identical resubmission of the same (serie, número, fechaExpedicion)
    returns ``200`` with the record already on file, marked ``yaExistente: true``,
    instead of creating a second one. That is what makes retrying a timeout safe,
    and this client retries them for you. :meth:`anular` flags its replay
    ``yaAnulada`` instead; see there.

    Change ``importeTotal`` or ``tipoFactura`` between attempts, though, and the
    API answers ``409 INVOICE_IDENTITY_CONFLICT``, correctly, because that is a
    different invoice wearing the same number. A genuinely new invoice needs a
    new number.
    """

    def crear(self, factura: Mapping[str, Any]) -> Dict[str, Any]:
        """Register an invoice (``POST /v1/verifactu/crear``).

        The response is ``estado: pendiente_proceso``: **accepted, not filed**.
        AEAT is addressed asynchronously by a minute-tick pipeline, so the verdict
        arrives later, so use :meth:`~veribai.resources.facturas.FacturasRecurso.esperar_verdicto`
        or a webhook.

        ``Decimal`` amounts and ``date`` objects in the payload are converted to
        the wire formats automatically; see :mod:`veribai.serialization`.

        ``totales.cuotaTotal`` and ``totales.importeTotal`` reach AEAT exactly as
        you declare them. With recargo de equivalencia, ``cuotaTotal`` is the sum
        of ``cuotaRepercutida`` **and** ``cuotaRecargoEquivalencia``, and
        ``importeTotal`` is base + cuota + recargo.

        ``especial`` carries AEAT's optional ``RegistroAlta`` flags, all of which
        are transmitted: ``facturaSimplificadaArt7273``,
        ``facturaSinIdentifDestinatarioArt61d`` and ``cupon`` (``"S"``/``"N"``),
        ``emitidaPor`` (``"T"``/``"D"``), ``tercero`` (``nombre`` up to 120
        characters plus ``nif`` or ``idOtro``, as in ``destinatario``),
        ``numRegistroAcuerdoFacturacion`` (up to 15 characters) and
        ``idAcuerdoSistemaInformatico`` (up to 16). ``aux.refExterna`` is accepted
        but **not transmitted to AEAT**, so do not rely on finding it there.

        Example::

            respuesta = client.verifactu.crear({
                "version": "1.0",
                "emisor": {"nif": "B12345674", "nombre": "Ejemplo SL"},
                "cabecera": {
                    "serie": "A",
                    "numero": "1",
                    "fechaExpedicion": date(2026, 9, 15),
                    "tipoFactura": "F1",
                    "descripcion": "Servicios de consultoría",
                },
                "destinatario": {"nif": "B00000000", "nombre": "CLIENTE, SL"},
                "detalleDesglose": [{
                    "claveRegimen": "01",
                    "calificacionOperacion": "S1",
                    "baseImponible": Decimal("100.00"),
                    "tipoImpositivo": Decimal("21"),
                    "cuotaRepercutida": Decimal("21.00"),
                }],
                "totales": {"cuotaTotal": Decimal("21.00"),
                            "importeTotal": Decimal("121.00")},
            })
        """
        return dict(
            self._post("/v1/verifactu/crear", json=preparar(factura), idempotente=True).datos
        )

    def subsanar(self, factura: Mapping[str, Any]) -> Dict[str, Any]:
        """Correct a rejected or incorrect record (``PUT /v1/verifactu/subsanar``).

        Send the whole corrected invoice, not a patch. ``serie``, ``numero`` and
        ``fechaExpedicion`` identify the record and cannot change, and a different
        issue date is a different invoice, not a correction of this one.

        ``rechazoPrevio`` is the AEAT tri-state string: ``"N"``, ``"S"``, or
        ``"X"`` when the record does not exist at AEAT at all.
        """
        return dict(
            self._put("/v1/verifactu/subsanar", json=preparar(factura), idempotente=True).datos
        )

    def anular(self, anulacion: Mapping[str, Any]) -> Dict[str, Any]:
        """Cancel an invoice (``POST /v1/verifactu/anular``).

        VeriFactu nests the target in ``facturaAnulada`` (TicketBAI does not:
        its cancel body is flat).

        ``sinRegistroPrevio`` says the invoice being cancelled was never reported
        to AEAT, the onboarding case, where you void a pre-VeriFactu invoice and
        keep the hash chain coherent. Getting it the wrong way round is its own
        409: ``INVOICE_NOT_FOUND`` when it is ``false`` but nothing is on record,
        ``INVOICE_EXISTS`` when it is ``true`` but the invoice *is* on record.

        ``nombreEmisor`` (optional, max 120) goes in ``facturaAnulada``. VeriBai
        fills it from the alta when it holds one; for an invoice it never saw
        (typically ``sinRegistroPrevio: true``) send it exactly as in the AEAT
        census, or the call fails ``400 VALIDATION_ERROR`` naming
        ``facturaAnulada.nombreEmisor``.

        The response is an envelope: the record is under ``data``, including
        ``numSerieFactura``, ``serie`` and ``numero``.

        A repeat is a retry, not a second cancellation: whatever state the
        existing anulación is in, it answers ``200`` with **that** anulación
        (``data.creadoEn`` and ``data.estado`` are the existing one's) and
        ``data.yaAnulada: true``, as TicketBAI does. Nothing new is created or
        sent. Only a cancellation AEAT rejected lets a new one through.

        An invoice with rectificativas cannot be cancelled until they are:
        ``409 INVOICE_HAS_RECTIFICATIVAS`` (a :class:`~veribai.errors.ConflictError`),
        with ``idFactura``, ``numSerieFactura``, ``serie``, ``numero``,
        ``fechaExpedicion`` and ``rectificativas`` in ``details``.

        Example::

            client.verifactu.anular({
                "version": "1.0",
                "facturaAnulada": {
                    "nifEmisor": "B12345674",
                    "serie": "A",
                    "numero": "1",
                    "fechaExpedicion": date(2026, 9, 15),
                },
            })

            # Never reported to AEAT: VeriBai has no alta to take the name from.
            client.verifactu.anular({
                "version": "1.0",
                "sinRegistroPrevio": True,
                "facturaAnulada": {
                    "nifEmisor": "B12345674",
                    "nombreEmisor": "EMPRESA EJEMPLO SL",
                    "serie": "A",
                    "numero": "0",
                    "fechaExpedicion": date(2026, 9, 1),
                },
            })
        """
        return dict(
            self._post("/v1/verifactu/anular", json=preparar(anulacion), idempotente=True).datos
        )


__all__ = ["VerifactuRecurso"]
