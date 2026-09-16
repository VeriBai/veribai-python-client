"""VeriFactu: issue an invoice, wait for the AEAT verdict, fetch the QR.

python examples/01_primera_factura.py
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import veribai

NIF_EMISOR = os.environ["VERIBAI_NIF_EMISOR"]


def main() -> None:
    with veribai.Client() as client:  # sandbox, key from VERIBAI_API_KEY
        cuenta = client.cuenta.obtener()
        print(f"entorno={cuenta['entorno']} plan={cuenta.get('plan')}")
        if not cuenta.get("facturacionActiva", True):
            raise SystemExit("billing is blocking new invoices on this account")

        factura = {
            "version": "1.0",
            "emisor": {"nif": NIF_EMISOR, "nombre": "Mi Empresa SL"},
            "cabecera": {
                "serie": "DEMO",
                "numero": date.today().strftime("%Y%m%d%H%M"),
                "fechaExpedicion": date.today(),  # a date object; converted for you
                "tipoFactura": "F1",
                "descripcion": "Servicios de consultoría",
            },
            "destinatario": {"nif": "B98765432", "nombre": "Cliente Ejemplo SL"},
            "detalleDesglose": [
                {
                    "impuesto": "01",
                    "claveRegimen": "01",
                    "calificacionOperacion": "S1",
                    "baseImponible": Decimal("100.00"),  # Decimal, never float
                    "tipoImpositivo": Decimal("21"),
                    "cuotaRepercutida": Decimal("21.00"),
                }
            ],
            "totales": {"cuotaTotal": Decimal("21.00"), "importeTotal": Decimal("121.00")},
        }

        respuesta = client.verifactu.crear(factura)
        id_factura = respuesta["idFactura"]
        # Accepted — NOT yet filed. The AEAT has not seen it.
        print(f"aceptada: {id_factura} estado={respuesta['estado']}")

        # The verdict arrives asynchronously; VeriFactu submits on a minute tick.
        try:
            verdicto = client.facturas.esperar_verdicto(
                id_factura, nif_emisor=NIF_EMISOR, timeout=240, con_detalle=True
            )
        except veribai.VerdictTimeout as exc:
            # Not a failure of the invoice — it is accepted and still in flight.
            print(f"still in flight: {exc.ultimo_estado.get('estadoEnvio')}")
            return

        if verdicto.registrada:
            print(f"REGISTRADA · CSV {verdicto.csv_aeat}")
            client.facturas.guardar_qr(id_factura, nif_emisor=NIF_EMISOR, ruta="factura-qr.png")
            print("QR written to factura-qr.png")
        elif verdicto.requiere_subsanacion:
            # Filed, but with errors. It will never change on its own.
            print("ACEPTADA CON ERRORES — send a subsanación")
        else:
            print("RECHAZADA — not filed; the obligation is still open")
            for registro in (verdicto.detalle or {}).get("registros", []):
                codigo = registro.get("codigoRespuestaAeat")
                if codigo:
                    print(f"  [{codigo}] {registro.get('descripcionRespuestaAeat', '')}")


if __name__ == "__main__":
    main()
