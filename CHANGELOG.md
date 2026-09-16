# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

While the package is `0.x`, minor versions may contain breaking changes.
**`1.0.0` is reserved for the first release made after the VeriBai LIVE environment has
actually run** — it is meant as an honest signal to integrators, not a maturity badge.

## [Unreleased]

## [0.1.0] — 2026-09-15

First public release. Beta: the API surface is complete and tested, the production
environment is not yet exercised.

### Added

- `veribai.Client` covering the whole API-Key surface of both VeriBai APIs — 36 paths
  across VeriFactu, TicketBAI, the invoice read surface, submission records, account,
  NIF census validation, secondary clients, Alta capacidad devices, representation
  mandates, webhooks and compliance documents.
- **Retry semantics that distinguish a refusal from an unknown outcome.** A `429` or a
  documented retry-safe `503` is always retried; a network error is retried only on the
  routes VeriBai replays by identity, never where a duplicate would be a real second
  object.
- **`esperar_verdicto()`** — polls until the tax authority has actually answered, and
  models `aceptada_con_errores` as terminal, because it never resolves on its own.
- **`veribai.webhooks.parse_entrega()`** — HMAC verification over the raw request bytes,
  constant-time, with no deserialization before the signature passes; exposes the
  deterministic `idEntrega` to deduplicate on.
- **`Decimal`/`date`/`time` serialization** to the exact formats the AEAT and TicketBAI
  schemas define. `float` is refused for money; amounts are never silently rounded.
- **The QR base64 trap absorbed** — `Accept: image/png` is always sent, and the body is
  decoded if the gateway returned base64 text anyway.
- Typed exceptions for every documented error code, including the API Gateway `403`
  that actually means "unknown API key" rather than "not allowed".
- Cursor pagination helpers with a guard against a repeating cursor.
- Sandbox by default; LIVE must be selected explicitly and warns that it is unexercised.

[Unreleased]: https://github.com/VeriBai/veribai-python-client/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/VeriBai/veribai-python-client/releases/tag/v0.1.0
