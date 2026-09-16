"""Retry semantics.

These are the rules that make the difference between a client that is safe to
put in front of a fiscal API and one that quietly files duplicates, so they are
tested by behaviour rather than by reading the policy back.
"""

from __future__ import annotations

from typing import ClassVar

import pytest
import requests
import responses

from veribai import errors
from veribai._transport import RetryPolicy, Transport, construir_error

from .conftest import SANDBOX, error

RUTA = f"{SANDBOX}/v1/facturas"


def transporte(sin_dormir, **kwargs):
    kwargs.setdefault("retry", RetryPolicy(max_attempts=3, backoff_base=0.01, jitter=False))
    t = Transport("k", **kwargs)
    t._sleep = sin_dormir
    return t


class TestPoliticaDeReintentos:
    def test_espera_crece_exponencialmente(self):
        p = RetryPolicy(backoff_base=1.0, backoff_max=100.0, jitter=False)
        assert [p.espera(i) for i in (1, 2, 3, 4)] == [1.0, 2.0, 4.0, 8.0]

    def test_espera_topada(self):
        p = RetryPolicy(backoff_base=1.0, backoff_max=3.0, jitter=False)
        assert p.espera(10) == 3.0

    def test_retry_after_manda(self):
        p = RetryPolicy(backoff_base=1.0, backoff_max=100.0, jitter=False)
        assert p.espera(1, retry_after=7.0) == 7.0

    def test_retry_after_tambien_topado(self):
        p = RetryPolicy(backoff_base=1.0, backoff_max=5.0, jitter=False)
        assert p.espera(1, retry_after=600.0) == 5.0

    def test_jitter_mantiene_la_espera_en_rango(self):
        p = RetryPolicy(backoff_base=4.0, backoff_max=100.0, jitter=True)
        valores = [p.espera(1) for _ in range(50)]
        assert all(2.0 <= v <= 4.0 for v in valores)
        assert len(set(valores)) > 1  # actually varies, or it is not jitter

    def test_configuracion_invalida(self):
        with pytest.raises(errors.ConfigurationError):
            RetryPolicy(max_attempts=0)
        with pytest.raises(errors.ConfigurationError):
            RetryPolicy(backoff_base=0)


class TestErrorDeRed:
    """A network error proves nothing about whether the server acted."""

    @responses.activate
    def test_no_se_reintenta_en_rutas_no_idempotentes(self, sin_dormir):
        # Retrying a webhook create after a timeout would make a second webhook.
        responses.add(responses.POST, f"{SANDBOX}/v1/webhooks", body=requests.ConnectionError())
        with pytest.raises(errors.TransportError):
            transporte(sin_dormir).request("POST", SANDBOX, "/v1/webhooks", json={})
        assert len(responses.calls) == 1

    @responses.activate
    def test_se_reintenta_donde_la_api_reproduce_por_identidad(self, sin_dormir):
        # An identical alta replays the original record, so a retry is safe.
        responses.add(
            responses.POST, f"{SANDBOX}/v1/verifactu/crear", body=requests.ConnectionError()
        )
        responses.add(
            responses.POST, f"{SANDBOX}/v1/verifactu/crear", body=requests.ConnectionError()
        )
        responses.add(responses.POST, f"{SANDBOX}/v1/verifactu/crear", json={"idFactura": "F1"})
        r = transporte(sin_dormir).request(
            "POST", SANDBOX, "/v1/verifactu/crear", json={}, idempotente=True
        )
        assert r.datos["idFactura"] == "F1"
        assert len(responses.calls) == 3

    @responses.activate
    def test_timeout_se_convierte_en_excepcion_propia(self, sin_dormir):
        responses.add(responses.GET, RUTA, body=requests.Timeout())
        with pytest.raises(errors.TimeoutError, match="timed out"):
            transporte(sin_dormir).request("GET", SANDBOX, "/v1/facturas")

    @responses.activate
    def test_se_agotan_los_intentos(self, sin_dormir):
        for _ in range(3):
            responses.add(responses.GET, RUTA, body=requests.ConnectionError())
        with pytest.raises(errors.TransportError):
            transporte(sin_dormir).request("GET", SANDBOX, "/v1/facturas", idempotente=True)
        assert len(responses.calls) == 3


class TestRespuestasDeError:
    """A status response proves the server refused — which is different evidence."""

    @responses.activate
    def test_429_siempre_se_reintenta(self, sin_dormir):
        # Throttled means nothing executed, on any route.
        responses.add(responses.POST, f"{SANDBOX}/v1/webhooks", json=error("TOO_MANY"), status=429)
        responses.add(responses.POST, f"{SANDBOX}/v1/webhooks", json={"ok": True}, status=201)
        r = transporte(sin_dormir).request("POST", SANDBOX, "/v1/webhooks", json={})
        assert r.datos == {"ok": True}

    @responses.activate
    def test_429_respeta_retry_after(self, sin_dormir):
        responses.add(
            responses.GET, RUTA, json=error("TOO_MANY"), status=429, headers={"Retry-After": "2"}
        )
        responses.add(responses.GET, RUTA, json={"facturas": []})
        transporte(sin_dormir).request("GET", SANDBOX, "/v1/facturas")
        assert sin_dormir.esperas == [2.0]

    @responses.activate
    def test_retry_after_con_fecha_http_cae_al_backoff(self, sin_dormir):
        responses.add(
            responses.GET,
            RUTA,
            json=error("TOO_MANY"),
            status=429,
            headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"},
        )
        responses.add(responses.GET, RUTA, json={})
        transporte(sin_dormir).request("GET", SANDBOX, "/v1/facturas")
        assert sin_dormir.esperas == [0.01]

    @responses.activate
    def test_sharding_unavailable_se_reintenta(self, sin_dormir):
        # Documented retry-safe: the request is never routed unverified.
        url = f"{SANDBOX}/v1/verifactu/crear"
        responses.add(responses.POST, url, json=error("SHARDING_UNAVAILABLE"), status=503)
        responses.add(responses.POST, url, json={"idFactura": "F1"})
        r = transporte(sin_dormir).request(
            "POST", SANDBOX, "/v1/verifactu/crear", json={}, idempotente=True
        )
        assert r.datos["idFactura"] == "F1"

    @responses.activate
    def test_chain_contention_se_reintenta(self, sin_dormir):
        url = f"{SANDBOX}/v1/ticketbai/crear"
        responses.add(responses.POST, url, json=error("CHAIN_CONTENTION"), status=503)
        responses.add(responses.POST, url, json={"idFactura": "F1"})
        r = transporte(sin_dormir).request(
            "POST", SANDBOX, "/v1/ticketbai/crear", json={}, idempotente=True
        )
        assert r.datos["idFactura"] == "F1"

    @responses.activate
    def test_environment_not_available_no_se_reintenta(self, sin_dormir):
        # LIVE is not deployed; waiting will not deploy it.
        responses.add(
            responses.POST,
            f"{SANDBOX}/v1/verifactu/crear",
            json=error("ENVIRONMENT_NOT_AVAILABLE"),
            status=503,
        )
        with pytest.raises(errors.EnvironmentNotAvailableError):
            transporte(sin_dormir).request(
                "POST", SANDBOX, "/v1/verifactu/crear", json={}, idempotente=True
            )
        assert len(responses.calls) == 1

    @responses.activate
    def test_signing_in_flight_se_reintenta(self, sin_dormir):
        url = f"{SANDBOX}/v1/ticketbai/crear"
        responses.add(responses.POST, url, json=error("INVOICE_SIGNING_IN_FLIGHT"), status=409)
        responses.add(responses.POST, url, json={"idFactura": "F1"})
        r = transporte(sin_dormir).request(
            "POST", SANDBOX, "/v1/ticketbai/crear", json={}, idempotente=True
        )
        assert r.datos["idFactura"] == "F1"

    @responses.activate
    def test_500_nombrado_como_seguro_se_reintenta_incluso_si_no_es_idempotente(self, sin_dormir):
        # RECORD_PERSIST_ERROR means nothing was handed to the pipeline.
        responses.add(
            responses.POST, f"{SANDBOX}/v1/webhooks", json=error("RECORD_PERSIST_ERROR"), status=500
        )
        responses.add(responses.POST, f"{SANDBOX}/v1/webhooks", json={"ok": 1}, status=201)
        r = transporte(sin_dormir).request("POST", SANDBOX, "/v1/webhooks", json={})
        assert r.datos == {"ok": 1}

    @responses.activate
    def test_500_sin_codigo_conocido_no_se_reintenta_en_ruta_no_idempotente(self, sin_dormir):
        responses.add(responses.POST, f"{SANDBOX}/v1/webhooks", json=error("MYSTERY"), status=500)
        with pytest.raises(errors.ServerError):
            transporte(sin_dormir).request("POST", SANDBOX, "/v1/webhooks", json={})
        assert len(responses.calls) == 1

    @responses.activate
    def test_502_se_reintenta_solo_si_es_idempotente(self, sin_dormir):
        # A gateway error can mean the Lambda ran to completion.
        responses.add(responses.POST, f"{SANDBOX}/v1/webhooks", json={}, status=502)
        with pytest.raises(errors.ServerError):
            transporte(sin_dormir).request("POST", SANDBOX, "/v1/webhooks", json={})
        assert len(responses.calls) == 1

    @responses.activate
    def test_400_nunca_se_reintenta(self, sin_dormir):
        responses.add(responses.GET, RUTA, json=error("VALIDATION_ERROR"), status=400)
        with pytest.raises(errors.ValidationError):
            transporte(sin_dormir).request("GET", SANDBOX, "/v1/facturas")
        assert len(responses.calls) == 1

    @responses.activate
    def test_reintentos_desactivados(self, sin_dormir):
        responses.add(responses.GET, RUTA, json=error("TOO_MANY"), status=429)
        t = Transport("k", retry=RetryPolicy(max_attempts=1))
        t._sleep = sin_dormir
        with pytest.raises(errors.RateLimitError):
            t.request("GET", SANDBOX, "/v1/facturas")
        assert len(responses.calls) == 1


class TestMapeoDeErrores:
    @responses.activate
    def test_rechazo_del_gateway_es_problema_de_clave_no_de_permisos(self, sin_dormir):
        # API Gateway answers 403 {"message": "Forbidden"} — no `code` — when the
        # key is missing, unknown or disabled. Reading that as a permission
        # problem sends people hunting for the wrong bug.
        responses.add(responses.GET, RUTA, json={"message": "Forbidden"}, status=403)
        with pytest.raises(errors.AuthenticationError, match="missing, unknown or disabled"):
            transporte(sin_dormir).request("GET", SANDBOX, "/v1/facturas")

    @responses.activate
    def test_ruta_desconocida(self, sin_dormir):
        responses.add(
            responses.GET, RUTA, json={"message": "Missing Authentication Token"}, status=403
        )
        with pytest.raises(errors.UnknownRouteError, match="does not exist"):
            transporte(sin_dormir).request("GET", SANDBOX, "/v1/facturas")

    @responses.activate
    def test_403_de_aplicacion_sigue_siendo_forbidden(self, sin_dormir):
        responses.add(responses.GET, RUTA, json=error("FORBIDDEN", "no es tuyo"), status=403)
        with pytest.raises(errors.ForbiddenError):
            transporte(sin_dormir).request("GET", SANDBOX, "/v1/facturas")

    @responses.activate
    def test_errors_se_expone_como_lista_de_cadenas(self, sin_dormir):
        cuerpo = error("VALIDATION_ERROR", errors=["cabecera.numero: Field required"])
        responses.add(responses.GET, RUTA, json=cuerpo, status=400)
        with pytest.raises(errors.ValidationError) as exc:
            transporte(sin_dormir).request("GET", SANDBOX, "/v1/facturas")
        assert exc.value.errors == ["cabecera.numero: Field required"]
        assert exc.value.code == "VALIDATION_ERROR"

    @responses.activate
    def test_request_id_se_conserva(self, sin_dormir):
        responses.add(
            responses.GET,
            RUTA,
            json=error("INTERNAL_ERROR"),
            status=500,
            headers={"x-amzn-RequestId": "abc-123"},
        )
        with pytest.raises(errors.ServerError) as exc:
            transporte(sin_dormir).request("GET", SANDBOX, "/v1/facturas")
        assert exc.value.request_id == "abc-123"

    @responses.activate
    def test_cuerpo_no_json_no_rompe_el_mapeo(self, sin_dormir):
        responses.add(responses.GET, RUTA, body="<html>502</html>", status=500)
        with pytest.raises(errors.ServerError) as exc:
            transporte(sin_dormir).request("GET", SANDBOX, "/v1/facturas")
        assert exc.value.payload["_raw"].startswith("<html>")

    @pytest.mark.parametrize(
        ("status", "code", "clase"),
        [
            (400, "VALIDATION_ERROR", errors.ValidationError),
            (402, "PAYMENT_REQUIRED", errors.PaymentRequiredError),
            (404, "NOT_FOUND", errors.NotFoundError),
            (404, "SUBMISSION_IN_PROGRESS", errors.SubmissionInProgressError),
            (409, "INVOICE_IDENTITY_CONFLICT", errors.IdentityConflictError),
            (409, "ALREADY_CANCELLED", errors.AlreadyCancelledError),
            (409, "MACHINE_NOT_REGISTERED", errors.ShardingConflictError),
            (409, "SERIE_OWNED_BY_OTHER_MACHINE", errors.ShardingConflictError),
            (409, "CLIENT_LIMIT_REACHED", errors.ClientLimitReachedError),
            (409, "OTRO", errors.ConflictError),
            (429, "TOO_MANY", errors.RateLimitError),
            (500, "INTERNAL_ERROR", errors.ServerError),
            (503, "AEAT_UNAVAILABLE", errors.AeatUnavailableError),
            (503, "CUALQUIERA", errors.ServiceUnavailableError),
            (418, "RARO", errors.APIError),
        ],
    )
    def test_clase_por_status_y_codigo(self, status, code, clase):
        assert errors.error_class(status, code) is clase

    def test_el_mensaje_lleva_status_y_codigo(self):
        exc = errors.APIError(409, "ALREADY_CANCELLED", "ya anulada")
        assert "409" in str(exc) and "ALREADY_CANCELLED" in str(exc) and "ya anulada" in str(exc)


class TestConstruccion:
    def test_hace_falta_una_clave(self):
        with pytest.raises(errors.ConfigurationError, match="api_key"):
            Transport("")

    @responses.activate
    def test_cabeceras_por_defecto(self, sin_dormir):
        responses.add(responses.GET, RUTA, json={})
        transporte(sin_dormir).request("GET", SANDBOX, "/v1/facturas")
        enviadas = responses.calls[0].request.headers
        assert enviadas["x-api-key"] == "k"
        assert enviadas["Accept"] == "application/json"
        assert enviadas["User-Agent"].startswith("veribai-python/")

    @pytest.mark.parametrize("clave", ["z", "corta", "una-clave-de-api-larguisima-0000"])
    def test_la_clave_nunca_aparece_entera_en_el_repr(self, clave):
        # A repr lands in logs and tracebacks. Showing a tail is only safe once
        # there is enough key for the tail not to BE the key.
        mostrado = repr(Transport(clave)).split("key=")[1].split()[0]
        assert mostrado.startswith("***")
        assert clave not in mostrado

    @responses.activate
    def test_cuerpo_json_sin_escapar_acentos(self, sin_dormir):
        responses.add(responses.POST, f"{SANDBOX}/v1/x", json={})
        transporte(sin_dormir).request("POST", SANDBOX, "/v1/x", json={"d": "consultoría"})
        assert "consultoría".encode() in responses.calls[0].request.body

    @responses.activate
    def test_204_sin_cuerpo(self, sin_dormir):
        responses.add(responses.DELETE, f"{SANDBOX}/v1/x", status=204, body="")
        r = transporte(sin_dormir).request("DELETE", SANDBOX, "/v1/x")
        assert r.datos == {}


class TestCasosLimite:
    @responses.activate
    def test_timeout_se_reintenta_en_ruta_idempotente(self, sin_dormir):
        url = f"{SANDBOX}/v1/verifactu/crear"
        responses.add(responses.POST, url, body=requests.Timeout())
        responses.add(responses.POST, url, json={"idFactura": "F1"})
        r = transporte(sin_dormir).request(
            "POST", SANDBOX, "/v1/verifactu/crear", json={}, idempotente=True
        )
        assert r.datos["idFactura"] == "F1"
        assert len(responses.calls) == 2

    def test_construir_error_acepta_un_cuerpo_que_no_es_objeto(self):
        class RespuestaFalsa:
            status_code = 500
            content = b"[1,2]"
            reason = "Server Error"
            headers: ClassVar[dict] = {}

            def json(self):
                return [1, 2]

        err = construir_error(RespuestaFalsa())  # type: ignore[arg-type]
        assert isinstance(err, errors.ServerError)
        assert err.payload == {"_raw": [1, 2]}

    @responses.activate
    def test_errors_que_no_es_una_lista_se_ignora(self, sin_dormir):
        responses.add(
            responses.GET, RUTA, json={"code": "X", "message": "m", "errors": {"a": 1}}, status=400
        )
        with pytest.raises(errors.ValidationError) as exc:
            transporte(sin_dormir).request("GET", SANDBOX, "/v1/facturas")
        assert exc.value.errors == []
