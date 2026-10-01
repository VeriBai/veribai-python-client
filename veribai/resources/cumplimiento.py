"""Compliance documents VeriBai publishes about itself."""

from __future__ import annotations

from typing import Any, Dict

from ._base import Recurso


class CumplimientoRecurso(Recurso):
    """VeriBai's own compliance paperwork."""

    def declaracion_responsable(self) -> Dict[str, Any]:
        """The current Declaración Responsable: the document certifying that
        VeriBai's sistema informático de facturación complies with the reglamento.

        Returns::

            {
                "url": "https://docshare.veribai.com/compliance/declaracion-responsable.pdf",
                "lastModified": "2026-06-20T09:14:22Z",
            }

        Prefer this over hardcoding the URL: you get ``lastModified`` as a change
        signal.

        The endpoint needs an API key; the document it points at does not, since it is
        anonymously readable by design, so a prospect, auditor or tax authority
        can read it without a VeriBai account. It is not a secret.
        """
        return dict(self._get("/v1/cumplimiento/declaracion-responsable").datos)


__all__ = ["CumplimientoRecurso"]
