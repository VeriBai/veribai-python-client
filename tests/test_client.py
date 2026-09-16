"""Client construction, environment selection and lifecycle."""

from __future__ import annotations

import warnings

import pytest
import requests

import veribai
from veribai.config import normalize_environment

from .conftest import MANAGE, SANDBOX


class TestConstruccion:
    def test_sandbox_por_defecto(self):
        # The cost of a mistaken sandbox invoice is a wasted test; the cost of a
        # mistaken production invoice is a filed tax record. Default accordingly.
        c = veribai.Client(api_key="k")
        assert c.entorno == "test"
        assert c.invoicing_url == SANDBOX
        assert c.management_url == MANAGE
        assert c.es_live is False

    def test_live_explicito(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", veribai.LiveEnvironmentWarning)
            c = veribai.Client(api_key="k", environment="live")
        assert c.entorno == "live"
        assert c.invoicing_url == "https://api.veribai.com"
        assert c.es_live is True

    def test_live_avisa_una_vez(self):
        # LIVE has never been deployed as of this release; saying so beats a
        # confusing 503 at the worst possible moment.
        with warnings.catch_warnings(record=True) as capturados:
            warnings.simplefilter("always")
            veribai.Client(api_key="k", environment="live")
        assert len(capturados) == 1
        assert issubclass(capturados[0].category, veribai.LiveEnvironmentWarning)

    def test_sandbox_no_avisa(self):
        with warnings.catch_warnings(record=True) as capturados:
            warnings.simplefilter("always")
            veribai.Client(api_key="k")
        assert capturados == []

    @pytest.mark.parametrize("alias", ["test", "TEST", " sandbox ", "pruebas"])
    def test_alias_de_test(self, alias):
        assert veribai.Client(api_key="k", environment=alias).entorno == "test"

    @pytest.mark.parametrize("alias", ["live", "prod", "production", "produccion"])
    def test_alias_de_live(self, alias):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            assert veribai.Client(api_key="k", environment=alias).entorno == "live"

    def test_entorno_desconocido_no_cae_en_ninguno(self):
        # A typo must not silently pick an environment — least of all LIVE.
        with pytest.raises(ValueError, match="unknown environment"):
            veribai.Client(api_key="k", environment="producion")

    def test_entorno_no_textual(self):
        with pytest.raises(ValueError, match="must be a string"):
            normalize_environment(1)  # type: ignore[arg-type]

    def test_hace_falta_una_clave(self, monkeypatch):
        monkeypatch.delenv("VERIBAI_API_KEY", raising=False)
        with pytest.raises(veribai.ConfigurationError, match="VERIBAI_API_KEY"):
            veribai.Client()

    def test_clave_desde_el_entorno(self, monkeypatch):
        monkeypatch.setenv("VERIBAI_API_KEY", "desde-el-entorno")
        assert veribai.Client().entorno == "test"

    def test_entorno_desde_la_variable(self, monkeypatch):
        monkeypatch.setenv("VERIBAI_API_KEY", "k")
        monkeypatch.setenv("VERIBAI_ENVIRONMENT", "live")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            assert veribai.Client().es_live is True

    def test_el_argumento_gana_a_la_variable(self, monkeypatch):
        monkeypatch.setenv("VERIBAI_ENVIRONMENT", "live")
        assert veribai.Client(api_key="k", environment="test").entorno == "test"

    def test_urls_sobreescribibles(self):
        c = veribai.Client(
            api_key="k", invoicing_url="http://localhost:1", management_url="http://localhost:2"
        )
        assert c.invoicing_url == "http://localhost:1"
        assert c.management_url == "http://localhost:2"

    def test_sesion_propia(self):
        sesion = requests.Session()
        c = veribai.Client(api_key="k", session=sesion)
        assert c._transport.session is sesion

    def test_user_agent_propio(self):
        c = veribai.Client(api_key="k", user_agent="mi-erp/2.0")
        assert c._transport.session.headers["User-Agent"] == "mi-erp/2.0"


class TestEstructura:
    def test_los_recursos_apuntan_a_la_api_correcta(self):
        c = veribai.Client(api_key="k")
        for nombre in ("verifactu", "ticketbai", "facturas", "registros", "cuenta"):
            assert getattr(c, nombre)._base == SANDBOX, nombre
        for nombre in (
            "nif",
            "clientes",
            "dispositivos",
            "representacion",
            "webhooks",
            "cumplimiento",
        ):
            assert getattr(c, nombre)._base == MANAGE, nombre

    def test_un_solo_transporte_compartido(self):
        # One connection pool, one retry policy — not eleven.
        c = veribai.Client(api_key="k")
        assert c.facturas._t is c.clientes._t

    def test_repr_sin_secretos(self):
        assert "k" not in repr(veribai.Client(api_key="k")).replace("veribai.Client", "")


class TestCicloDeVida:
    def test_context_manager_cierra_la_sesion(self):
        sesion = requests.Session()
        cerrada = []
        sesion.close = lambda: cerrada.append(True)  # type: ignore[method-assign]
        with veribai.Client(api_key="k", session=sesion):
            assert cerrada == []
        assert cerrada == [True]

    def test_close_es_idempotente(self):
        c = veribai.Client(api_key="k")
        c.close()
        c.close()

    def test_comprobar_llama_a_cuenta(self, mock_http):
        mock_http.add(mock_http.GET, f"{SANDBOX}/v1/cuenta", json={"entorno": "test"})
        with veribai.Client(api_key="k") as c:
            assert c.comprobar() == {"entorno": "test"}
