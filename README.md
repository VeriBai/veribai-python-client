# veribai — cliente de Python

[![PyPI](https://img.shields.io/pypi/v/veribai.svg)](https://pypi.org/project/veribai/)
[![Python](https://img.shields.io/pypi/pyversions/veribai.svg)](https://pypi.org/project/veribai/)
[![Tests](https://github.com/VeriBai/veribai-python-client/actions/workflows/test.yml/badge.svg)](https://github.com/VeriBai/veribai-python-client/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/VeriBai/veribai-python-client/branch/main/graph/badge.svg)](https://codecov.io/gh/VeriBai/veribai-python-client)
[![License](https://img.shields.io/pypi/l/veribai.svg)](LICENSE)

Cliente oficial de Python para la API de [VeriBai](https://veribai.com) — envío de facturas
bajo los dos regímenes de facturación electrónica españoles: **VeriFactu** (AEAT) y
**TicketBAI** (las haciendas forales de Álava, Bizkaia y Gipuzkoa).

```bash
pip install veribai
```

```python
import veribai
from datetime import date
from decimal import Decimal

client = veribai.Client(api_key="...")  # sandbox por defecto

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

## Lo primero que hay que entender

**Un `200` de `crear` significa _aceptada_, no _presentada_.**

VeriBai ha recibido la factura, la ha validado y —en TicketBAI— ya la ha firmado y ha
avanzado de forma permanente la cadena de hash del obligado tributario. La autoridad
tributaria responde después, y *esa* respuesta es la que tiene valor legal. VeriFactu se
envía mediante un proceso que se ejecuta cada minuto; TicketBAI suele responder en segundos.

Es decir: hay dos momentos, no uno.

```python
respuesta = client.verifactu.crear(factura)  # aceptada
verdicto = client.facturas.esperar_verdicto(  # presentada, o rechazada
    respuesta["idFactura"], nif_emisor=nif, con_detalle=True
)

if verdicto.rechazada:
    # NO presentada. La obligación sigue abierta: corrige los datos y subsana.
    ...
elif verdicto.requiere_subsanacion:
    # Presentada, pero con errores. No se va a resolver sola.
    ...
```

En cuanto haya volumen, usa un webhook en lugar de hacer *polling*: cada consulta es una
llamada más contra un cupo mensual que es **por clave de API**.

## Qué aporta este paquete frente a usar `requests`

**Reintentos que saben cuándo un reintento es seguro.** Un `429` o un
`503 SHARDING_UNAVAILABLE` demuestran que el servidor rechazó la petición *antes* de hacer
nada, así que reintentar siempre es seguro. Una conexión caída no demuestra nada: puede que
la factura ya esté firmada y encolada. Por eso los errores de red solo se reintentan en las
rutas que VeriBai hace idempotentes por identidad (las rutas de factura, donde un reenvío
idéntico reproduce el registro original en lugar de crear uno segundo), y nunca en rutas
donde un duplicado sería un segundo objeto real.

**Importes y fechas en el formato exacto que exige la API.** Pasa `Decimal` y `date`; la
conversión se hace al salir. `float` se rechaza de plano: 0.1 no es exactamente 0.1 en coma
flotante binaria, y un céntimo de desviación en una cuota es un defecto fiscal, no una
molestia de redondeo. Tampoco se redondea nunca en silencio: un importe con más precisión de
la que admite el formato lanza una excepción, de modo que la decisión de redondear sigue
siendo tuya.

**Verificación de webhooks que verifica de verdad.** El HMAC se calcula sobre los **bytes
crudos de la petición**, así que el habitual `json.loads` → `json.dumps` lo invalida en
silencio. `veribai.webhooks.parse_entrega` verifica primero, parsea después, y te devuelve el
`idEntrega` determinista sobre el que deduplicar.

**La trampa del QR, resuelta.** API Gateway solo devuelve el PNG como bytes cuando la
*petición* envía `Accept: image/png`; con el `*/*` que mandan la mayoría de clientes por
defecto, el cuerpo es el **texto base64** del PNG aunque siga anunciándose como `image/png`
— lo escribes a un fichero y obtienes una imagen que no abre. `client.facturas.qr()` envía
siempre la cabecera y, aun así, comprueba el número mágico del PNG.

**Errores sobre los que se puede ramificar.** Cada fallo documentado se corresponde con una
excepción tipada que lleva el `code` de la API. Ramifica por el código, nunca por el estado
HTTP a secas: un `409` es un conflicto de sharding en `crear`, `ALREADY_CANCELLED` en
`anular`, y un límite de plan o un conflicto de autoemisor en `clientes/crear`.

Lo que deliberadamente **no** hace es replicar las reglas de validación fiscal. Las fijan
cuatro administraciones tributarias y cambian; un cliente que rechazara en local se quedaría
desactualizado y empezaría a rechazar facturas que la API habría aceptado. Aquí se comprueba
el formato; la legalidad la decide la API.

## Entornos

| | API de Facturación | API de Gestión |
|---|---|---|
| **test** (por defecto) | `sandbox.veribai.com` | `manage-api.veribai.com` |
| **live** | `api.veribai.com` | `manage-api.veribai.com` |

En facturación, la URL base *es* el entorno. La API de Gestión es una única pasarela que
resuelve el entorno a partir de la propia clave, y por eso ninguna llamada de gestión recibe
un parámetro `entorno`.

```python
client = veribai.Client(api_key="...", environment="live")
```

El sandbox es el valor por defecto a propósito: el coste de una factura equivocada en sandbox
es una prueba desperdiciada, y el de una factura equivocada en producción es un registro
fiscal presentado legalmente.

La configuración también puede venir del entorno, para que el mismo código pase de uno a otro
sin tocar nada:

```bash
export VERIBAI_API_KEY=...
export VERIBAI_ENVIRONMENT=live     # por defecto: test
```

> **LIVE no está probado en esta versión.** `api.veribai.com` todavía no se ha desplegado, así
> que seleccionar `live` emite un `LiveEnvironmentWarning` y las llamadas pueden responder
> `503 ENVIRONMENT_NOT_AVAILABLE`. La versión `1.0.0` queda reservada para la primera
> publicación posterior a que producción haya funcionado de verdad.

## Superficie de la API

Los nombres de los métodos reflejan los endpoints, y los nombres de campo son los de la
propia API —en español— así que todo lo que leas en la
[documentación de la API](https://veribai.com/docs/api) se traslada aquí sin
traducción.

| Grupo | Métodos |
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

Las respuestas son diccionarios de JSON decodificado. Es una decisión, no dejadez: la API
añade campos (hace poco llegaron tres en una sola semana), y unos modelos rígidos
convertirían un cambio aditivo del servidor en una rotura del cliente. Solo hay objetos
tipados donde una lectura equivocada cuesta algo: `Verdicto`, `Pagina`, `webhooks.Entrega`.

## Webhooks

Registrar un endpoint es la mitad del trabajo: las entregas no empiezan hasta que además
**vinculas clientes secundarios**. Un webhook sin clientes vinculados no emite nada, y esa es
la razón más frecuente de que una integración nueva no reciba nada.

```python
wh = client.webhooks.crear(
    nombre="Producción",
    url="https://ejemplo.com/veribai",  # https y host público, obligatorio
    secreto=os.environ["VERIBAI_WEBHOOK_SECRET"],
)
client.webhooks.vincular_clientes(wh["webhook"]["idWebhook"], ["B12345674"])
```

Recibirlos (aquí con Flask; en cualquier framework es igual):

```python
@app.post("/veribai")
def recibir():
    try:
        entrega = veribai.webhooks.parse_entrega(
            cuerpo=request.get_data(),  # bytes CRUDOS, antes de parsear el JSON
            cabeceras=request.headers,
            secreto=os.environ["VERIBAI_WEBHOOK_SECRET"],
        )
    except veribai.WebhookSignatureError:
        return "", 401

    if ya_procesado(entrega.id_entrega):  # al menos una vez: deduplicar es cosa tuya
        return "", 200

    if entrega.rechazada:
        motivo = entrega.motivo_rechazo  # el código y el motivo de la propia autoridad
        ...
    return "", 200
```

La entrega es **al menos una vez** y los duplicados son normales. Cada reintento lleva un
cuerpo idéntico byte a byte y el mismo `idEntrega` —un UUIDv5 determinista de
(webhook, factura, evento), nunca aleatorio—, así que es una clave de deduplicación sólida.
`factura.rechazada` no se puede excluir de una suscripción: un registro rechazado no se ha
presentado, y la obligación de presentarlo es del obligado tributario.

## Errores

```python
try:
    client.verifactu.crear(factura)
except veribai.IdentityConflictError as exc:
    # misma serie+número+fecha, distinto importe o tipo: es otra factura
    print(exc.code, exc.errors)
except veribai.ValidationError as exc:
    print(exc.errors)  # cadenas por campo, incluidos códigos de reglas de la AEAT
except veribai.RateLimitError as exc:
    print(exc.retry_after)  # ya se reintentó; esto es después de agotar la política
except veribai.APIError as exc:
    print(exc.status, exc.code, exc.request_id)
```

Ojo: un `403` en la superficie de clave de API normalmente **no** es un problema de permisos.
API Gateway responde `403 {"message": "Forbidden"}` —sin `code`— cuando la clave falta, es
desconocida o está deshabilitada. Ese caso se lanza como `AuthenticationError`, para que no
acabes buscando el error donde no está.

## Reintentos

```python
client = veribai.Client(
    api_key="...",
    retry=veribai.RetryPolicy(max_attempts=4, backoff_base=0.5, backoff_max=20.0),
    timeout=30.0,
)
```

`max_attempts=1` desactiva los reintentos. Se respeta `Retry-After` cuando el servidor lo
envía, y el *jitter* está activado por defecto para que una flota de workers no se
resincronice en el mismo segundo después de un throttle.

## Desarrollo

```bash
uv venv && uv pip install -e . --group dev
uv run pytest                 # tests y cobertura
uv run ruff check . && uv run ruff format --check .
uv run mypy
```

Ningún test de la suite por defecto habla con un entorno real de VeriBai ni con una
administración tributaria; todo está simulado en la frontera HTTP. Los tests marcados como
`integration` necesitan credenciales reales y son opcionales.

## Seguridad

Solo el propietario del repositorio puede hacer merge o publicar; las releases se construyen
en CI a partir de un commit de `main` que sube la versión, se publican en PyPI mediante OIDC
(Trusted Publishing, sin ningún token de larga duración) y llevan atestaciones de
procedencia. Para
reportar un problema, consulta [SECURITY.md](SECURITY.md) — por favor, no abras una issue
pública para una vulnerabilidad.

La lista de dependencias en tiempo de ejecución es deliberadamente de un solo paquete
(`requests`). Esta biblioteca envía registros fiscales legalmente vinculantes: cada
dependencia transitiva es superficie de ataque en la cadena de suministro.

## Licencia

Apache 2.0 — ver [LICENSE](LICENSE).
