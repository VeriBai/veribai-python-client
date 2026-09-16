"""Recibir entregas de webhook.

    pip install flask
    flask --app examples/03_webhook_flask.py run --port 8000

Flask es lo de menos: los mismos tres pasos valen para cualquier framework — coger los
bytes CRUDOS, verificar y deduplicar.
"""

from __future__ import annotations

import os

from flask import Flask, request

import veribai

app = Flask(__name__)
SECRETO = os.environ["VERIBAI_WEBHOOK_SECRET"]

# Sustituto de tu base de datos. La entrega es al menos una vez, así que esto no es opcional.
_procesadas: set = set()


@app.post("/veribai")
def recibir() -> tuple[str, int]:
    try:
        entrega = veribai.webhooks.parse_entrega(
            cuerpo=request.get_data(),  # bytes CRUDOS — NO request.json
            cabeceras=request.headers,
            secreto=SECRETO,
        )
    except veribai.WebhookSignatureError:
        # Entrada sin verificar. Ni la parsees, ni le devuelvas el cuerpo al emisor en un log.
        return "", 401

    if entrega.id_entrega in _procesadas:
        return "", 200  # es un reintento; mismo cuerpo, mismo id
    _procesadas.add(entrega.id_entrega)

    if entrega.registrada:
        print(f"registrada {entrega.id_factura} ({entrega.sistema_fiscal})")
    elif entrega.rechazada:
        # NO presentada. La obligación de presentarla sigue siendo del obligado tributario,
        # y por eso este evento no se puede excluir de una suscripción.
        motivo = entrega.motivo_rechazo
        print(f"RECHAZADA {entrega.id_factura}: [{motivo.codigo}] {motivo.descripcion}")
        for extra in motivo.motivos_adicionales:
            # Corrígelos todos antes de reenviar: cada intento de TicketBAI avanza de forma
            # permanente la cadena de hash del obligado tributario.
            print(f"  además [{extra.codigo}] {extra.descripcion}")
    elif entrega.anulada:
        print(f"anulada {entrega.id_factura}")

    # Responde rápido. Tardar más de 10 s cuenta como fallo y se reintenta; 20 fallos
    # consecutivos suspenden el webhook. Encola el trabajo de verdad.
    return "", 200
