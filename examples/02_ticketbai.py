"""TicketBAI: la factura se firma en la entrada, así que el QR vuelve de inmediato.

    python examples/02_ticketbai.py

El emisor debe estar dado de alta con una hacienda `tbai-*`, y `provincia` tiene que
coincidir con ella.
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
            # Obligatorio en Álava, cuya hacienda rechaza las altas sin líneas de detalle.
            "lineas": [
                {
                    "descripcion": "Servicios de consultoría",
                    "cantidad": Decimal("1"),
                    "importeUnitario": Decimal("100.00"),  # sin IVA
                    "importeTotal": Decimal("121.00"),  # con IVA
                }
            ],
        }

        respuesta = client.ticketbai.crear(factura)

        # Ya firmada y encadenada: estos identificadores son definitivos y estables entre
        # reintentos, porque un duplicado se reproduce en lugar de volver a firmarse.
        print(f"idTbai: {respuesta['idTbai']}")
        print(f"URL:    {respuesta['urlValidacion']}")

        if qr := respuesta.get("qrBase64"):
            datos = qr.split(",", 1)[-1]  # quita el prefijo del data: URI si viene
            with open("tbai-qr.png", "wb") as fh:
                fh.write(base64.b64decode(datos))
            print("QR guardado en tbai-qr.png")

        # Solo el envío a la hacienda foral es asíncrono.
        verdicto = client.facturas.esperar_verdicto(
            respuesta["idFactura"], nif_emisor=NIF_EMISOR, timeout=120
        )
        print("registrada" if verdicto.registrada else f"estado: {verdicto.estado_envio}")


if __name__ == "__main__":
    main()
