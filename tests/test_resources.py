"""Every endpoint group: the right verb, the right path, the right body."""

from __future__ import annotations

import base64
import datetime as dt
import json
from decimal import Decimal

import pytest

import veribai

from .conftest import MANAGE, SANDBOX, error


def cuerpo(mock_http, indice=0):
    return json.loads(mock_http.calls[indice].request.body)


class TestVerifactu:
    def test_crear(self, client, mock_http):
        mock_http.add(mock_http.POST, f"{SANDBOX}/v1/verifactu/crear", json={"idFactura": "F1"})
        respuesta = client.verifactu.crear(
            {
                "version": "1.0",
                "cabecera": {"fechaExpedicion": dt.date(2026, 9, 15)},
                "totales": {"importeTotal": Decimal("121")},
            }
        )
        assert respuesta == {"idFactura": "F1"}
        enviado = cuerpo(mock_http)
        assert enviado["cabecera"]["fechaExpedicion"] == "15-09-2026"
        assert enviado["totales"]["importeTotal"] == "121.00"

    def test_subsanar_usa_put(self, client, mock_http):
        mock_http.add(mock_http.PUT, f"{SANDBOX}/v1/verifactu/subsanar", json={})
        client.verifactu.subsanar({"version": "1.0"})
        assert mock_http.calls[0].request.method == "PUT"

    def test_anular(self, client, mock_http):
        mock_http.add(mock_http.POST, f"{SANDBOX}/v1/verifactu/anular", json={"code": "SUCCESS"})
        client.verifactu.anular(
            {"version": "1.0", "facturaAnulada": {"fechaExpedicion": dt.date(2026, 1, 5)}}
        )
        assert cuerpo(mock_http)["facturaAnulada"]["fechaExpedicion"] == "05-01-2026"

    def test_el_booleano_de_subsanacion_llega_como_booleano(self, client, mock_http):
        # Both `true` and `"S"` are valid; converting either silently would be
        # the library inventing a contract it was not given.
        mock_http.add(mock_http.POST, f"{SANDBOX}/v1/verifactu/crear", json={})
        client.verifactu.crear({"subsanacion": True, "rechazoPrevio": "X"})
        assert cuerpo(mock_http) == {"subsanacion": True, "rechazoPrevio": "X"}

    def test_conflicto_de_identidad(self, client, mock_http):
        mock_http.add(
            mock_http.POST,
            f"{SANDBOX}/v1/verifactu/crear",
            json=error("INVOICE_IDENTITY_CONFLICT", "distinta", errors=["importeTotal"]),
            status=409,
        )
        with pytest.raises(veribai.IdentityConflictError) as exc:
            client.verifactu.crear({})
        assert exc.value.errors == ["importeTotal"]


class TestTicketbai:
    def test_crear(self, client, mock_http):
        mock_http.add(
            mock_http.POST,
            f"{SANDBOX}/v1/ticketbai/crear",
            json={"idTbai": "TBAI-...", "estado": "en_cola"},
        )
        respuesta = client.ticketbai.crear(
            {"provincia": "araba", "horaExpedicion": dt.time(10, 0, 0)}
        )
        assert respuesta["idTbai"] == "TBAI-..."
        assert cuerpo(mock_http)["horaExpedicion"] == "10:00:00"

    def test_subsanar(self, client, mock_http):
        mock_http.add(mock_http.PUT, f"{SANDBOX}/v1/ticketbai/subsanar", json={})
        client.ticketbai.subsanar({"subsanacion": True})
        assert mock_http.calls[0].request.method == "PUT"

    def test_anular_es_plano(self, client, mock_http):
        # TicketBAI cancel has no nested facturaAnulada, unlike VeriFactu.
        mock_http.add(mock_http.POST, f"{SANDBOX}/v1/ticketbai/anular", json={"yaAnulada": True})
        client.ticketbai.anular({"nifEmisor": "B1", "numero": "1", "provincia": "bizkaia"})
        assert "facturaAnulada" not in cuerpo(mock_http)

    def test_provincias_publicadas(self):
        from veribai.resources.ticketbai import PROVINCIAS

        assert PROVINCIAS == ("araba", "bizkaia", "gipuzkoa")


class TestNif:
    def test_entradas_completas(self, client, mock_http):
        mock_http.add(mock_http.POST, f"{MANAGE}/v1/nif/validar", json={"resultados": []})
        client.nif.validar(
            [
                {"nif": "B26682641", "nombre": "SKY CLOUD INFRASTRUCTURE SL"},
                {"nif": "12345678Z", "nombre": "NOMBRE APELLIDO"},
            ]
        )
        assert cuerpo(mock_http) == {
            "nifs": [
                {"nif": "B26682641", "nombre": "SKY CLOUD INFRASTRUCTURE SL"},
                {"nif": "12345678Z", "nombre": "NOMBRE APELLIDO"},
            ]
        }

    def test_una_cadena_suelta_se_rechaza_en_local(self, client):
        # `nombre` is required on every entry, so a bare string is a guaranteed 400.
        # Refusing here saves a call against a quota that is per API key, and the
        # message carries the reason the API's own 400 does not: the census cache is
        # keyed on (nif, nombre).
        with pytest.raises(ValueError, match="bare NIF string is not enough"):
            client.nif.validar(["B26682641"])

    def test_nombre_vacio_se_rechaza(self, client):
        with pytest.raises(ValueError, match="nifs\\[0\\]: 'nombre' is required"):
            client.nif.validar([{"nif": "B1", "nombre": "  "}])

    def test_nif_ausente_se_rechaza(self, client):
        with pytest.raises(ValueError, match="nifs\\[0\\]: 'nif' is required"):
            client.nif.validar([{"nombre": "SOLO EL NOMBRE"}])

    def test_el_indice_del_error_es_el_de_la_entrada(self, client):
        with pytest.raises(ValueError, match="nifs\\[1\\]"):
            client.nif.validar([{"nif": "B1", "nombre": "UNO"}, {"nif": "B2", "nombre": ""}])

    def test_no_se_envia_forzar(self, client, mock_http):
        # `forzar` is a 400 on the API-key surface since 2026-09-16; it survives only
        # on the JWT dashboard route. The parameter is gone rather than ignored.
        mock_http.add(mock_http.POST, f"{MANAGE}/v1/nif/validar", json={})
        client.nif.validar([{"nif": "B1", "nombre": "X"}])
        assert "forzar" not in cuerpo(mock_http)
        with pytest.raises(TypeError):
            client.nif.validar([{"nif": "B1", "nombre": "X"}], forzar=True)

    def test_lista_vacia(self, client):
        with pytest.raises(ValueError, match="at least one"):
            client.nif.validar([])

    def test_entrada_de_tipo_imposible(self, client):
        with pytest.raises(TypeError, match="mapping with 'nif' and 'nombre'"):
            client.nif.validar([123])

    def test_censo_caido(self, client, mock_http):
        mock_http.add(
            mock_http.POST,
            f"{MANAGE}/v1/nif/validar",
            json=error("AEAT_UNAVAILABLE", "caído", resultados=[{"nif": "B1"}]),
            status=503,
        )
        with pytest.raises(veribai.AeatUnavailableError) as exc:
            client.nif.validar([{"nif": "B1", "nombre": "X"}])
        # The cached subset still came back; losing it would waste a real answer.
        assert exc.value.payload["resultados"] == [{"nif": "B1"}]

    def test_un_nif_sin_respuesta_del_censo_es_un_200_normal(self, client, mock_http):
        # Since 2026-09-16 a NIF the census answers nothing about is a per-entry
        # `no_procesado`, not a 503 for the whole batch. The old behaviour told the
        # caller to retry a condition no retry can change.
        mock_http.add(
            mock_http.POST,
            f"{MANAGE}/v1/nif/validar",
            json={"resultados": [{"nif": "B1", "estado": "no_procesado"}]},
        )
        respuesta = client.nif.validar([{"nif": "B1", "nombre": "X"}])
        assert respuesta["resultados"][0]["estado"] == "no_procesado"


class TestClientes:
    def test_listar(self, client, mock_http):
        mock_http.add(mock_http.GET, f"{MANAGE}/v1/clientes", json={"clientes": [], "total": 0})
        client.clientes.listar()
        assert mock_http.calls[0].request.params == {}

    def test_incluir_eliminados(self, client, mock_http):
        mock_http.add(mock_http.GET, f"{MANAGE}/v1/clientes", json={})
        client.clientes.listar(incluir_eliminados=True)
        assert mock_http.calls[0].request.params == {"incluirEliminados": "true"}

    def test_asientos(self, client, mock_http):
        mock_http.add(
            mock_http.GET,
            f"{MANAGE}/v1/clientes",
            json={"limitePlan": 10, "clientesUsados": 7, "clientesDisponibles": 3},
        )
        assert client.clientes.asientos() == {"limite": 10, "usados": 7, "disponibles": 3}

    def test_asientos_ausentes_son_none_no_cero(self, client, mock_http):
        # `0` means "at your cap" and would hide a create button from an account
        # that has no cap at all. Absent must stay absent.
        mock_http.add(mock_http.GET, f"{MANAGE}/v1/clientes", json={"clientes": []})
        assert client.clientes.asientos() == {"limite": None, "usados": None, "disponibles": None}

    def test_crear(self, client, mock_http):
        mock_http.add(
            mock_http.POST, f"{MANAGE}/v1/clientes/crear", json={"cliente": {}}, status=201
        )
        client.clientes.crear({"nif": "B1", "nombre": "X", "hacienda": "verifactu"})
        assert cuerpo(mock_http)["hacienda"] == "verifactu"

    def test_crear_limite_de_plan(self, client, mock_http):
        mock_http.add(
            mock_http.POST,
            f"{MANAGE}/v1/clientes/crear",
            json=error("CLIENT_LIMIT_REACHED"),
            status=409,
        )
        with pytest.raises(veribai.ClientLimitReachedError):
            client.clientes.crear({"nif": "B1"})

    def test_obtener_y_modificar(self, client, mock_http):
        mock_http.add(mock_http.GET, f"{MANAGE}/v1/clientes/B1", json={"cliente": {}})
        client.clientes.obtener("B1")
        mock_http.add(mock_http.PATCH, f"{MANAGE}/v1/clientes/B1", json={"cliente": {}})
        client.clientes.modificar("B1", {"nombre": "Nuevo"})
        assert cuerpo(mock_http, 1) == {"nombre": "Nuevo"}

    def test_activar_y_desactivar(self, client, mock_http):
        mock_http.add(mock_http.PATCH, f"{MANAGE}/v1/clientes/B1/estado", json={"estado": "activo"})
        client.clientes.activar("B1")
        assert cuerpo(mock_http) == {"estado": "activo"}
        mock_http.add(
            mock_http.PATCH, f"{MANAGE}/v1/clientes/B1/estado", json={"estado": "inactivo"}
        )
        client.clientes.desactivar("B1")
        assert cuerpo(mock_http, 1) == {"estado": "inactivo"}

    def test_estado_invalido_se_para_antes_de_salir(self, client):
        with pytest.raises(ValueError, match="activo"):
            client.clientes.cambiar_estado("B1", "eliminado")

    def test_borrado_logico_no_se_deshace_con_el_toggle(self, client, mock_http):
        # Only the restore path checks the 30-day window and clears the markers.
        mock_http.add(
            mock_http.PATCH,
            f"{MANAGE}/v1/clientes/B1/estado",
            json=error("CLIENT_DELETED"),
            status=409,
        )
        with pytest.raises(veribai.ConflictError) as exc:
            client.clientes.activar("B1")
        assert exc.value.code == "CLIENT_DELETED"


class TestDispositivos:
    def test_listar(self, client, mock_http):
        mock_http.add(
            mock_http.GET,
            f"{MANAGE}/v1/clientes/B1/dispositivos",
            json={"faseAltaCapacidad": "preparacion", "dispositivos": [], "series": []},
        )
        assert client.dispositivos.listar("B1")["faseAltaCapacidad"] == "preparacion"

    def test_registrar(self, client, mock_http):
        mock_http.add(mock_http.POST, f"{MANAGE}/v1/clientes/B1/dispositivos", json={}, status=201)
        client.dispositivos.registrar("B1", "TPV-01", etiqueta="Barra")
        assert cuerpo(mock_http) == {"idMaquina": "TPV-01", "etiqueta": "Barra"}

    def test_registrar_sin_etiqueta(self, client, mock_http):
        mock_http.add(mock_http.POST, f"{MANAGE}/v1/clientes/B1/dispositivos", json={})
        client.dispositivos.registrar("B1", "TPV-01")
        assert cuerpo(mock_http) == {"idMaquina": "TPV-01"}

    def test_id_ya_activo(self, client, mock_http):
        # ids are chain keys and are never recycled between machines.
        mock_http.add(
            mock_http.POST,
            f"{MANAGE}/v1/clientes/B1/dispositivos",
            json=error("MACHINE_ALREADY_REGISTERED"),
            status=409,
        )
        with pytest.raises(veribai.ConflictError):
            client.dispositivos.registrar("B1", "TPV-01")

    def test_dar_de_baja(self, client, mock_http):
        mock_http.add(mock_http.DELETE, f"{MANAGE}/v1/clientes/B1/dispositivos/TPV-01", json={})
        client.dispositivos.dar_de_baja("B1", "TPV-01")
        assert mock_http.calls[0].request.method == "DELETE"

    def test_promover_todo(self, client, mock_http):
        mock_http.add(
            mock_http.POST, f"{MANAGE}/v1/clientes/B1/dispositivos/promover", json={"creados": []}
        )
        client.dispositivos.promover("B1")
        assert mock_http.calls[0].request.body is None

    def test_promover_un_subconjunto(self, client, mock_http):
        mock_http.add(mock_http.POST, f"{MANAGE}/v1/clientes/B1/dispositivos/promover", json={})
        client.dispositivos.promover("B1", ["TPV-01"])
        assert cuerpo(mock_http) == {"idsMaquina": ["TPV-01"]}

    def test_promover_lista_vacia_no_es_lo_mismo_que_omitirla(self, client):
        with pytest.raises(ValueError, match="omit it"):
            client.dispositivos.promover("B1", [])

    def test_solicitar_activacion(self, client, mock_http):
        mock_http.add(
            mock_http.POST,
            f"{MANAGE}/v1/clientes/B1/dispositivos/solicitar-activacion",
            json={"solicitadoEn": "2026-09-15T10:00:00Z"},
        )
        assert "solicitadoEn" in client.dispositivos.solicitar_activacion("B1")

    def test_reservar_series(self, client, mock_http):
        mock_http.add(
            mock_http.POST,
            f"{MANAGE}/v1/clientes/B1/dispositivos/series-centralizadas",
            json={"reservadas": ["A"], "omitidas": []},
        )
        client.dispositivos.reservar_series_centralizadas("B1", ["A", "B"])
        assert cuerpo(mock_http) == {"series": ["A", "B"]}

    def test_reservar_sin_series(self, client):
        with pytest.raises(ValueError, match="at least one serie"):
            client.dispositivos.reservar_series_centralizadas("B1", [])

    def test_liberar_serie_con_barra_se_codifica(self, client, mock_http):
        # "A/2026" is a perfectly normal serie and must not become a path segment.
        mock_http.add(
            mock_http.DELETE,
            f"{MANAGE}/v1/clientes/B1/dispositivos/series-centralizadas/A%2F2026",
            json={},
        )
        client.dispositivos.liberar_serie_centralizada("B1", "A/2026")
        assert "A%2F2026" in mock_http.calls[0].request.url

    def test_reserva_bloqueada_tras_la_activacion(self, client, mock_http):
        mock_http.add(
            mock_http.DELETE,
            f"{MANAGE}/v1/clientes/B1/dispositivos/series-centralizadas/A",
            json=error("RESERVATION_LOCKED"),
            status=409,
        )
        with pytest.raises(veribai.ConflictError) as exc:
            client.dispositivos.liberar_serie_centralizada("B1", "A")
        assert exc.value.code == "RESERVATION_LOCKED"

    def test_constante_del_emisor_central(self):
        from veribai.resources.dispositivos import CENTRAL

        assert CENTRAL == "__SHARD0__"


class TestRepresentacion:
    def test_generar(self, client, mock_http):
        mock_http.add(
            mock_http.GET, f"{MANAGE}/v1/clientes/B1/representacion/generar", json={"url": "u"}
        )
        assert client.representacion.generar("B1")["url"] == "u"

    def test_firmar_codifica_los_binarios(self, client, mock_http):
        mock_http.add(mock_http.POST, f"{MANAGE}/v1/clientes/B1/representacion/firmar", json={})
        client.representacion.firmar("B1", pdf=b"%PDF", certificado=b"p12", password="s3cr3t")
        enviado = cuerpo(mock_http)
        assert enviado["pdf"] == base64.b64encode(b"%PDF").decode()
        assert enviado["certificado"] == base64.b64encode(b"p12").decode()
        assert enviado["password"] == "s3cr3t"

    def test_firmar_acepta_base64_ya_hecho(self, client, mock_http):
        mock_http.add(mock_http.POST, f"{MANAGE}/v1/clientes/B1/representacion/firmar", json={})
        client.representacion.firmar("B1", pdf="JVBERg==", certificado="cDEy", password="x")
        assert cuerpo(mock_http)["pdf"] == "JVBERg=="

    def test_verificar(self, client, mock_http):
        mock_http.add(mock_http.POST, f"{MANAGE}/v1/clientes/B1/representacion/verificar", json={})
        client.representacion.verificar("B1", pdf_firmado=b"%PDF-signed")
        assert cuerpo(mock_http)["pdfFirmado"] == base64.b64encode(b"%PDF-signed").decode()

    def test_estado_y_cancelacion(self, client, mock_http):
        mock_http.add(
            mock_http.GET,
            f"{MANAGE}/v1/clientes/B1/representacion/estado",
            json={"estadoRepresentacion": "pendiente", "firmaEnCurso": True},
        )
        assert client.representacion.estado("B1")["firmaEnCurso"] is True
        mock_http.add(
            mock_http.DELETE, f"{MANAGE}/v1/clientes/B1/representacion/firma-en-curso", json={}
        )
        client.representacion.cancelar_firma("B1")
        assert mock_http.calls[1].request.method == "DELETE"

    def test_gate_live(self, client, mock_http):
        # On LIVE an unsigned mandate blocks invoicing for that emisor.
        mock_http.add(
            mock_http.POST,
            f"{SANDBOX}/v1/verifactu/crear",
            json=error("REPRESENTATION_PENDING"),
            status=403,
        )
        with pytest.raises(veribai.ForbiddenError) as exc:
            client.verifactu.crear({})
        assert exc.value.code == "REPRESENTATION_PENDING"


class TestWebhooks:
    def test_crear(self, client, mock_http):
        mock_http.add(
            mock_http.POST,
            f"{MANAGE}/v1/webhooks",
            json={"webhook": {}, "entorno": "test"},
            status=201,
        )
        client.webhooks.crear(
            nombre="Prod", url="https://ejemplo.com/hook", secreto="0123456789abcdef"
        )
        assert cuerpo(mock_http) == {
            "nombre": "Prod",
            "url": "https://ejemplo.com/hook",
            "secreto": "0123456789abcdef",
        }

    def test_crear_con_eventos(self, client, mock_http):
        mock_http.add(mock_http.POST, f"{MANAGE}/v1/webhooks", json={}, status=201)
        client.webhooks.crear(
            nombre="P",
            url="https://e.com/h",
            secreto="0123456789abcdef",
            eventos=["factura.registrada", "factura.rechazada"],
        )
        assert cuerpo(mock_http)["eventos"] == ["factura.registrada", "factura.rechazada"]

    def test_url_privada_rechazada_por_la_api(self, client, mock_http):
        # 169.254.169.254 is how a webhook becomes an SSRF primitive.
        mock_http.add(
            mock_http.POST,
            f"{MANAGE}/v1/webhooks",
            json=error("VALIDATION_ERROR", "host no público"),
            status=400,
        )
        with pytest.raises(veribai.ValidationError):
            client.webhooks.crear(
                nombre="x", url="https://169.254.169.254/", secreto="0123456789abcdef"
            )

    def test_modificar_puede_limpiar_los_eventos(self, client, mock_http):
        # `eventos: null` clears the subscription; dropping the None would turn a
        # deliberate reset into a no-op.
        mock_http.add(mock_http.PATCH, f"{MANAGE}/v1/webhooks/w1", json={})
        client.webhooks.modificar("w1", {"eventos": None})
        assert cuerpo(mock_http) == {"eventos": None}

    def test_reactivar_tras_la_suspension(self, client, mock_http):
        mock_http.add(mock_http.PATCH, f"{MANAGE}/v1/webhooks/w1", json={})
        client.webhooks.modificar("w1", {"estado": "activo"})
        assert cuerpo(mock_http) == {"estado": "activo"}

    def test_propagacion_incompleta_es_reintentable_por_el_usuario(self, client, mock_http):
        mock_http.add(
            mock_http.PATCH,
            f"{MANAGE}/v1/webhooks/w1",
            json=error("PROPAGATION_INCOMPLETE"),
            status=500,
        )
        with pytest.raises(veribai.ServerError) as exc:
            client.webhooks.modificar("w1", {"nombre": "x"})
        assert exc.value.code == "PROPAGATION_INCOMPLETE"

    def test_listar_obtener_eliminar(self, client, mock_http):
        mock_http.add(mock_http.GET, f"{MANAGE}/v1/webhooks", json={"webhooks": []})
        client.webhooks.listar()
        mock_http.add(mock_http.GET, f"{MANAGE}/v1/webhooks/w1", json={"webhook": {}})
        client.webhooks.obtener("w1")
        mock_http.add(mock_http.DELETE, f"{MANAGE}/v1/webhooks/w1", json={})
        client.webhooks.eliminar("w1")
        assert [c.request.method for c in mock_http.calls] == ["GET", "GET", "DELETE"]

    def test_vincular_y_desvincular_clientes(self, client, mock_http):
        mock_http.add(mock_http.GET, f"{MANAGE}/v1/webhooks/w1/clientes", json={})
        client.webhooks.listar_clientes("w1")
        mock_http.add(mock_http.POST, f"{MANAGE}/v1/webhooks/w1/clientes", json={})
        client.webhooks.vincular_clientes("w1", ["B1", "B2"])
        assert cuerpo(mock_http, 1) == {"clientes": ["B1", "B2"]}
        mock_http.add(mock_http.DELETE, f"{MANAGE}/v1/webhooks/w1/clientes/B1", json={})
        client.webhooks.desvincular_cliente("w1", "B1")
        assert mock_http.calls[2].request.method == "DELETE"

    def test_vincular_sin_clientes(self, client):
        with pytest.raises(ValueError, match="at least one NIF"):
            client.webhooks.vincular_clientes("w1", [])

    def test_eventos_publicados(self):
        from veribai.resources.webhooks import EVENTOS

        assert EVENTOS == ("factura.registrada", "factura.rechazada", "factura.anulada")


class TestCumplimiento:
    def test_declaracion_responsable(self, client, mock_http):
        mock_http.add(
            mock_http.GET,
            f"{MANAGE}/v1/cumplimiento/declaracion-responsable",
            json={"url": "https://docshare.veribai.com/compliance/declaracion-responsable.pdf"},
        )
        assert client.cumplimiento.declaracion_responsable()["url"].endswith(".pdf")

    def test_todavia_no_publicada(self, client, mock_http):
        mock_http.add(
            mock_http.GET,
            f"{MANAGE}/v1/cumplimiento/declaracion-responsable",
            json=error("NOT_UPLOADED_YET"),
            status=404,
        )
        with pytest.raises(veribai.NotFoundError):
            client.cumplimiento.declaracion_responsable()


class TestFacturacionSuspendida:
    def test_402_en_rutas_mutantes(self, client, mock_http):
        mock_http.add(
            mock_http.POST,
            f"{SANDBOX}/v1/verifactu/crear",
            json=error("PAYMENT_REQUIRED", "facturación suspendida"),
            status=402,
        )
        with pytest.raises(veribai.PaymentRequiredError):
            client.verifactu.crear({})
