# Changelog

Aquí se documentan todos los cambios relevantes del proyecto.
El formato sigue [Keep a Changelog](https://keepachangelog.com/es/1.1.0/), y el proyecto usa
[versionado semántico](https://semver.org/lang/es/).

Mientras el paquete sea `0.x`, las versiones menores pueden contener cambios incompatibles.

## [Unreleased]

### Cambiado

- **El texto de los mensajes de excepción y avisos cambia.** Se han eliminado las rayas (—)
  de toda la prosa del paquete, incluidos los mensajes que llegan al usuario, como el de
  `LiveEnvironmentWarning` y el de firma inválida de webhook. Los `code` y las clases de
  excepción no se tocan: si ramificas por `code`, como debes, esto no te afecta. Si haces
  coincidir texto de mensajes, sí.
- La descripción del paquete en PyPI pasa a `Official Python client for the VeriBai API:
  VeriFactu and TicketBAI invoice submission`.

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
- **La trampa del QR en base64, resuelta**: se envía siempre `Accept: image/png`, y el cuerpo
  se decodifica igualmente si la pasarela devolvió texto base64.
- **Validación de NIF contra el censo de la AEAT**, con `nombre` obligatorio en cada entrada:
  una cadena suelta se rechaza en local, con un `ValueError` que explica el motivo, en vez de
  gastar una llamada del cupo para recibir un `400`. Es obligatorio incluso para un CIF, cuyo
  nombre la AEAT ignora, porque la caché del censo se indexa por `(nif, nombre)`. Ojo:
  `identificado` significa que el NIF **existe**, no que el nombre enviado sea correcto. Para
  un CIF la razón social real vuelve en `nombreCenso` y compararla es cosa tuya.
- **Excepciones tipadas para cada código de error documentado**, incluido el `403` de API
  Gateway que en realidad significa «clave API desconocida» y no «sin permiso». Entre
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

[Unreleased]: https://github.com/VeriBai/veribai-python-client/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/VeriBai/veribai-python-client/releases/tag/v0.1.0
