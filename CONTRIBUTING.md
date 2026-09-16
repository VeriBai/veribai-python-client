# Cómo contribuir

Gracias por pasarte por aquí. Conviene saber un par de cosas antes de abrir un PR, porque
este paquete tiene un alcance más estrecho que la mayoría de clientes de API.

## Qué entra aquí y qué no

Esta biblioteca es la capa de **transporte y ergonomía**. Sabe que un importe viaja como una
cadena decimal y que una fecha es `DD-MM-YYYY`. Deliberadamente **no** sabe si una factura es
fiscalmente válida.

Esa línea no es manía. Las reglas las fijan la AEAT y tres haciendas forales, cambian, y dos
de las propias reglas de fechas de VeriBai siguen siendo decisiones abiertas. Un cliente que
rechazara payloads en local se quedaría desactualizado y empezaría a rechazar facturas que la
API habría aceptado — y ese es justo el tipo de bug que un integrador no puede esquivar. Así
que:

- **Sí**: serialización, reintentos, paginación, mapeo de errores, verificación de webhooks,
  cualquier cosa que elimine una trampa en *cómo se llama* a la API.
- **No**: validar que un `tipoFactura` encaja con una operación, que una cuota cuadra con su
  base, o que una `fechaOperacion` está permitida. La autoridad es la API.

## Puesta en marcha

```bash
uv venv && uv sync --group dev

uv run pytest            # más de 250 tests, todos sin red
uv run ruff check . && uv run ruff format .
uv run mypy
```

## Tests

Ningún test de la suite por defecto puede tocar la red. Todo se simula en la frontera HTTP con
`responses`. Es una regla dura, no una preferencia: un envío real firma un documento y avanza
de forma permanente la cadena de hash de un obligado tributario, y eso no es algo que una
ejecución de tests pueda hacer por accidente. Los tests que necesitan credenciales reales van
marcados como `integration` y son opcionales.

La cobertura está en el 99% y debe mantenerse por encima del 95%. Más útil que el número:
cuando arregles un bug, añade el test que lo habría cazado, y escribe el comentario que
explica **por qué** el comportamiento es el que es. Varios tests existen aquí porque una
alternativa de aspecto razonable es incorrecta — que un reintento tras un error de red es
seguro en unas rutas y no en otras, que `aceptada_con_errores` es un estado terminal, que un
cupo ausente no es un cupo a cero. Esos comentarios son el objetivo, no el adorno.

## Estilo

- `ruff` para lint y formato (100 columnas), `mypy --strict` para tipos.
- Los nombres de los métodos públicos reflejan los endpoints de la API, y los nombres de campo
  siguen siendo los suyos en español, para que la
  [documentación de la API](https://github.com/VeriBai) se traslade aquí sin traducción.
- **Idioma**: la documentación pública va en español (`README.md`, este fichero,
  `CHANGELOG.md`, `SECURITY.md` y `examples/`). El código va en inglés: docstrings,
  comentarios, mensajes de excepción, nombres de tests y mensajes de commit.
- Las respuestas vuelven como diccionarios simples. Los objetos tipados son para los sitios
  donde una lectura equivocada cuesta algo (`Verdicto`, `Pagina`, `webhooks.Entrega`);
  añadir modelos para todo lo demás convertiría un cambio aditivo del servidor en una rotura
  del cliente.

## Añadir un endpoint

1. Lee el handler o la especificación OpenAPI, no solo la documentación en prosa. Las dos se
   desincronizan, en ambos sentidos.
2. Ponlo en la clase de recurso correcta con la URL base correcta (facturación o gestión).
3. Decide `idempotente=` honestamente. Es lo que autoriza un reintento tras un error de red,
   así que solo puede ser `True` donde VeriBai reproduce de verdad por identidad.
4. Testea el verbo, la ruta, el cuerpo y al menos un error que el endpoint devuelva de verdad.
5. Actualiza la tabla de superficie del `README.md` y añade una entrada en el `CHANGELOG.md`.

## Publicar una versión

Solo mantenedores. **La versión de `pyproject.toml` es la única fuente de verdad**: no hay
ninguna etiqueta que empujar a mano.

1. Sube `version` en `pyproject.toml` y añade la entrada en `CHANGELOG.md`.
2. Haz merge a `main`.

Ya está. El workflow `release` se dispara con cualquier push a `main` que toque
`pyproject.toml`, comprueba si `v<version>` ya existe y, si es una versión nueva, ejecuta la
suite completa, construye los artefactos, publica en PyPI y **después** crea la etiqueta y la
release de GitHub.

Lo que dispara una publicación es el acto deliberado de cambiar la versión, no el merge: un
merge que no toque `version` no publica nada, porque la etiqueta ya existe. La etiqueta es el
*resultado* de una release, no su entrada — así, si la publicación falla o se rechaza, no
queda una etiqueta afirmando lo contrario.

Si el entorno `pypi` tiene revisores obligatorios configurados (ver abajo), el job de
publicación se queda esperando en GitHub → **Actions** → **Review deployments → pypi →
Approve and deploy**.

### Configuración inicial (pendiente)

**Trusted Publishing de PyPI.** No hay ningún token de API en ninguna parte, por diseño: hay
que decirle a PyPI que confíe en este workflow. En
<https://pypi.org/manage/account/publishing/>, añade un *pending publisher*:

| Campo | Valor |
|---|---|
| PyPI project name | `veribai` |
| Owner | `VeriBai` |
| Repository name | `veribai-python-client` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

Nombrar el entorno importa: significa que una ejecución del workflow que no haya pasado por el
revisor obligatorio no puede obtener un token de PyPI ni aunque llegue de algún modo al paso
de publicación.

**Entorno `pypi` en GitHub.** En Settings → Environments → `pypi`, marca **Required
reviewers** y añádete. Sin eso, el entorno existe pero no detiene nada.

> ⚠️ Esa opción solo aparece en repositorios **públicos**, o en repositorios privados de una
> organización con plan de pago. Mientras este repo sea privado en el plan gratuito, el
> entorno `pypi` no puede exigir aprobación y la publicación es automática. Las demás
> protecciones (Trusted Publishing, atestaciones, acciones fijadas por SHA, `pip-audit`
> bloqueante, revisión obligatoria del code owner para llegar a `main`) siguen en pie.

**Codecov.** Añade un secreto de repositorio `CODECOV_TOKEN` desde
<https://app.codecov.io>. Las subidas no bloquean (`fail_ci_if_error: false`), así que la
suite sigue en verde hasta que esté configurado.
