# Ejemplos

Todos los scripts de aquí se ejecutan contra el **sandbox** y necesitan dos cosas:

```bash
export VERIBAI_API_KEY=...
export VERIBAI_NIF_EMISOR=...     # un cliente secundario registrado en tu cuenta
```

Están ordenados: el `01` es el ciclo completo de VeriFactu y el resto dan por hecho que ya lo
has leído.

| Fichero | Qué muestra |
|---|---|
| [`01_primera_factura.py`](01_primera_factura.py) | Alta VeriFactu, espera del veredicto de la AEAT y lectura del QR |
| [`02_ticketbai.py`](02_ticketbai.py) | Alta TicketBAI: firmada en la entrada, así que el QR viene en la respuesta |
| [`03_webhook_flask.py`](03_webhook_flask.py) | Recibir entregas: verificar, deduplicar, actuar |
| [`04_alta_capacidad.py`](04_alta_capacidad.py) | Registrar dispositivos durante la ventana de preparación |

Ninguno toca producción. El `01` y el `02` sí envían facturas reales de sandbox a los entornos
de pruebas de las administraciones tributarias, que es justo para lo que sirve un sandbox.
