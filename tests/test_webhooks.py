"""Webhook verification.

The signature covers the RAW request bytes. Every test here exists because there
is a realistic way to get that wrong and not notice until a forged delivery is
processed.
"""

from __future__ import annotations

import json

import pytest

from veribai import webhooks
from veribai.errors import WebhookSignatureError

SECRETO = "un-secreto-de-al-menos-16"

CUERPO = json.dumps(
    {
        "evento": "factura.registrada",
        "idEntrega": "5f2c0f5e-1b7e-5a2d-9f0a-2b3c4d5e6f70",
        "timestamp": "2026-09-15T10:00:00Z",
        "datos": {
            "sistemaFiscal": "verifactu",
            "nifEmisor": "B12345674",
            "idFactura": "FAC-1",
            "numeroFactura": "A1",
            "tipoFactura": "F1",
            "importeTotal": "121.00",
            "cuotaTotal": "21.00",
            "estadoFactura": "registrada",
            "fechaRegistro": "2026-09-15T10:00:00Z",
            "csvAeat": "CSV-1",
        },
    },
    ensure_ascii=False,
    separators=(",", ":"),  # as a server emits it, no incidental whitespace
).encode("utf-8")


def cabeceras(cuerpo=CUERPO, secreto=SECRETO, **extra):
    return {
        "X-VeriBai-Signature": webhooks.firma_esperada(secreto, cuerpo),
        "X-VeriBai-Event": "factura.registrada",
        "X-VeriBai-Delivery-Id": "5f2c0f5e-1b7e-5a2d-9f0a-2b3c4d5e6f70",
        "Idempotency-Key": "5f2c0f5e-1b7e-5a2d-9f0a-2b3c4d5e6f70",
        **extra,
    }


class TestVerificacion:
    def test_firma_valida(self):
        webhooks.verificar_firma(SECRETO, CUERPO, webhooks.firma_esperada(SECRETO, CUERPO))

    def test_formato_de_la_firma(self):
        firma = webhooks.firma_esperada(SECRETO, CUERPO)
        assert firma.startswith("sha256=")
        assert len(firma) == len("sha256=") + 64

    def test_secreto_incorrecto(self):
        with pytest.raises(WebhookSignatureError, match="mismatch"):
            webhooks.verificar_firma(
                "otro-secreto-cualquiera", CUERPO, cabeceras()["X-VeriBai-Signature"]
            )

    def test_cuerpo_alterado(self):
        firma = webhooks.firma_esperada(SECRETO, CUERPO)
        with pytest.raises(WebhookSignatureError, match="mismatch"):
            webhooks.verificar_firma(SECRETO, CUERPO + b" ", firma)

    def test_reserializar_el_json_invalida_la_firma(self):
        # This is THE mistake: parse, re-dump, then verify. Byte-different body,
        # same meaning, signature will never match.
        firma = webhooks.firma_esperada(SECRETO, CUERPO)
        reserializado = json.dumps(json.loads(CUERPO)).encode("utf-8")  # default separators
        assert reserializado != CUERPO
        with pytest.raises(WebhookSignatureError, match="RAW bytes"):
            webhooks.verificar_firma(SECRETO, reserializado, firma)

    def test_sin_cabecera(self):
        with pytest.raises(WebhookSignatureError, match="missing"):
            webhooks.verificar_firma(SECRETO, CUERPO, None)

    def test_prefijo_ausente(self):
        digest = webhooks.firma_esperada(SECRETO, CUERPO).split("=", 1)[1]
        with pytest.raises(WebhookSignatureError, match="malformed"):
            webhooks.verificar_firma(SECRETO, CUERPO, digest)

    def test_sin_secreto(self):
        with pytest.raises(WebhookSignatureError, match="secret is required"):
            webhooks.verificar_firma("", CUERPO, "sha256=" + "0" * 64)

    def test_cuerpo_de_tipo_imposible(self):
        with pytest.raises(WebhookSignatureError, match="raw bytes"):
            webhooks.firma_esperada(SECRETO, 42)  # type: ignore[arg-type]


class TestParseo:
    def test_entrega_valida(self):
        entrega = webhooks.parse_entrega(CUERPO, cabeceras(), secreto=SECRETO)
        assert entrega.evento == "factura.registrada"
        assert entrega.registrada is True
        assert entrega.rechazada is False
        assert entrega.nif_emisor == "B12345674"
        assert entrega.id_factura == "FAC-1"
        assert entrega.sistema_fiscal == "verifactu"
        assert entrega.datos["csvAeat"] == "CSV-1"

    def test_la_clave_de_dedup_es_el_id_de_entrega(self):
        # Deterministic uuid5 of (webhook, invoice, event): identical on every retry.
        entrega = webhooks.parse_entrega(CUERPO, cabeceras(), secreto=SECRETO)
        assert entrega.clave_dedup == entrega.id_entrega
        assert entrega.id_entrega == "5f2c0f5e-1b7e-5a2d-9f0a-2b3c4d5e6f70"

    def test_no_se_parsea_nada_si_la_firma_falla(self):
        # Hostile input must not be deserialized before it is authenticated.
        basura = b'{"evento": "x"'
        with pytest.raises(WebhookSignatureError, match="mismatch"):
            webhooks.parse_entrega(basura, cabeceras(), secreto=SECRETO)

    def test_cuerpo_firmado_pero_no_json(self):
        cuerpo = b"no soy json"
        with pytest.raises(WebhookSignatureError, match="not valid JSON"):
            webhooks.parse_entrega(cuerpo, cabeceras(cuerpo), secreto=SECRETO)

    def test_cuerpo_firmado_pero_no_es_un_objeto(self):
        cuerpo = b"[1, 2, 3]"
        with pytest.raises(WebhookSignatureError, match="not a JSON object"):
            webhooks.parse_entrega(cuerpo, cabeceras(cuerpo), secreto=SECRETO)

    def test_cabeceras_insensibles_a_mayusculas(self):
        crudas = {k.lower(): v for k, v in cabeceras().items()}
        entrega = webhooks.parse_entrega(CUERPO, crudas, secreto=SECRETO)
        assert entrega.evento == "factura.registrada"

    def test_cuerpo_como_texto(self):
        entrega = webhooks.parse_entrega(CUERPO.decode("utf-8"), cabeceras(), secreto=SECRETO)
        assert entrega.id_factura == "FAC-1"

    def test_cuerpo_conservado_tal_cual(self):
        entrega = webhooks.parse_entrega(CUERPO, cabeceras(), secreto=SECRETO)
        assert entrega.cuerpo == CUERPO


class TestRechazo:
    def _entrega_rechazada(self, **motivo):
        cuerpo = json.dumps(
            {
                "evento": "factura.rechazada",
                "idEntrega": "id-1",
                "timestamp": "2026-09-15T10:00:00Z",
                "datos": {
                    "sistemaFiscal": "ticketbai",
                    "nifEmisor": "B12345674",
                    "idFactura": "FAC-2",
                    "tipoRegistro": "alta",
                    "motivoRechazo": motivo,
                },
            }
        ).encode("utf-8")
        return webhooks.parse_entrega(cuerpo, cabeceras(cuerpo), secreto=SECRETO)

    def test_motivo_de_rechazo(self):
        entrega = self._entrega_rechazada(codigo="B4_2000080", descripcion="Campo incorrecto")
        assert entrega.rechazada is True
        assert entrega.registrada is False
        motivo = entrega.motivo_rechazo
        assert motivo is not None
        assert motivo.codigo == "B4_2000080"
        assert motivo.descripcion == "Campo incorrecto"

    def test_motivos_adicionales(self):
        # Every one must be fixed before resubmitting: each TicketBAI attempt
        # permanently advances the taxpayer's hash chain.
        entrega = self._entrega_rechazada(
            codigo="A",
            descripcion="uno",
            motivosAdicionales=[{"codigo": "B", "descripcion": "dos"}],
        )
        motivo = entrega.motivo_rechazo
        assert motivo is not None
        assert [m.codigo for m in motivo.motivos_adicionales] == ["B"]

    def test_registrada_no_trae_motivo(self):
        entrega = webhooks.parse_entrega(CUERPO, cabeceras(), secreto=SECRETO)
        assert entrega.motivo_rechazo is None

    def test_anulada(self):
        cuerpo = json.dumps(
            {"evento": "factura.anulada", "idEntrega": "i", "timestamp": "t", "datos": {}}
        ).encode("utf-8")
        entrega = webhooks.parse_entrega(cuerpo, cabeceras(cuerpo), secreto=SECRETO)
        assert entrega.anulada is True
        assert entrega.nif_emisor is None
        assert entrega.id_factura is None
        assert entrega.sistema_fiscal is None


class TestCabecerasRaras:
    def test_mapeo_sin_get(self):
        class SoloItems:
            def __init__(self, datos):
                self._datos = datos

            def items(self):
                return self._datos.items()

        entrega = webhooks.parse_entrega(
            CUERPO, SoloItems({k.upper(): v for k, v in cabeceras().items()}), secreto=SECRETO
        )
        assert entrega.evento == "factura.registrada"

    def test_cabecera_ausente_del_todo(self):
        with pytest.raises(WebhookSignatureError, match="missing"):
            webhooks.parse_entrega(CUERPO, {}, secreto=SECRETO)
