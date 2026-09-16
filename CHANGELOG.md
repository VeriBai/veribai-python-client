# Changelog

Aquí se documentan todos los cambios relevantes del proyecto.
El formato sigue [Keep a Changelog](https://keepachangelog.com/es/1.1.0/), y el proyecto usa
[versionado semántico](https://semver.org/lang/es/).

Mientras el paquete sea `0.x`, las versiones menores pueden contener cambios incompatibles.
**La `1.0.0` queda reservada para la primera publicación posterior a que el entorno LIVE de
VeriBai haya funcionado de verdad** — es una señal honesta para los integradores, no una
medalla de madurez.

## [Unreleased]

Puesta al día con los cambios de la API del 2026-09-16 (CERTIFY M-16).

### Cambiado — **incompatible**

- **Se deja de soportar Python 3.9**; el mínimo pasa a ser **3.10** (`requires-python = ">=3.10"`).
  Quien siga en 3.9 no recibirá esta versión: `pip` se quedará en la última compatible en lugar
  de romperse.
- **Se añade Python 3.14** a la matriz de CI y a los classifiers. La matriz cubre ahora
  3.10–3.14 en Linux, macOS y Windows.
- `client.nif.validar()` ahora exige `nombre` en cada entrada. Una cadena suelta
  (`validar(["B26682641"])`) se rechaza en local con un `ValueError` que explica el motivo,
  en lugar de gastar una llamada para recibir un `400 VALIDATION_ERROR`. Es obligatorio
  incluso para un CIF, cuyo nombre la AEAT ignora, porque la caché del censo se indexa por
  `(nif, nombre)`: una entrada cacheada con el nombre vacío podría después devolver
  `identificado` para un DNI/NIE consultado con el nombre equivocado.
- `client.nif.validar()` pierde el parámetro `forzar`. Desde el 2026-09-16 la API responde
  `400` si llega en la superficie de clave de API; solo sigue vivo en la ruta JWT del panel,
  donde respalda el botón «Revalidar».
- La documentación pública (`README.md`, `CONTRIBUTING.md`, `SECURITY.md`, este changelog y
  los ejemplos) pasa a estar en español. El código —docstrings, comentarios y mensajes de
  excepción— sigue en inglés.
- El workflow de publicación se dispara ahora al subir `version` en `pyproject.toml` y hacer
  merge a `main`; la etiqueta la crea CI después de publicar. Ya no hay que empujarla a mano.

### Añadido

- `XmlPersistError` para el `500 XML_PERSIST_ERROR` de TicketBAI, con una propiedad
  `reintentable`. El mismo código cubre dos situaciones opuestas y solo el mensaje las separa:
  en `subsanar`/`anular` no se firmó ni se encoló nada y el reintento es correcto; en `crear`
  la factura **ya está firmada y el eslabón de la cadena sellado**, reintentar devuelve
  `409 INVOICE_SIGNING_IN_FLIGHT` indefinidamente y hace falta reparación manual. El cliente
  ya solo reintenta la primera variante.
- `RepresentationSigningError` (`409 SIGNING_IN_PROGRESS`), `SignatureVerificationError`
  (la familia `SIGNATURE_*` de `representacion.verificar`) y `CertificateError`
  (`400 CERT_ERROR`, fichero `.p12` o contraseña incorrectos).
- `DATABASE_ERROR` y `AUTH_ERROR` se suman a los `500` documentados como reintentables, así
  que ahora se reintentan también en rutas no idempotentes.
- `CF_NOT_CONFIGURED` deja de reintentarse: es un fallo de despliegue y seguirá ahí dentro de
  veinte segundos.

### Documentación

- `nif.validar()` documenta que `identificado` significa que el NIF **existe**, no que el
  nombre enviado sea correcto: para un CIF la AEAT ignora el nombre y devuelve la razón social
  real en `nombreCenso`, y compararlos es cosa tuya; para un DNI/NIE el nombre sí forma parte
  del veredicto.
- Un NIF del que el censo no dice nada ya no es un `503` para todo el lote, sino un `200` con
  `estado: no_procesado` para esa entrada. `AeatUnavailableError` queda reservado para un
  fallo real de transporte.
- `cuenta.consumo()` documenta `observadoEn` y que el único aviso fiable de haber agotado el
  cupo es un `429`.

## [0.1.0] — 2026-09-15

Primera versión pública. Beta: la superficie de la API está completa y testeada, el entorno de
producción todavía no se ha ejercitado.

### Añadido

- `veribai.Client`, que cubre toda la superficie accesible con clave de API de las dos APIs de
  VeriBai — 36 rutas entre VeriFactu, TicketBAI, la lectura de facturas, los registros de
  envío, la cuenta, la validación de NIF en el censo, los clientes secundarios, los
  dispositivos de Alta capacidad, los mandatos de representación, los webhooks y los
  documentos de cumplimiento.
- **Reintentos que distinguen un rechazo de un resultado desconocido.** Un `429` o un `503`
  documentado como seguro se reintentan siempre; un error de red se reintenta solo en las
  rutas que VeriBai reproduce por identidad, nunca donde un duplicado sería un segundo objeto
  real.
- **`esperar_verdicto()`** — hace *polling* hasta que la administración ha respondido de
  verdad, y modela `aceptada_con_errores` como estado terminal, porque no se resuelve solo.
- **`veribai.webhooks.parse_entrega()`** — verificación HMAC sobre los bytes crudos de la
  petición, en tiempo constante y sin deserializar nada antes de que pase la firma; expone el
  `idEntrega` determinista sobre el que deduplicar.
- **Serialización de `Decimal`/`date`/`time`** a los formatos exactos que definen los esquemas
  de la AEAT y de TicketBAI. `float` se rechaza para importes; los importes nunca se redondean
  en silencio.
- **La trampa del QR en base64, resuelta** — se envía siempre `Accept: image/png`, y el cuerpo
  se decodifica igualmente si la pasarela devolvió texto base64.
- Excepciones tipadas para cada código de error documentado, incluido el `403` de API Gateway
  que en realidad significa «clave de API desconocida» y no «sin permiso».
- Utilidades de paginación por cursor, con protección frente a un cursor que se repite.
- Sandbox por defecto; LIVE hay que seleccionarlo explícitamente y avisa de que no está
  ejercitado.

[Unreleased]: https://github.com/VeriBai/veribai-python-client/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/VeriBai/veribai-python-client/releases/tag/v0.1.0
