# Contributing

Thanks for looking. A few things are worth knowing before you open a PR, because this
package has a narrower brief than most API clients.

## What belongs here, and what does not

This library is the **transport and ergonomics** layer. It knows that an amount travels
as a plain decimal string and that a date is `DD-MM-YYYY`. It deliberately does **not**
know whether an invoice is fiscally valid.

That line is not fussiness. The rules are set by the AEAT and three foral haciendas, they
change, and two of VeriBai's own date rules are still open decisions. A client that
pre-rejected payloads locally would go stale and start refusing invoices the API would
have accepted — and that is the one class of bug an integrator cannot work around. So:

- **Yes**: serialization, retries, pagination, error mapping, webhook verification,
  anything that removes a footgun in how the API is *called*.
- **No**: validating that a `tipoFactura` suits an operation, that a cuota matches its
  base, or that a `fechaOperacion` is permitted. The API is the authority.

## Setup

```bash
uv venv && uv sync --group dev
uv run pytest            # 250+ tests, all offline
uv run ruff check . && uv run ruff format .
uv run mypy
```

## Tests

No test in the default suite may reach the network. Everything is mocked at the HTTP
boundary with `responses`. This is a hard rule, not a preference: a real submission signs
a document and permanently advances a taxpayer's hash chain, and that is not something a
test run may do by accident. Tests that need real credentials are marked `integration`
and are opt-in.

Coverage is at 99% and should stay above 95%. More useful than the number: when you fix a
bug, add the test that would have caught it, and write the comment explaining **why** the
behaviour is what it is. Several tests here exist because a plausible-looking alternative
is wrong — that a retry after a network error is safe on some routes and not others, that
`aceptada_con_errores` is terminal, that an absent quota is not a zero one. Those comments
are the point.

## Style

- `ruff` for lint and format (100 columns), `mypy --strict` for types.
- Public method names mirror the API's endpoints, and field names stay the API's own
  Spanish, so the [API documentation](https://github.com/VeriBai) maps here without
  translation. Code, comments and docstrings are in English.
- Responses come back as plain dicts. Typed objects are for places where a wrong reading
  has a cost (`Verdicto`, `Pagina`, `webhooks.Entrega`) — adding models for everything
  else would turn an additive server change into a client-side breakage.

## Adding an endpoint

1. Read the handler or the OpenAPI spec — not the prose docs alone. They drift, in both
   directions.
2. Put it on the right resource class with the right base URL (invoicing vs management).
3. Decide `idempotente=` honestly. It is what licenses a retry after a network error, so
   it must be `True` only where VeriBai genuinely replays by identity.
4. Test the verb, the path, the body and at least one error the endpoint really returns.
5. Update the surface table in the README and add a CHANGELOG entry.

## Releasing

Maintainers only.

1. Bump `version` in `pyproject.toml` and add the `CHANGELOG.md` entry.
2. Merge to `main`.
3. Push a tag matching the version: `git tag v0.1.1 && git push origin v0.1.1`.

CI then verifies the tag matches `pyproject.toml`, runs the full suite, builds, and
**waits for approval on the `pypi` environment**. Merging alone never publishes, and a
tag alone does not either.

### One-time setup (not yet done)

**PyPI Trusted Publishing.** There is no API token anywhere, by design — PyPI has to be
told to trust this workflow instead. At <https://pypi.org/manage/account/publishing/>,
add a pending publisher:

| Field | Value |
|---|---|
| PyPI project name | `veribai` |
| Owner | `VeriBai` |
| Repository name | `veribai-python-client` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

Naming the environment matters: it means a workflow run that has not passed the required
reviewer cannot mint a PyPI token even if it somehow reached the publish step.

**Codecov.** Add a `CODECOV_TOKEN` repository secret from
<https://app.codecov.io>. Uploads are non-blocking (`fail_ci_if_error: false`), so the
suite stays green until it is set.
