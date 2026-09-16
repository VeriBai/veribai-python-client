# Examples

Every script here runs against the **sandbox** and needs two things:

```bash
export VERIBAI_API_KEY=...
export VERIBAI_NIF_EMISOR=...     # a secondary client registered on your account
```

They are ordered: `01` is the whole VeriFactu round trip and the rest assume you have
read it.

| File | What it shows |
|---|---|
| [`01_primera_factura.py`](01_primera_factura.py) | VeriFactu alta, waiting for the AEAT verdict, reading the QR |
| [`02_ticketbai.py`](02_ticketbai.py) | TicketBAI alta — signed at ingress, so the QR is in the response |
| [`03_webhook_flask.py`](03_webhook_flask.py) | Receiving deliveries: verify, deduplicate, act |
| [`04_alta_capacidad.py`](04_alta_capacidad.py) | Registering devices during the preparation window |

None of them touches production. `01` and `02` do submit real sandbox invoices to the
tax authorities' test environments, which is the point of a sandbox.
