# Changelog

Aquí se documentan todos los cambios relevantes del proyecto.
El formato sigue [Keep a Changelog](https://keepachangelog.com/es/1.1.0/), y el proyecto usa
[versionado semántico](https://semver.org/lang/es/).

Mientras el paquete sea `0.x`, las versiones menores pueden contener cambios incompatibles.

## [0.2.2] - 2026-09-23

### Documentación

- Ejemplo en el README de un destinatario extranjero con `idOtro` (`{codigoPais?, idType, id}`,
  en lugar de `nif`). El cliente no valida `idOtro` ni las claves por impuesto: la API responde
  `400`.
- Ejemplo en el README de una factura TicketBAI intracomunitaria (`clavesRegimen`, líneas con
  `operacionExenta`, `causaNoSujecion` y `tipoOperacion`). Los campos nuevos de TicketBAI
  viajan sin cambios en el cliente.
- El NIF de destinatario de los ejemplos (`B98765432`) tenía el dígito de control mal y la API
  ahora lo rechaza con `400`. Sustituido por `B00000000`, un marcador: pon ahí el NIF de tu
  cliente. El ejemplo de `client.nif.validar` usa el mismo.

## [0.2.1] - 2026-09-23

### Cambiado

- **`client.facturas.qr()` usa la nueva respuesta JSON de la API.** `GET /v1/facturas/{id}/qr`
  ya no devuelve un cuerpo binario `image/png`, sino `{"qrBase64": ..., "urlValidacion": ...}`,
  con los mismos campos que la respuesta de alta. El método sigue devolviendo los bytes del
  PNG y ahora lanza `VeriBaiError` si `qrBase64` falta o no es un PNG. Ya no se envía
  `Accept: image/png`.
- `qrBase64` es base64 sin prefijo `data:`, tanto aquí como en las respuestas de alta.

## [0.2.0] - 2026-09-22

Primera batería de pruebas contra el entorno TEST real, ejecutada el 2026-09-22 instalando el
paquete publicado en PyPI. Todo lo funcional pasó: alta, verdicto, QR, XML, anulación,
paginación, idempotencia y firma de webhooks, en VeriFactu y en TicketBAI. Los cambios de
abajo son lo que esa sesión dejó al descubierto.

### Añadido

- **`RateLimitError.cuota_agotada`**, que separa las dos situaciones distintas que comparten
  el `429`. Un *throttle* es una ráfaga por encima del límite por segundo y se despeja al
  segundo siguiente; un cupo mensual agotado seguirá agotado cuatro intentos después. Las dos
  llegan **sin campo `code`**, así que `code` vale `None` en ambas y no las
  distingue: este es el único sitio de la biblioteca donde la regla de «ramifica siempre por
  `code`» no tiene nada que ofrecer, y `cuota_agotada` es lo que hay que mirar en su lugar.
  Solo se deduce cuando no hay `code`, de modo que un `429` propio de VeriBai con su código
  nunca se confunde con el cupo de la clave.
- **`RetryPolicy.espera_excesiva()`**, que responde si la espera que pide el servidor es más
  larga de lo que el cliente está dispuesto a bloquear.

### Cambiado

- **Un `429` por cupo mensual agotado ya no se reintenta.** Antes se reintentaba cualquier
  `429`, así que agotar el cupo gastaba los cuatro intentos y unos tres segundos y medio para
  llegar al mismo error. Nada se había ejecutado, así que reintentar era *seguro*, pero no
  *útil*. Un *throttle* se sigue reintentando igual que siempre.
- **Un `Retry-After` ya no se recorta a `backoff_max`.** Recortarlo en silencio convertía un
  «espera 600 segundos» en una siesta de 20 y un segundo rechazo. Ahora `espera()` devuelve la
  cifra tal cual la envió el servidor y, cuando supera `backoff_max`, el cliente **deja de
  reintentar y lanza la excepción** con `retry_after` intacto: una espera así de larga es una
  decisión de quien llama, que es el único que sabe si le compensa. Es el único cambio de esta
  entrega que se puede notar desde fuera.

### Documentación

- **El cursor de paginación es opaco, y ahora el docstring lo dice entero.** El backend lo
  selló el 2026-09-22: era base64 legible y ahora es un token cifrado, ligado al inquilino, al
  *endpoint* y al entorno que lo emitió, y **caduca a las 24 horas**. Documentado que no se
  inspecciona ni se construye, que no se guarda entre ejecuciones (para reanudar, re-derive la
  posición con `fecha_inicio`/`fecha_fin`, nunca con un cursor almacenado) y que no se lleva de
  un *endpoint*, un entorno o una cuenta a otra. La lista de causas de `400 INVALID_CURSOR`
  estaba incompleta: faltaban «caducado» y «emitido para otro sitio». El cliente ya trataba el
  cursor como opaco, así que el sellado no rompió nada.
- **`Verdicto` explica las dos formas en que responde `GET /v1/facturas/{id}/estado`**, que es
  lo que más confusión causó durante las pruebas. Una factura registrada trae `estadoFactura` y
  **no** `estadoEnvio`; una en vuelo, y una rechazada (porque una factura rechazada nunca llega
  a ser una entidad registrada), traen `estadoEnvio` y **no** `estadoFactura`. Por eso
  `registrada` mira los dos campos y `rechazada` solo mira `estado_envio`. Verificado contra
  sandbox en los dos sistemas fiscales.
- **`ticketbai`: el cuerpo es *más plano* que el de VeriFactu, no plano.** El docstring decía
  «plano» a secas, y eso solo vale para `anular`. `crear` exige un `emisor` anidado (`nif` y
  `nombre`) y una lista `desglose` cuyas líneas son `baseImponible`/`tipoImpositivo`/`cuota`,
  no el `detalleDesglose`/`cuotaRepercutida` de VeriFactu.
- **`cuenta.obtener()` enumera los valores de `estadoCuenta`** y avisa de que
  `pago_pendiente` es una ventana de gracia, no un corte: es la semana posterior a un impago,
  durante la cual se sigue facturando y `facturacionActiva` sigue en `True`. Solo `suspendida`
  bloquea las llamadas que mutan, con un `402`; las lecturas no se bloquean en ningún estado.
  `desconocido` significa que no se pudo leer el estado, no que pase algo malo.
- Los nombres de los planes se renombraron en el backend el 2026-09-21 (`test` a `sandbox`,
  `minimum` a `esencial`, `premium` a `plataforma`, `enterprise` a `dedicado`). El cliente no
  fija ninguno: `plan` y `estadoCuenta` viajan tal cual, así que no hizo falta tocar código.
  Solo se actualizó un *fixture* de prueba que todavía decía `minimum`.

## [0.1.1] - 2026-09-18

### Cambiado

- **El texto de los mensajes de excepción y avisos cambia.** Se han eliminado las rayas (—)
  de toda la prosa del paquete, incluidos los mensajes que llegan al usuario, como el de
  `LiveEnvironmentWarning` y el de firma inválida de webhook. Los `code` y las clases de
  excepción no se tocan: si ramificas por `code`, como debes, esto no te afecta. Si haces
  coincidir texto de mensajes, sí.
- La descripción del paquete en PyPI pasa a `Official Python client for the VeriBai API:
  VeriFactu and TicketBAI invoice submission`.

### Documentación

- Toda la documentación en español se ha reescrito siguiendo la voz de marca de VeriBai.
- Corregido en `README.md`: un `409` en `crear` es un conflicto de **identidad**
  (`INVOICE_IDENTITY_CONFLICT`), no de sharding. `SHARDING_UNAVAILABLE` es un `503`.
- `CONTRIBUTING.md` afirmaba que el entorno `pypi` de GitHub no puede exigir aprobación en un
  repositorio privado con plan gratuito. Sí puede: la 0.1.0 esperó a que un revisor la
  aprobara. Documentado también que `Workflow permissions` tiene que estar en
  **Read and write**, o el job `tag` falla con `403` después de publicar en PyPI.

## [0.1.0] - 2026-09-18

Primera versión pública. Beta: la superficie de la API está completa y testeada, el entorno de
producción todavía no se ha ejercitado.

### Requisitos

- **Python 3.10–3.14**, probado en CI sobre Linux, macOS y Windows.
- Una única dependencia en tiempo de ejecución: `requests`. Esta biblioteca envía registros
  fiscales legalmente vinculantes, así que cada dependencia transitiva es superficie de ataque.

### Añadido

- `veribai.Client`, que cubre toda la superficie accesible con clave API de las dos APIs de
  VeriBai: 36 rutas entre VeriFactu, TicketBAI, la lectura de facturas, los registros de
  envío, la cuenta, la validación de NIF en el censo, los clientes secundarios, los
  dispositivos de Alta capacidad, los mandatos de representación, los webhooks y los
  documentos de cumplimiento.
- **Reintentos que distinguen un rechazo de un resultado desconocido.** Un `429` o un `503`
  documentado como seguro se reintentan siempre; un error de red se reintenta solo en las
  rutas que VeriBai reproduce por identidad, nunca donde un duplicado sería un segundo objeto
  real. Los `500` que la API documenta como reintentables (incluidos `DATABASE_ERROR` y
  `AUTH_ERROR`) se reintentan incluso en rutas no idempotentes, mientras que
  `CF_NOT_CONFIGURED` no se reintenta nunca: es un fallo de despliegue y seguirá ahí dentro de
  veinte segundos.
- **`esperar_verdicto()`**: hace *polling* hasta que la administración ha respondido de
  verdad, y modela `aceptada_con_errores` como estado terminal, porque no se resuelve solo.
- **`veribai.webhooks.parse_entrega()`**: verificación HMAC sobre los bytes crudos de la
  petición, en tiempo constante y sin deserializar nada antes de que pase la firma; expone el
  `idEntrega` determinista sobre el que deduplicar. Un receptor debe tolerar un evento al que
  no se suscribió: la suscripción puede cambiar sin que se redespliegue tu handler.
- **Serialización de `Decimal`/`date`/`time`** a los formatos exactos que definen los esquemas
  de la AEAT y de TicketBAI. `float` se rechaza para importes; los importes nunca se redondean
  en silencio.
- **QR siempre como bytes PNG**: se envía `Accept: image/png` y, si el cuerpo llega como
  texto base64, se decodifica igualmente.
- **Validación de NIF contra el censo de la AEAT**, con `nombre` obligatorio en cada entrada:
  una cadena suelta se rechaza en local, con un `ValueError` que explica el motivo, en vez de
  gastar una llamada del cupo para recibir un `400`. Es obligatorio incluso para un CIF, cuyo
  nombre la AEAT ignora, porque la caché del censo se indexa por `(nif, nombre)`. Ojo:
  `identificado` significa que el NIF **existe**, no que el nombre enviado sea correcto. Para
  un CIF la razón social real vuelve en `nombreCenso` y compararla es cosa tuya.
- **Excepciones tipadas para cada código de error documentado**, incluido el `403` sin
  `code` que en realidad significa «clave API desconocida» y no «sin permiso». Entre
  ellas: `XmlPersistError`, que separa las dos situaciones opuestas que comparte el
  `500 XML_PERSIST_ERROR` de TicketBAI: en `subsanar`/`anular` no se firmó ni se encoló nada y
  el reintento es correcto; en `crear` la factura **ya está firmada y el eslabón de la cadena
  sellado**, así que reintentar devuelve `409 INVOICE_SIGNING_IN_FLIGHT` indefinidamente y hace
  falta reparación manual. También `RepresentationSigningError` (`409 SIGNING_IN_PROGRESS`),
  `SignatureVerificationError` (la familia `SIGNATURE_*` de `representacion.verificar`) y
  `CertificateError` (`400 CERT_ERROR`, fichero `.p12` o contraseña incorrectos).
- Utilidades de paginación por cursor, con protección frente a un cursor que se repite.
- **Selección de entorno explícita y auditable.** El entorno se resuelve en un único orden:
  el argumento `environment=`, la variable `VERIBAI_ENVIRONMENT` y, como último recurso,
  `"test"`. Un `Client(api_key="...")` a secas es sandbox solo si esa variable no está
  definida, así que el `README.md` y los ejemplos pasan `environment=` de forma explícita:
  el argumento gana siempre, y es lo que hace que merezca la pena escribirlo. Un
  `environment=""` se rechaza en lugar de caer en la variable, por el mismo motivo por el que
  se rechaza una errata.
- `Client.origen_entorno` dice de dónde salió el entorno: el argumento, la variable o el
  valor por defecto. `entorno` dice *dónde* estás; esto dice *por qué*, que es lo que falta
  en una línea de log cuando el LIVE no lo eligió nadie por escrito.
- `LiveEnvironmentWarning` nombra quién eligió LIVE. Un `environment="live"` es alguien
  diciéndolo; un `VERIBAI_ENVIRONMENT=live` es un despliegue decidiéndolo por código que no
  menciona producción en ninguna parte, y el aviso es el único sitio donde eso consta.

### Documentación

- La documentación pública (`README.md`, `CONTRIBUTING.md`, `SECURITY.md`, este changelog y
  los ejemplos) está en español, que es el idioma de quienes presentan ante la AEAT y las
  haciendas forales. El código (docstrings, comentarios y mensajes de excepción) está en
  inglés.
- `cuenta.consumo()` documenta `observadoEn` y que el único aviso fiable de haber agotado el
  cupo es un `429`: la cifra se refresca por ciclos y puede ir minutos por detrás.

[0.2.2]: https://github.com/VeriBai/veribai-python-client/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/VeriBai/veribai-python-client/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/VeriBai/veribai-python-client/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/VeriBai/veribai-python-client/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/VeriBai/veribai-python-client/releases/tag/v0.1.0
