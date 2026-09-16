"""Receiving webhook deliveries.

    pip install flask
    flask --app examples/03_webhook_flask.py run --port 8000

Flask is incidental — the same three steps apply to any framework: take the RAW bytes,
verify, then deduplicate.
"""

from __future__ import annotations

import os

from flask import Flask, request

import veribai

app = Flask(__name__)
SECRETO = os.environ["VERIBAI_WEBHOOK_SECRET"]

# Stand-in for your database. Delivery is at-least-once, so this is not optional.
_procesadas: set = set()


@app.post("/veribai")
def recibir() -> tuple[str, int]:
    try:
        entrega = veribai.webhooks.parse_entrega(
            cuerpo=request.get_data(),  # RAW bytes — NOT request.json
            cabeceras=request.headers,
            secreto=SECRETO,
        )
    except veribai.WebhookSignatureError:
        # Unverified input. Do not parse it, do not log the body back.
        return "", 401

    if entrega.id_entrega in _procesadas:
        return "", 200  # a retry; identical body, identical id
    _procesadas.add(entrega.id_entrega)

    if entrega.registrada:
        print(f"registrada {entrega.id_factura} ({entrega.sistema_fiscal})")
    elif entrega.rechazada:
        # NOT filed. The filing obligation is still the taxpayer's, which is why this
        # event cannot be excluded from a subscription.
        motivo = entrega.motivo_rechazo
        print(f"RECHAZADA {entrega.id_factura}: [{motivo.codigo}] {motivo.descripcion}")
        for extra in motivo.motivos_adicionales:
            # Fix every one before resubmitting: each TicketBAI attempt permanently
            # advances the taxpayer's hash chain.
            print(f"  also [{extra.codigo}] {extra.descripcion}")
    elif entrega.anulada:
        print(f"anulada {entrega.id_factura}")

    # Answer fast. Slower than 10s counts as a failure and is retried; 20 consecutive
    # failures suspend the webhook. Queue the real work.
    return "", 200
