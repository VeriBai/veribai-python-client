"""The invoice read surface, the QR trap, and waiting for a verdict."""

from __future__ import annotations

import base64
import datetime as dt
import json
import zlib

import pytest

import veribai
from veribai.errors import SubmissionInProgressError, VerdictTimeout

from .conftest import SANDBOX, error

# A minimal but genuine 1x1 PNG, so the magic-number check is tested against a
# real file rather than a placeholder.
PNG = (
    b"\x89PNG\r\n\x1a\n"
    + b"\x00\x00\x00\rIHDR"
    + b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    + zlib.crc32(b"IHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00").to_bytes(4, "big")
    + b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


class TestListado:
    def test_una_pagina(self, client, mock_http):
        mock_http.add(
            mock_http.GET,
            f"{SANDBOX}/v1/facturas",
            json={"facturas": [{"idFactura": "A"}, {"idFactura": "B"}], "proximaPagina": None},
        )
        pagina = client.facturas.listar("B12345674")
        assert len(pagina) == 2
        assert pagina.total_en_pagina == 2
        assert pagina.hay_mas is False
        assert [f["idFactura"] for f in pagina] == ["A", "B"]

    def test_filtros_van_en_la_query(self, client, mock_http):
        mock_http.add(mock_http.GET, f"{SANDBOX}/v1/facturas", json={"facturas": []})
        client.facturas.listar(
            "B12345674", estado="registrada", sistema_fiscal="verifactu", limite=50
        )
        query = mock_http.calls[0].request.params
        assert query == {
            "nifEmisor": "B12345674",
            "estado": "registrada",
            "sistemaFiscal": "verifactu",
            "limite": "50",
        }

    def test_los_filtros_no_enviados_no_aparecen(self, client, mock_http):
        mock_http.add(mock_http.GET, f"{SANDBOX}/v1/facturas", json={"facturas": []})
        client.facturas.listar("B12345674")
        assert mock_http.calls[0].request.params == {"nifEmisor": "B12345674"}

    def test_iterar_recorre_las_paginas(self, client, mock_http):
        mock_http.add(
            mock_http.GET,
            f"{SANDBOX}/v1/facturas",
            json={"facturas": [{"idFactura": "A"}], "proximaPagina": "c1"},
        )
        mock_http.add(
            mock_http.GET,
            f"{SANDBOX}/v1/facturas",
            json={"facturas": [{"idFactura": "B"}], "proximaPagina": None},
        )
        assert [f["idFactura"] for f in client.facturas.iterar("B12345674")] == ["A", "B"]
        assert mock_http.calls[1].request.params["cursor"] == "c1"

    def test_un_cursor_que_se_repite_no_da_vueltas_para_siempre(self, client, mock_http):
        # An unbounded loop over a paginated API is how a monthly quota disappears.
        for _ in range(5):
            mock_http.add(
                mock_http.GET,
                f"{SANDBOX}/v1/facturas",
                json={"facturas": [{"idFactura": "A"}], "proximaPagina": "siempre-el-mismo"},
            )
        assert len(list(client.facturas.iterar("B12345674"))) == 2

    def test_max_paginas(self, client, mock_http):
        for _ in range(3):
            mock_http.add(
                mock_http.GET,
                f"{SANDBOX}/v1/facturas",
                json={"facturas": [{"idFactura": "A"}], "proximaPagina": "c"},
            )
        assert len(list(client.facturas.iterar("B12345674", max_paginas=2))) == 2


class TestDetalle:
    def test_obtener(self, client, mock_http):
        mock_http.add(
            mock_http.GET, f"{SANDBOX}/v1/facturas/FAC-1", json={"factura": {"idFactura": "FAC-1"}}
        )
        assert client.facturas.obtener("FAC-1", nif_emisor="B1")["factura"]["idFactura"] == "FAC-1"

    def test_el_id_se_codifica_en_la_url(self, client, mock_http):
        # ids are opaque; anything could be in one, including a slash.
        mock_http.add(mock_http.GET, f"{SANDBOX}/v1/facturas/a%2Fb", json={})
        client.facturas.obtener("a/b", nif_emisor="B1")
        assert "a%2Fb" in mock_http.calls[0].request.url

    def test_buscar_normaliza_la_fecha(self, client, mock_http):
        mock_http.add(mock_http.GET, f"{SANDBOX}/v1/facturas/buscar", json={"factura": {}})
        client.facturas.buscar(
            nif_emisor="B1", numero="12", fecha_expedicion=dt.date(2026, 1, 5), serie="A"
        )
        query = mock_http.calls[0].request.params
        assert query["fechaExpedicion"] == "05-01-2026"
        assert query["serie"] == "A" and query["numero"] == "12"

    def test_buscar_sin_serie(self, client, mock_http):
        # An invoice issued without a serie is a real case, not a missing value.
        mock_http.add(mock_http.GET, f"{SANDBOX}/v1/facturas/buscar", json={})
        client.facturas.buscar(nif_emisor="B1", numero="12", fecha_expedicion="05-01-2026")
        assert "serie" not in mock_http.calls[0].request.params


class TestQr:
    def test_bytes_devueltos_tal_cual(self, client, mock_http):
        mock_http.add(
            mock_http.GET,
            f"{SANDBOX}/v1/facturas/F1/qr",
            body=PNG,
            content_type="image/png",
        )
        assert client.facturas.qr("F1", nif_emisor="B1") == PNG

    def test_siempre_se_pide_accept_image_png(self, client, mock_http):
        # API Gateway only decodes the payload to bytes when the REQUEST says so.
        mock_http.add(mock_http.GET, f"{SANDBOX}/v1/facturas/F1/qr", body=PNG)
        client.facturas.qr("F1", nif_emisor="B1")
        assert mock_http.calls[0].request.headers["Accept"] == "image/png"

    def test_base64_de_texto_se_decodifica(self, client, mock_http):
        # The trap: same Content-Type, but the body is the base64 TEXT of the PNG.
        # Written straight to a file it produces an image that will not open.
        mock_http.add(
            mock_http.GET,
            f"{SANDBOX}/v1/facturas/F1/qr",
            body=base64.b64encode(PNG),
            content_type="image/png",
        )
        assert client.facturas.qr("F1", nif_emisor="B1") == PNG

    def test_data_uri_se_tolera(self, client, mock_http):
        cuerpo = b"data:image/png;base64," + base64.b64encode(PNG)
        mock_http.add(mock_http.GET, f"{SANDBOX}/v1/facturas/F1/qr", body=cuerpo)
        assert client.facturas.qr("F1", nif_emisor="B1") == PNG

    def test_algo_que_no_es_png_ni_base64_se_devuelve_intacto(self, client, mock_http):
        # Better to hand back what arrived than to invent a decoding of it.
        mock_http.add(mock_http.GET, f"{SANDBOX}/v1/facturas/F1/qr", body=b"?? no soy un png")
        assert client.facturas.qr("F1", nif_emisor="B1") == b"?? no soy un png"

    def test_base64_que_no_decodifica_a_png(self, client, mock_http):
        mock_http.add(
            mock_http.GET, f"{SANDBOX}/v1/facturas/F1/qr", body=base64.b64encode(b"otra cosa")
        )
        assert client.facturas.qr("F1", nif_emisor="B1") == base64.b64encode(b"otra cosa")

    def test_guardar_qr(self, client, mock_http, tmp_path):
        mock_http.add(mock_http.GET, f"{SANDBOX}/v1/facturas/F1/qr", body=PNG)
        destino = tmp_path / "qr.png"
        ruta = client.facturas.guardar_qr("F1", nif_emisor="B1", ruta=destino)
        assert destino.read_bytes() == PNG
        assert ruta == str(destino)


class TestXml:
    def test_devuelve_texto(self, client, mock_http):
        mock_http.add(
            mock_http.GET,
            f"{SANDBOX}/v1/facturas/F1/xml",
            body="<TicketBai>ñ</TicketBai>".encode(),
            content_type="application/xml",
        )
        assert client.facturas.xml("F1", nif_emisor="B1") == "<TicketBai>ñ</TicketBai>"

    def test_en_vuelo_es_su_propia_excepcion(self, client, mock_http):
        # 404 SUBMISSION_IN_PROGRESS does not mean the invoice is missing: the
        # evidence copy simply does not exist yet.
        mock_http.add(
            mock_http.GET,
            f"{SANDBOX}/v1/facturas/F1/xml",
            json=error("SUBMISSION_IN_PROGRESS", "en curso"),
            status=404,
        )
        with pytest.raises(SubmissionInProgressError):
            client.facturas.xml("F1", nif_emisor="B1")

    def test_no_encontrada_es_distinto(self, client, mock_http):
        mock_http.add(
            mock_http.GET, f"{SANDBOX}/v1/facturas/F1/xml", json=error("NOT_FOUND"), status=404
        )
        with pytest.raises(veribai.NotFoundError) as exc:
            client.facturas.xml("F1", nif_emisor="B1")
        assert not isinstance(exc.value, SubmissionInProgressError)


class TestVerdicto:
    def _estado(self, mock_http, **campos):
        mock_http.add(mock_http.GET, f"{SANDBOX}/v1/facturas/F1/estado", json=campos)

    def test_registrada(self, client, mock_http):
        self._estado(mock_http, idFactura="F1", estadoFactura="registrada", csvAeat="CSV")
        v = client.facturas.verdicto("F1", nif_emisor="B1")
        assert v.terminal and v.registrada and not v.rechazada
        assert v.csv_aeat == "CSV"

    def test_rechazada(self, client, mock_http):
        self._estado(mock_http, idFactura="F1", estadoFactura=None, estadoEnvio="rechazada")
        v = client.facturas.verdicto("F1", nif_emisor="B1")
        assert v.terminal and v.rechazada and not v.registrada

    def test_aceptada_con_errores_es_terminal(self, client, mock_http):
        # It IS filed, and it will never change on its own: only a subsanación
        # supersedes it. Polling for it to resolve waits for ever.
        self._estado(mock_http, idFactura="F1", estadoEnvio="aceptada_con_errores")
        v = client.facturas.verdicto("F1", nif_emisor="B1")
        assert v.terminal and v.requiere_subsanacion and not v.rechazada

    @pytest.mark.parametrize(
        "estado", ["pendiente_proceso", "pendiente_envio", "en_lote", "en_cola", "desconocido"]
    )
    def test_estados_en_vuelo(self, client, mock_http, estado):
        self._estado(mock_http, idFactura="F1", estadoEnvio=estado)
        assert client.facturas.verdicto("F1", nif_emisor="B1").terminal is False

    def test_anulada(self, client, mock_http):
        self._estado(mock_http, idFactura="F1", estadoFactura="anulada")
        v = client.facturas.verdicto("F1", nif_emisor="B1")
        assert v.anulada and v.terminal

    def test_esperar_hasta_el_veredicto(self, client, mock_http, monkeypatch):
        monkeypatch.setattr("veribai.resources.facturas.time.sleep", lambda s: None)
        self._estado(mock_http, idFactura="F1", estadoEnvio="en_lote")
        self._estado(mock_http, idFactura="F1", estadoEnvio="en_lote")
        self._estado(mock_http, idFactura="F1", estadoFactura="registrada")
        v = client.facturas.esperar_verdicto("F1", nif_emisor="B1", intervalo=0.01)
        assert v.registrada
        assert len(mock_http.calls) == 3

    def test_esperar_con_detalle_pide_la_factura_una_sola_vez(self, client, mock_http, monkeypatch):
        monkeypatch.setattr("veribai.resources.facturas.time.sleep", lambda s: None)
        self._estado(mock_http, idFactura="F1", estadoEnvio="en_cola")
        self._estado(mock_http, idFactura="F1", estadoEnvio="rechazada")
        mock_http.add(
            mock_http.GET,
            f"{SANDBOX}/v1/facturas/F1",
            json={"registros": [{"codigoRespuestaAeat": "1178"}]},
        )
        v = client.facturas.esperar_verdicto(
            "F1", nif_emisor="B1", intervalo=0.01, con_detalle=True
        )
        assert v.rechazada
        assert v.detalle["registros"][0]["codigoRespuestaAeat"] == "1178"
        assert len(mock_http.calls) == 3

    def test_timeout_conserva_el_ultimo_estado(self, client, mock_http, monkeypatch):
        # Giving up is not a failure of the invoice. It is accepted and in flight,
        # so the caller must be able to resume.
        monkeypatch.setattr("veribai.resources.facturas.time.sleep", lambda s: None)
        for _ in range(10):
            self._estado(mock_http, idFactura="F1", estadoEnvio="en_lote")
        with pytest.raises(VerdictTimeout) as exc:
            client.facturas.esperar_verdicto("F1", nif_emisor="B1", timeout=0.0, intervalo=0.01)
        assert exc.value.ultimo_estado["estadoEnvio"] == "en_lote"
        assert "still in flight" in str(exc.value)

    def test_intervalo_invalido(self, client):
        with pytest.raises(ValueError, match="intervalo"):
            client.facturas.esperar_verdicto("F1", nif_emisor="B1", intervalo=0)


class TestRegistros:
    def test_listar(self, client, mock_http):
        mock_http.add(
            mock_http.GET, f"{SANDBOX}/v1/registros", json={"registros": [{"idRegistro": "r1"}]}
        )
        assert client.registros.listar("B1").items == [{"idRegistro": "r1"}]

    def test_obtener_exige_la_factura_padre(self, client, mock_http):
        mock_http.add(mock_http.GET, f"{SANDBOX}/v1/registros/UkVD", json={"registro": {}})
        client.registros.obtener("UkVD", nif_emisor="B1", id_factura="F1")
        assert mock_http.calls[0].request.params == {"nifEmisor": "B1", "idFactura": "F1"}

    def test_el_token_opaco_se_codifica(self, client, mock_http):
        mock_http.add(mock_http.GET, f"{SANDBOX}/v1/registros/a%2Bb", json={})
        client.registros.obtener("a+b", nif_emisor="B1", id_factura="F1")
        assert "a%2Bb" in mock_http.calls[0].request.url

    def test_iterar(self, client, mock_http):
        mock_http.add(
            mock_http.GET,
            f"{SANDBOX}/v1/registros",
            json={"registros": [{"idRegistro": "r1"}], "proximaPagina": "c"},
        )
        mock_http.add(
            mock_http.GET, f"{SANDBOX}/v1/registros", json={"registros": [{"idRegistro": "r2"}]}
        )
        assert [r["idRegistro"] for r in client.registros.iterar("B1")] == ["r1", "r2"]


class TestCuenta:
    def test_obtener(self, client, mock_http):
        mock_http.add(
            mock_http.GET, f"{SANDBOX}/v1/cuenta", json={"entorno": "test", "plan": "sandbox"}
        )
        assert client.cuenta.obtener()["plan"] == "sandbox"

    def test_consumo_presente(self, client, mock_http):
        mock_http.add(
            mock_http.GET,
            f"{SANDBOX}/v1/cuenta",
            json={"entorno": "test", "consumo": {"usadas": 312, "restantes": 688}},
        )
        assert client.cuenta.consumo() == {"usadas": 312, "restantes": 688}

    def test_consumo_ausente_es_none_no_cero(self, client, mock_http):
        # `restantes: 0` means "at your cap". Absent means "not known yet".
        # Collapsing the two would stop a brand-new key from invoicing.
        mock_http.add(mock_http.GET, f"{SANDBOX}/v1/cuenta", json={"entorno": "test"})
        assert client.cuenta.consumo() is None


def test_cuerpo_json_se_serializa_una_sola_vez(client, mock_http):
    mock_http.add(mock_http.POST, f"{SANDBOX}/v1/verifactu/crear", json={"idFactura": "F1"})
    client.verifactu.crear({"version": "1.0"})
    assert json.loads(mock_http.calls[0].request.body) == {"version": "1.0"}


class TestPaginacionDefensiva:
    def test_una_clave_que_no_es_lista_no_rompe(self, client, mock_http):
        mock_http.add(mock_http.GET, f"{SANDBOX}/v1/facturas", json={"facturas": "vaya"})
        assert client.facturas.listar("B1").items == []

    def test_entradas_que_no_son_objetos_se_descartan(self, client, mock_http):
        mock_http.add(
            mock_http.GET, f"{SANDBOX}/v1/facturas", json={"facturas": [{"idFactura": "A"}, "x"]}
        )
        assert client.facturas.listar("B1").items == [{"idFactura": "A"}]
