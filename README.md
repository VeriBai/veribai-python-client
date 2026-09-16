# veribai — Python client

[![PyPI](https://img.shields.io/pypi/v/veribai.svg)](https://pypi.org/project/veribai/)
[![Python](https://img.shields.io/pypi/pyversions/veribai.svg)](https://pypi.org/project/veribai/)
[![Tests](https://github.com/VeriBai/veribai-python-client/actions/workflows/test.yml/badge.svg)](https://github.com/VeriBai/veribai-python-client/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/VeriBai/veribai-python-client/branch/main/graph/badge.svg)](https://codecov.io/gh/VeriBai/veribai-python-client)
[![License](https://img.shields.io/pypi/l/veribai.svg)](LICENSE)

Official Python client for the [VeriBai](https://veribai.com) API — invoice submission
under Spain's two electronic-invoicing regimes: **VeriFactu** (AEAT) and **TicketBAI**
(the Álava, Bizkaia and Gipuzkoa foral haciendas).

```bash
pip install veribai
```

```python
import veribai
from datetime import date
from decimal import Decimal

client = veribai.Client(api_key="...")  # sandbox by default

respuesta = client.verifactu.crear(
    {
        "version": "1.0",
        "emisor": {"nif": "B12345674", "nombre": "Ejemplo SL"},
        "cabecera": {
            "serie": "A",
            "numero": "1",
            "fechaExpedicion": date(2026, 9, 15),
            "tipoFactura": "F1",
            "descripcion": "Servicios de consultoría",
        },
        "destinatario": {"nif": "B98765432", "nombre": "Cliente SL"},
        "detalleDesglose": [
            {
                "claveRegimen": "01",
                "calificacionOperacion": "S1",
                "baseImponible": Decimal("100.00"),
                "tipoImpositivo": Decimal("21"),
                "cuotaRepercutida": Decimal("21.00"),
            }
        ],
        "totales": {"cuotaTotal": Decimal("21.00"), "importeTotal": Decimal("121.00")},
    }
)

verdicto = client.facturas.esperar_verdicto(respuesta["idFactura"], nif_emisor="B12345674")
print(verdicto.registrada, verdicto.csv_aeat)
```

---

## The one thing to understand first

**A `200` from `crear` means _accepted_, not _filed_.**

VeriBai has taken the invoice, validated it, and — for TicketBAI — already signed it
and permanently advanced the taxpayer's hash chain. The tax authority answers
afterwards, and *that* answer is the one with legal weight. VeriFactu is submitted by
a pipeline that ticks every minute; TicketBAI usually hears back in seconds.

So there are two moments, not one:

```python
respuesta = client.verifactu.crear(factura)  # accepted
verdicto = client.facturas.esperar_verdicto(  # filed, or rejected
    respuesta["idFactura"], nif_emisor=nif, con_detalle=True
)

if verdicto.rechazada:
    # NOT filed. The obligation is still open — correct the data and subsanar.
    ...
elif verdicto.requiere_subsanacion:
    # Filed, but with errors. It will never resolve on its own.
    ...
```

At any volume, use a webhook instead of polling — each poll is an API call against a
monthly quota that is **per API key**.

## What this package does that `requests` does not

**Retries that know when a retry is safe.** A `429` or a `503 SHARDING_UNAVAILABLE`
proves the server refused before doing anything, so retrying is always safe. A dropped
connection proves nothing — the invoice may already be signed and queued. So network
errors are retried only on the routes VeriBai makes idempotent by identity (the invoice
routes, where an identical resubmission replays the original record instead of creating
a second one), and never on routes where a duplicate would be a real second object.

**Amounts and dates in the shapes the API demands.** Pass `Decimal` and `date`; they are
converted on the way out. `float` is refused outright — 0.1 is not exactly 0.1 in binary
floating point, and a cent of drift in a cuota is a fiscal defect, not a rounding
nuisance. Amounts are never silently rounded either: an amount with more precision than
the format allows raises, so the rounding decision stays yours.

**Webhook verification that actually verifies.** The HMAC covers the **raw request
bytes**, so the usual `json.loads` → `json.dumps` round-trip silently invalidates it.
`veribai.webhooks.parse_entrega` verifies first, parses second, and hands back the
deterministic `idEntrega` you should deduplicate on.

**The QR trap, absorbed.** API Gateway only returns the PNG as bytes when the *request*
sends `Accept: image/png`; with the `*/*` most clients default to, the body is the
base64 *text* of the PNG while still claiming to be `image/png` — write it to a file and
you get an image that will not open. `client.facturas.qr()` always sends the header and
checks the PNG magic number anyway.

**Errors you can branch on.** Every documented failure maps to a typed exception carrying
the API's `code`. Branch on the code, never on the status alone: a `409` means a sharding
conflict on `crear`, `ALREADY_CANCELLED` on `anular`, and a plan-limit or self-client
conflict on `clientes/crear`.

What it deliberately does **not** do is mirror fiscal validation rules. Those are set by
four tax authorities and they move; a client that pre-rejected locally would go stale and
start refusing invoices the API would have accepted. Format is checked here; legality is
the API's call.

## Environments

| | Invoicing API | Management API |
|---|---|---|
| **test** (default) | `sandbox.veribai.com` | `manage-api.veribai.com` |
| **live** | `api.veribai.com` | `manage-api.veribai.com` |

The invoicing base URL *is* the environment. The Management API is a single gateway that
resolves the environment from the key, which is why no management call takes an
`entorno` parameter.

```python
client = veribai.Client(api_key="...", environment="live")
```

Sandbox is the default on purpose: the cost of a mistaken sandbox invoice is a wasted
test, and the cost of a mistaken production invoice is a legally filed tax record.

Configuration can also come from the environment, so the same code moves between them
without an edit:

```bash
export VERIBAI_API_KEY=...
export VERIBAI_ENVIRONMENT=live     # default: test
```

> **LIVE is unexercised in this release.** `api.veribai.com` has not been deployed yet,
> so selecting `live` emits a `LiveEnvironmentWarning` and calls may answer
> `503 ENVIRONMENT_NOT_AVAILABLE`. Version `1.0.0` is reserved for the first release made
> after production has actually run.

## API surface

Method names mirror the endpoints, and field names are the API's own — Spanish
throughout — so anything you read in the [API documentation](https://github.com/VeriBai)
maps here without translation.

| Group | Methods |
|---|---|
| `client.verifactu` | `crear` · `subsanar` · `anular` |
| `client.ticketbai` | `crear` · `subsanar` · `anular` |
| `client.facturas` | `listar` · `iterar` · `obtener` · `buscar` · `estado` · `verdicto` · `esperar_verdicto` · `qr` · `guardar_qr` · `xml` |
| `client.registros` | `listar` · `iterar` · `obtener` |
| `client.cuenta` | `obtener` · `consumo` |
| `client.nif` | `validar` |
| `client.clientes` | `listar` · `asientos` · `crear` · `obtener` · `modificar` · `cambiar_estado` · `activar` · `desactivar` |
| `client.dispositivos` | `listar` · `registrar` · `dar_de_baja` · `promover` · `solicitar_activacion` · `reservar_series_centralizadas` · `liberar_serie_centralizada` |
| `client.representacion` | `generar` · `firmar` · `verificar` · `estado` · `cancelar_firma` |
| `client.webhooks` | `listar` · `crear` · `obtener` · `modificar` · `eliminar` · `listar_clientes` · `vincular_clientes` · `desvincular_cliente` |
| `client.cumplimiento` | `declaracion_responsable` |

Responses are plain decoded JSON dicts. That is a decision, not laziness: the API adds
fields (three arrived in one week recently), and rigid models would turn an additive
server change into a client-side breakage. Typed objects exist only where a wrong reading
has a cost — `Verdicto`, `Pagina`, `webhooks.Entrega`.

## Webhooks

Registering an endpoint is half the job: deliveries do not start until you **link
secondary clients** to it. A webhook with no linked clients is silent, and that is the
commonest reason a new integration sees nothing arrive.

```python
wh = client.webhooks.crear(
    nombre="Producción",
    url="https://ejemplo.com/veribai",  # https, public host only
    secreto=os.environ["VERIBAI_WEBHOOK_SECRET"],
)
client.webhooks.vincular_clientes(wh["webhook"]["idWebhook"], ["B12345674"])
```

Receiving one (Flask shown; any framework works the same way):

```python
@app.post("/veribai")
def recibir():
    try:
        entrega = veribai.webhooks.parse_entrega(
            cuerpo=request.get_data(),  # RAW bytes, before any JSON parsing
            cabeceras=request.headers,
            secreto=os.environ["VERIBAI_WEBHOOK_SECRET"],
        )
    except veribai.WebhookSignatureError:
        return "", 401

    if ya_procesado(entrega.id_entrega):  # at-least-once: dedup is your job
        return "", 200

    if entrega.rechazada:
        motivo = entrega.motivo_rechazo  # the authority's own code + reason
        ...
    return "", 200
```

Delivery is **at-least-once** and duplicates are normal. Every retry carries a
byte-identical body and the same `idEntrega` — a deterministic UUIDv5 of
(webhook, invoice, event), never random — so it is a sound dedup key.
`factura.rechazada` cannot be excluded from a subscription: a rejected record was not
filed, and the filing obligation is the taxpayer's.

## Errors

```python
try:
    client.verifactu.crear(factura)
except veribai.IdentityConflictError as exc:
    # same serie+número+fecha, different importe or tipo — a different invoice
    print(exc.code, exc.errors)
except veribai.ValidationError as exc:
    print(exc.errors)  # field-named strings, incl. AEAT rule codes
except veribai.RateLimitError as exc:
    print(exc.retry_after)  # already retried; this is after the policy gave up
except veribai.APIError as exc:
    print(exc.status, exc.code, exc.request_id)
```

Note that `403` on the API-key surface is usually **not** a permission problem: API
Gateway answers `403 {"message": "Forbidden"}` — with no `code` — when the key itself is
missing, unknown or disabled. That case is raised as `AuthenticationError`, so you are
not sent hunting for the wrong bug.

## Retries

```python
client = veribai.Client(
    api_key="...",
    retry=veribai.RetryPolicy(max_attempts=4, backoff_base=0.5, backoff_max=20.0),
    timeout=30.0,
)
```

`max_attempts=1` disables retries. `Retry-After` is honoured when the server sends it,
and jitter is on by default so a fleet of workers does not resynchronise on the same
second after a throttle.

## Development

```bash
uv venv && uv pip install -e . --group dev
uv run pytest                 # tests + coverage
uv run ruff check . && uv run ruff format --check .
uv run mypy
```

No test in the default suite talks to a real VeriBai environment or a tax authority;
everything is mocked at the HTTP boundary. Tests marked `integration` need real
credentials and are opt-in.

## Security

Only the repository owner can merge or publish; releases are built in CI from a tagged
commit, published to PyPI via OIDC Trusted Publishing (no long-lived token exists), and
carry build provenance attestations. See [SECURITY.md](SECURITY.md) to report an issue —
please do not open a public issue for a vulnerability.

The runtime dependency list is deliberately one package (`requests`). This library
submits legally binding fiscal records; every transitive dependency is supply-chain
surface.

## License

Apache 2.0 — see [LICENSE](LICENSE).
