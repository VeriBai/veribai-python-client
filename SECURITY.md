# Security policy

## Reporting a vulnerability

**Do not open a public issue.** Report privately through
[GitHub Security Advisories](https://github.com/VeriBai/veribai-python-client/security/advisories/new),
or by email to **soporte@veribai.com**.

Please include what you can: affected version, a minimal reproduction, and the impact
you see. You will get an acknowledgement within 3 working days and an assessment within
10. If the finding is confirmed we will agree a disclosure timeline with you and credit
you in the advisory unless you would rather we did not.

## Supported versions

The latest released `0.x` only, while the package is pre-1.0.

## What this package is trusted with

An integrator gives this library an API key that can **file tax records** on behalf of
real businesses, and a webhook secret that authenticates inbound callbacks. A malicious
release would therefore be able to submit or suppress fiscal filings, not merely read
data. The controls below exist because of that, not as ceremony.

### Supply chain

- **One runtime dependency** (`requests`). Every transitive package is attack surface, so
  the list is kept deliberately short and reviewed before it grows.
- **Publishing uses PyPI Trusted Publishing (OIDC)**. No long-lived API token exists, so
  there is no token to steal, leak or forget to rotate.
- **Releases are built in CI from a tagged commit** and published only after a human
  approves the `pypi` GitHub environment. Merging to `main` does not publish.
- **Build provenance attestations** are attached to every artifact, so a published wheel
  can be traced back to the workflow run and commit that produced it.
- **Every third-party GitHub Action is pinned to a commit SHA**, not a tag — a tag can be
  moved to point at different code after it was reviewed.
- **Workflows are read-only by default** (`permissions: contents: read`); jobs request
  more only where they need it, and `persist-credentials: false` keeps the checkout token
  out of the build environment.
- **`pip-audit` gates CI**, so a dependency with a known advisory fails the build rather
  than appearing on a dashboard later.
- CodeQL (`security-extended`) and `bandit` run on every push, plus CodeQL weekly so a
  newly published advisory is found without waiting for a commit.

### Repository

- Only the owner can merge to `main` or `develop`: protected branches, required code-owner
  review, no force pushes, no branch deletion, and a linear history.
- Commits on protected branches must be signed.
- Release tags are protected and cannot be moved once published.

### In the library itself

- The API key is sent only as the `x-api-key` header, to the VeriBai hosts the client was
  configured with. It is never logged, and `repr()` redacts it — including for keys short
  enough that showing a tail would show the key.
- Webhook signatures are compared with `hmac.compare_digest`, and the body is **not
  deserialized until the signature has passed**, so unauthenticated input never reaches a
  parser.
- The library holds no credentials of its own and writes nothing to disk except where you
  explicitly ask (`guardar_qr`).

## Scope

Vulnerabilities in the VeriBai **service** (the API this package talks to) also go to
soporte@veribai.com. Findings in `requests` or Python itself belong upstream — though
please do tell us if this package uses them in a way that makes an upstream issue worse.
