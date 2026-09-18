"""Representation mandate: ``/v1/clientes/{nif}/representacion/*``.

The document by which a secondary client authorises you to file on its behalf.
On **LIVE** it is a gate, not paperwork: until ``estadoRepresentacion`` reads
``firmado``, altas for that emisor answer ``403 REPRESENTATION_PENDING``.
"""

from __future__ import annotations

import base64
from typing import Any, Dict, Union
from urllib.parse import quote

from ._base import Recurso


class RepresentacionRecurso(Recurso):
    """Generate, sign and check the representation document for one client."""

    def generar(self, nif: str) -> Dict[str, Any]:
        """Produce the unsigned PDF and a signed download URL.

        The document type follows the client's ``hacienda``. If the client row is
        missing data the form needs, the ``400`` names the gaps in
        ``camposFaltantes`` using public field paths (``direccion.calle``), so it
        tells you what to fix rather than that something is wrong.
        """
        return dict(self._get(f"/v1/clientes/{_nif(nif)}/representacion/generar").datos)

    def firmar(
        self,
        nif: str,
        *,
        pdf: Union[bytes, str],
        certificado: Union[bytes, str],
        password: str,
    ) -> Dict[str, Any]:
        """Cloud-sign the document with a PKCS#12 certificate.

        Args:
            pdf: the unsigned PDF, as bytes or base64 text.
            certificado: the signer's ``.p12``, as bytes or base64 text.
            password: the ``.p12`` password.

        The certificate and its password travel to VeriBai over TLS to be used
        for this one signature. If that is not acceptable to the client (and for
        many it will not be) sign the PDF on their own machine and upload the
        result with :meth:`verificar` instead; the two paths end in the same
        stored mandate.
        """
        cuerpo = {
            "pdf": _b64(pdf),
            "certificado": _b64(certificado),
            "password": password,
        }
        return dict(
            self._post(f"/v1/clientes/{_nif(nif)}/representacion/firmar", json=cuerpo).datos
        )

    def verificar(self, nif: str, *, pdf_firmado: Union[bytes, str]) -> Dict[str, Any]:
        """Upload a document signed elsewhere, for verification and storage."""
        return dict(
            self._post(
                f"/v1/clientes/{_nif(nif)}/representacion/verificar",
                json={"pdfFirmado": _b64(pdf_firmado)},
            ).datos
        )

    def estado(self, nif: str) -> Dict[str, Any]:
        """Current mandate status.

        ``firmaEnCurso`` is true while a generated document is waiting for its
        ``verificar``: a document is out in the world, unreturned.
        """
        return dict(self._get(f"/v1/clientes/{_nif(nif)}/representacion/estado").datos)

    def cancelar_firma(self, nif: str) -> Dict[str, Any]:
        """Abandon an in-flight signing, so a fresh document can be generated."""
        return dict(self._delete(f"/v1/clientes/{_nif(nif)}/representacion/firma-en-curso").datos)


def _b64(valor: Union[bytes, str]) -> str:
    """Accept raw bytes or text that is already base64."""
    if isinstance(valor, (bytes, bytearray)):
        return base64.b64encode(bytes(valor)).decode("ascii")
    return valor


def _nif(nif: str) -> str:
    return quote(str(nif), safe="")


__all__ = ["RepresentacionRecurso"]
