"""Compliance documents VeriBai publishes about itself."""

from __future__ import annotations

from typing import Any, Dict

from ._base import Recurso


class CumplimientoRecurso(Recurso):
    """VeriBai's own compliance paperwork."""

    def declaracion_responsable(self) -> Dict[str, Any]:
        """The current Declaración Responsable — the document certifying that
        VeriBai's sistema informático de facturación complies with the reglamento.

        Prefer this over hardcoding the URL: you get ``lastModified`` as a change
        signal and a clean 404 before any document exists, instead of a link that
        silently breaks for your users.

        The endpoint needs an API key; the document it points at does not — it is
        anonymously readable by design, so a prospect, auditor or tax authority
        can read it without a VeriBai account. It is not a secret.
        """
        return dict(self._get("/v1/cumplimiento/declaracion-responsable").datos)


__all__ = ["CumplimientoRecurso"]
