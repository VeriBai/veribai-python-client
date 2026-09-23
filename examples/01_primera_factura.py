"""VeriFactu: emitir una factura, esperar el veredicto de la AEAT y descargar el QR.

python examples/01_primera_factura.py
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import veribai

NIF_EMISOR = os.environ["VERIBAI_NIF_EMISOR"]


def main() -> None:
    # `environment` explícito: `Client()` a secas sólo es sandbox si
    # VERIBAI_ENVIRONMENT no está definida. La clave sale de VERIBAI_API_KEY.
    with veribai.Client(environment="test") as client:
        cuenta = client.cuenta.obtener()
        print(f"entorno={cuenta['entorno']} plan={cuenta.get('plan')}")
        if not cuenta.get("facturacionActiva", True):
            raise SystemExit("la facturación está bloqueada en esta cuenta")

        factura = {
            "version": "1.0",
            "emisor": {"nif": NIF_EMISOR, "nombre": "Mi Empresa SL"},
            "cabecera": {
                "serie": "DEMO",
                "numero": date.today().strftime("%Y%m%d%H%M"),
                "fechaExpedicion": date.today(),  # un objeto date; se convierte solo
                "tipoFactura": "F1",
                "descripcion": "Servicios de consultoría",
            },
            "destinatario": {"nif": "B00000000", "nombre": "CLIENTE, SL"},
            "detalleDesglose": [
                {
                    "impuesto": "01",
                    "claveRegimen": "01",
                    "calificacionOperacion": "S1",
                    "baseImponible": Decimal("100.00"),  # Decimal, nunca float
                    "tipoImpositivo": Decimal("21"),
                    "cuotaRepercutida": Decimal("21.00"),
                }
            ],
            "totales": {"cuotaTotal": Decimal("21.00"), "importeTotal": Decimal("121.00")},
        }

        respuesta = client.verifactu.crear(factura)
        id_factura = respuesta["idFactura"]
        # Aceptada, todavía NO presentada. La AEAT aún no la ha visto.
        print(f"aceptada: {id_factura} estado={respuesta['estado']}")

        # El veredicto llega de forma asíncrona; VeriFactu envía en un tick por minuto.
        try:
            verdicto = client.facturas.esperar_verdicto(
                id_factura, nif_emisor=NIF_EMISOR, timeout=240, con_detalle=True
            )
        except veribai.VerdictTimeout as exc:
            # No es un fallo de la factura: está aceptada y todavía en curso.
            print(f"todavía en curso: {exc.ultimo_estado.get('estadoEnvio')}")
            return

        if verdicto.registrada:
            print(f"REGISTRADA · CSV {verdicto.csv_aeat}")
            client.facturas.guardar_qr(id_factura, nif_emisor=NIF_EMISOR, ruta="factura-qr.png")
            print("QR guardado en factura-qr.png")
        elif verdicto.requiere_subsanacion:
            # Presentada, pero con errores. No va a cambiar por sí sola.
            print("ACEPTADA CON ERRORES: hay que enviar una subsanación")
        else:
            print("RECHAZADA: no presentada; la obligación sigue abierta")
            for registro in (verdicto.detalle or {}).get("registros", []):
                codigo = registro.get("codigoRespuestaAeat")
                if codigo:
                    print(f"  [{codigo}] {registro.get('descripcionRespuestaAeat', '')}")


if __name__ == "__main__":
    main()
