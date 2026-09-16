"""TicketBAI: the invoice is signed at ingress, so the QR comes back immediately.

    python examples/02_ticketbai.py

The emisor must be registered with a `tbai-*` hacienda, and `provincia` must match it.
"""

from __future__ import annotations

import base64
import os
from datetime import date
from decimal import Decimal

import veribai

NIF_EMISOR = os.environ["VERIBAI_NIF_EMISOR"]
PROVINCIA = os.environ.get("VERIBAI_PROVINCIA", "araba")


def main() -> None:
    with veribai.Client() as client:
        factura = {
            "provincia": PROVINCIA,
            "emisor": {"nif": NIF_EMISOR, "nombre": "Mi Empresa SL"},
            "serie": "DEMO",
            "numero": date.today().strftime("%Y%m%d%H%M"),
            "fechaExpedicion": date.today(),
            "tipoFactura": "F1",
            "importeTotal": Decimal("121.00"),
            "destinatario": {"nif": "B98765432", "nombre": "Cliente Ejemplo SL"},
            "desglose": [
                {
                    "baseImponible": Decimal("100.00"),
                    "tipoImpositivo": Decimal("21"),
                    "cuota": Decimal("21.00"),
                    "descripcion": "Servicios de consultoría",
                }
            ],
            # Required for Araba, whose hacienda rejects altas with no detail lines.
            "lineas": [
                {
                    "descripcion": "Servicios de consultoría",
                    "cantidad": Decimal("1"),
                    "importeUnitario": Decimal("100.00"),  # without VAT
                    "importeTotal": Decimal("121.00"),  # with VAT
                }
            ],
        }

        respuesta = client.ticketbai.crear(factura)

        # Already signed and chained: these identifiers are final and stable across
        # retries, because a duplicate is replayed rather than re-signed.
        print(f"idTbai: {respuesta['idTbai']}")
        print(f"URL:    {respuesta['urlValidacion']}")

        if qr := respuesta.get("qrBase64"):
            datos = qr.split(",", 1)[-1]  # strip the data: URI prefix if present
            with open("tbai-qr.png", "wb") as fh:
                fh.write(base64.b64decode(datos))
            print("QR written to tbai-qr.png")

        # Only the submission to the foral hacienda is asynchronous.
        verdicto = client.facturas.esperar_verdicto(
            respuesta["idFactura"], nif_emisor=NIF_EMISOR, timeout=120
        )
        print("registrada" if verdicto.registrada else f"estado: {verdicto.estado_envio}")


if __name__ == "__main__":
    main()
