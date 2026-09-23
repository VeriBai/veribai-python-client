# veribai: cliente de Python

[![PyPI](https://img.shields.io/pypi/v/veribai.svg)](https://pypi.org/project/veribai/)
[![Python](https://img.shields.io/pypi/pyversions/veribai.svg)](https://pypi.org/project/veribai/)
[![Tests](https://github.com/VeriBai/veribai-python-client/actions/workflows/test.yml/badge.svg)](https://github.com/VeriBai/veribai-python-client/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/VeriBai/veribai-python-client/branch/main/graph/badge.svg)](https://codecov.io/gh/VeriBai/veribai-python-client)
[![License](https://img.shields.io/pypi/l/veribai.svg)](LICENSE)

Cliente oficial de Python para la API de [VeriBai](https://veribai.com?utm_source=readme&utm_medium=referral&utm_campaign=python-client&utm_content=readme-intro). Con él puedes enviar
facturas a los dos sistemas de facturación electrónica de España: **VeriFactu** (AEAT) y
**TicketBAI** (haciendas forales de Álava, Bizkaia y Gipuzkoa).

```bash
pip install veribai
```

```python
import veribai
from datetime import date
from decimal import Decimal

client = veribai.Client(api_key="...", environment="test")  # sandbox

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
        "destinatario": {"nif": "B00000000", "nombre": "CLIENTE, SL"},
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

Si el cliente no tiene NIF español, identifícalo con `idOtro` **en lugar de** `nif`, nunca los
dos. Por ejemplo, una entrega intracomunitaria exenta (E5) a una empresa alemana:

```python
"destinatario": {
    "nombre": "Kunde GmbH",
    "idOtro": {"codigoPais": "DE", "idType": "02", "id": "DE123456789"},  # 02 = NIF-IVA
},
"detalleDesglose": [
    {
        "claveRegimen": "01",
        "operacionExenta": "E5",  # en lugar de calificacionOperacion; sin tipo ni cuota
        "baseImponible": Decimal("100.00"),
    }
],
"totales": {"cuotaTotal": Decimal("0.00"), "importeTotal": Decimal("100.00")},
```

En TicketBAI el desglose es plano y, con destinatario extranjero, cada línea lleva
`tipoOperacion`. Una venta intracomunitaria con una línea exenta y otra no sujeta:

```python
"clavesRegimen": ["01"],
"desglose": [
    {
        "baseImponible": Decimal("1000.00"),
        "operacionExenta": "E5",
        "tipoOperacion": "entrega",
        "descripcion": "Entrega intracomunitaria de maquinaria",
    },
    {
        "baseImponible": Decimal("300.00"),
        "calificacionOperacion": "N2",
        "causaNoSujecion": "RL",  # reglas de localización
        "tipoOperacion": "servicios",
        "descripcion": "Instalación en destino",
    },
],
```

El cliente envía `idOtro` y estos campos tal cual. Qué combinaciones valen (por impuesto, por
clave o por provincia) lo comprueba la API, que responde `400` si no encajan.

---

## Antes de empezar

**Que `crear` devuelva un `200` significa que la factura está _aceptada_, no _presentada_.**

En ese momento VeriBai ya ha recibido y validado la factura y, si es TicketBAI, también la ha
firmado y la ha añadido a la cadena de hash del emisor, algo que ya no tiene vuelta atrás.
La respuesta de la administración tributaria llega más tarde, y es esa la que tiene validez
legal. Los envíos a VeriFactu salen en un proceso que se ejecuta cada minuto; TicketBAI suele
responder en pocos segundos.

Por tanto, cada factura pasa por dos momentos distintos:

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

Cuando empieces a tener volumen, pasa a webhooks en lugar de consultar el estado una y otra
vez: cada consulta cuenta para el cupo mensual, y ese cupo va **por clave API**.

## Qué te ahorras frente a usar `requests` directamente

**Reintentos solo cuando son seguros.** Un `429` o un `503 SHARDING_UNAVAILABLE` indican que
el servidor rechazó la petición *antes* de procesarla, así que siempre se pueden repetir.
Con una conexión cortada no hay forma de saberlo: la factura puede estar ya firmada y en
cola. Por eso los errores de red solo se reintentan en las rutas de factura, donde VeriBai
reconoce un reenvío idéntico y devuelve el registro original en vez de crear otro. En las
demás rutas un duplicado sería un segundo objeto real, y ahí nunca se reintenta.

**Importes y fechas en el formato exacto que pide la API.** Pasa `Decimal` y `date` y el
cliente se encarga de convertirlos. Los `float` se rechazan: en coma flotante 0.1 no es
exactamente 0.1, y un céntimo de diferencia en una cuota es un error fiscal, no un problema
de redondeo. Tampoco se redondea nada por tu cuenta: si un importe tiene más decimales de los
que admite el formato, se lanza una excepción y decides tú cómo redondear.

**Webhooks bien verificados.** El HMAC se calcula sobre los **bytes originales de la
petición**, así que hacer `json.loads` y luego `json.dumps` rompe la firma sin avisar.
`veribai.webhooks.parse_entrega` primero verifica y después parsea, y te devuelve el
`idEntrega` que necesitas para descartar duplicados.

**Excepciones con las que puedes decidir qué hacer.** Cada error documentado tiene su propia
excepción, con el `code` que devuelve la API. Decide según ese código y no solo por el estado
HTTP: un `409` puede ser un conflicto de identidad en `crear`, `ALREADY_CANCELLED` en
`anular`, o un límite del plan o un conflicto de autoemisor en `clientes/crear`.

Lo que este paquete **no** hace, a propósito, es repetir las reglas de validación fiscal.
Las definen cuatro administraciones tributarias y van cambiando; un cliente que validara en
local acabaría quedándose atrás y rechazando facturas que la API sí aceptaría. Aquí se
comprueba el formato, y si una factura es correcta lo decide la API.

## Entornos

| | API de Facturación | API de Gestión |
|---|---|---|
| **test** (por defecto) | `sandbox.veribai.com` | `manage-api.veribai.com` |
| **live** | `api.veribai.com` | `manage-api.veribai.com` |

En la API de Facturación, el entorno lo determina la URL base. La API de Gestión tiene una
sola URL para los dos entornos y deduce cuál usar a partir de la clave; por eso ninguna
llamada de gestión lleva un parámetro `entorno`.

```python
client = veribai.Client(api_key="...", environment="live")
```

El entorno se elige **en este orden**:

1. el argumento `environment=`;
2. la variable `VERIBAI_ENVIRONMENT`;
3. `"test"`.

> Es decir, `veribai.Client(api_key="...")` apunta al sandbox **solo si
> `VERIBAI_ENVIRONMENT` no está definida**. Te recomendamos pasar siempre `environment=`:
> tiene prioridad sobre la variable, así que no depende de cómo esté configurada la máquina
> donde se ejecuta tu código.

Si no se indica nada, se usa el sandbox, y es a propósito: una factura equivocada en el
sandbox es solo una prueba fallida, pero en producción es un registro fiscal presentado
de verdad.

Para saber en qué entorno estás sin hacer ninguna llamada:

```python
client.entorno  # 'test' | 'live'
client.origen_entorno  # de dónde viene: el argumento, la variable o el valor por defecto
client.invoicing_url  # la URL de facturación que se va a usar
```

Si quieres confirmarlo con el servidor, `client.cuenta.obtener()` devuelve el `entorno` que
la API asocia a tu clave, y ese es el dato fiable.

Equivocarse de entorno no hace que acabes presentando una factura donde no toca: **cada
clave pertenece a un único entorno**, así que la API de VeriBai rechaza con un
`AuthenticationError` una clave de TEST enviada a `api.veribai.com` o una de LIVE enviada al
sandbox.

También puedes configurarlo con variables de entorno, y así el mismo código funciona en los
dos entornos sin cambios:

```bash
export VERIBAI_API_KEY=...
export VERIBAI_ENVIRONMENT=live     # por defecto: test
```

> **LIVE todavía no está probado en esta versión.** `api.veribai.com` aún no está desplegada,
> así que al elegir `live` se emite un `LiveEnvironmentWarning` y las llamadas pueden
> devolver `503 ENVIRONMENT_NOT_AVAILABLE`. Publicaremos la versión `1.0.0` cuando producción
> esté funcionando.

## Métodos disponibles

Los métodos siguen los mismos nombres que los endpoints, y los campos se llaman igual que en
la API (en español), así que lo que leas en la
[documentación de la API](https://veribai.com/docs/api?utm_source=readme&utm_medium=referral&utm_campaign=python-client&utm_content=readme-api-docs) te sirve tal cual.

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

Las respuestas se devuelven como diccionarios con el JSON ya decodificado. Lo hemos
decidido así porque la API va incorporando campos nuevos (hace poco se añadieron tres en una
misma semana), y con modelos cerrados cada campo nuevo obligaría a actualizar el cliente.
Solo usamos objetos tipados donde leer mal un campo puede salir caro: `Verdicto`, `Pagina` y
`webhooks.Entrega`.

`client.facturas.qr()` devuelve directamente los bytes del PNG, listos para guardar en un
fichero, y `guardar_qr()` lo hace por ti.

## Webhooks

Registrar el endpoint no basta: no recibirás ninguna entrega hasta que le **vincules
clientes secundarios**. Un webhook sin clientes vinculados no envía nada, y es el motivo más
habitual de que una integración nueva no reciba eventos.

```python
wh = client.webhooks.crear(
    nombre="Producción",
    url="https://ejemplo.com/veribai",  # https y host público, obligatorio
    secreto=os.environ["VERIBAI_WEBHOOK_SECRET"],
)
client.webhooks.vincular_clientes(wh["webhook"]["idWebhook"], ["B12345674"])
```

Para recibirlos (el ejemplo usa Flask, pero en cualquier framework se hace igual):

```python
@app.post("/veribai")
def recibir():
    try:
        entrega = veribai.webhooks.parse_entrega(
            cuerpo=request.get_data(),  # los bytes originales, sin parsear el JSON
            cabeceras=request.headers,
            secreto=os.environ["VERIBAI_WEBHOOK_SECRET"],
        )
    except veribai.WebhookSignatureError:
        return "", 401

    if ya_procesado(entrega.id_entrega):  # puede llegar más de una vez: descarta duplicados
        return "", 200

    if entrega.rechazada:
        motivo = entrega.motivo_rechazo  # código y motivo que da la administración
        ...
    return "", 200
```

Cada evento se entrega **al menos una vez**, así que recibir duplicados es normal. Los
reintentos llevan exactamente el mismo cuerpo y el mismo `idEntrega`, un UUIDv5 que se
calcula a partir del webhook, la factura y el evento (nunca es aleatorio), así que puedes
usarlo con total seguridad para descartar duplicados.

No es posible darse de baja de `factura.rechazada`: una factura rechazada no se ha
presentado, y presentarla sigue siendo responsabilidad del obligado tributario.

## Errores

```python
try:
    client.verifactu.crear(factura)
except veribai.IdentityConflictError as exc:
    # misma serie, número y fecha, pero distinto importe o tipo: es otra factura
    print(exc.code, exc.errors)
except veribai.ValidationError as exc:
    print(exc.errors)  # un mensaje por campo, con los códigos de regla de la AEAT
except veribai.RateLimitError as exc:
    print(exc.retry_after)  # llega aquí después de agotar los reintentos
except veribai.APIError as exc:
    print(exc.status, exc.code, exc.request_id)
```

Un `403 {"message": "Forbidden"}` sin `code` **no** es un problema de permisos: la API de
VeriBai lo devuelve cuando falta la clave, no existe o está desactivada. Por eso se lanza
como `AuthenticationError` y no como error de permisos, para que busques el problema en el
sitio correcto.

## Reintentos

```python
client = veribai.Client(
    api_key="...",
    retry=veribai.RetryPolicy(max_attempts=4, backoff_base=0.5, backoff_max=20.0),
    timeout=30.0,
)
```

Con `max_attempts=1` se desactivan los reintentos. Si el servidor envía `Retry-After`, se
respeta, y por defecto se añade un margen aleatorio (*jitter*) a cada espera para que, si
tienes muchos workers, no vuelvan a lanzar todos las peticiones en el mismo segundo después
de un límite de velocidad.

## Desarrollo

```bash
uv venv && uv pip install -e . --group dev
uv run pytest                 # tests y cobertura
uv run ruff check . && uv run ruff format --check .
uv run mypy
```

Ningún test de la batería por defecto se conecta a VeriBai ni a ninguna administración
tributaria: todas las llamadas HTTP están simuladas. Los tests marcados como `integration`
necesitan credenciales reales y son opcionales.

## Seguridad

Solo el propietario del repositorio puede hacer merge o publicar versiones. Cada versión se
genera en CI a partir de un commit de `main` que actualiza el número de versión, se publica en
PyPI mediante OIDC (Trusted Publishing, sin tokens de larga duración) e incluye atestaciones
de procedencia. Si encuentras una vulnerabilidad, sigue las instrucciones de
[SECURITY.md](SECURITY.md) y no abras una issue pública.

En ejecución, el paquete depende de una sola librería (`requests`), y es intencionado: esta
librería envía registros fiscales con validez legal, y cada dependencia añadida es un punto
más por donde podría entrar un ataque a la cadena de suministro.

## Licencia

Apache 2.0. Consulta [LICENSE](LICENSE).
