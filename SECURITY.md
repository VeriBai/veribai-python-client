# Política de seguridad

## Cómo reportar una vulnerabilidad

**No abras una issue pública.** Repórtala en privado a través de
[GitHub Security Advisories](https://github.com/VeriBai/veribai-python-client/security/advisories/new),
o por correo a **soporte@veribai.com**.

Incluye lo que puedas: versión afectada, una reproducción mínima y el impacto que ves.
Recibirás acuse de recibo en 3 días laborables y una valoración en 10. Si se confirma el
hallazgo, VeriBai acordará contigo un calendario de divulgación y te acreditará en el aviso,
salvo que prefieras que no.

## Versiones soportadas

Solo la última `0.x` publicada, mientras el paquete siga siendo anterior a la 1.0.

## Qué se le confía a este paquete

Un integrador le entrega a esta biblioteca una clave API capaz de **presentar registros
fiscales** en nombre de empresas reales, y un secreto de webhook que autentica las llamadas
entrantes. Una release maliciosa podría, por tanto, presentar o suprimir declaraciones
fiscales, no solo leer datos. Los controles de abajo existen por eso.

### Cadena de suministro

- **Una sola dependencia en tiempo de ejecución** (`requests`). Cada paquete transitivo es
  superficie de ataque, así que la lista se mantiene deliberadamente corta y se revisa antes
  de que crezca.
- **La publicación usa Trusted Publishing de PyPI (OIDC)**. No existe ningún token de API de
  larga duración, así que no hay token que robar, filtrar u olvidarse de rotar.
- **Las releases se construyen en CI**, nunca en la máquina de nadie. Lo que dispara una
  publicación es subir `version` en `pyproject.toml`: un merge a `main` que no cambie la
  versión no publica nada. La etiqueta y la release de GitHub se crean *después* de una
  publicación correcta, de modo que una etiqueta siempre corresponde a algo que se publicó
  de verdad.
- **El job de publicación corre en el entorno `pypi` de GitHub**, que puede exigir la
  aprobación de una persona con *required reviewers*. Esa protección solo está disponible en
  repositorios públicos o en planes de pago; mientras este repositorio sea privado en el plan
  gratuito, el entorno no bloquea nada y llegar a `main` (revisión obligatoria del code owner,
  ramas protegidas) es la barrera efectiva.
- **Cada artefacto lleva atestaciones de procedencia** (*build provenance*), de modo que un
  wheel publicado se puede rastrear hasta la ejecución del workflow y el commit que lo
  produjeron.
- **Cada GitHub Action de terceros está fijada a un SHA de commit**, no a una etiqueta: una
  etiqueta se puede mover para apuntar a código distinto del que se revisó.
- **Los workflows son de solo lectura por defecto** (`permissions: contents: read`); los jobs
  piden más solo donde lo necesitan, y `persist-credentials: false` mantiene el token del
  checkout fuera del entorno de build.
- **`pip-audit` bloquea el CI**, así que una dependencia con un aviso conocido rompe la build
  en lugar de aparecer más tarde en un panel.
- CodeQL (`security-extended`) y `bandit` se ejecutan en cada push, y CodeQL además
  semanalmente, para que un aviso recién publicado se detecte sin esperar a un commit.

### Repositorio

- Solo el propietario puede hacer merge a `main` o `develop`: ramas protegidas, revisión
  obligatoria del code owner, sin force push, sin borrado de rama e historial lineal.
- Los commits en ramas protegidas deben ir firmados.
- Las etiquetas de release están protegidas y no se pueden mover una vez publicadas.

### En la propia biblioteca

- La clave API se envía únicamente como cabecera `x-api-key`, y solo a los hosts de VeriBai
  con los que se configuró el cliente. Nunca se registra en logs, y `repr()` la censura,
  incluso para claves lo bastante cortas como para que mostrar el final fuera mostrar la
  clave.
- Las firmas de webhook se comparan con `hmac.compare_digest`, y el cuerpo **no se
  deserializa hasta que la firma ha pasado**, de modo que una entrada no autenticada nunca
  llega a un parser.
- La biblioteca no guarda credenciales propias y no escribe nada en disco salvo donde se lo
  pidas explícitamente (`guardar_qr`).

## Alcance

Las vulnerabilidades del **servicio** VeriBai (la API con la que habla este paquete) también
van a soporte@veribai.com. Los hallazgos en `requests` o en el propio Python corresponden a
sus proyectos. Aun así, repórtalo si este paquete los usa de una forma que agrave el
problema original.
