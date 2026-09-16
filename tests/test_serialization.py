"""Money and dates must reach the wire in exactly the shapes the schemas demand."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from veribai import errors
from veribai.serialization import (
    IMPORTE_RE,
    TIPO_RE,
    cantidad,
    fecha,
    hora,
    importe,
    limpiar,
    preparar,
    tipo,
)


class TestImporte:
    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [
            (Decimal("121"), "121.00"),
            (Decimal("121.0"), "121.00"),
            (Decimal("100.5"), "100.50"),
            (Decimal("0"), "0.00"),
            (Decimal("-50"), "-50.00"),
            (0, "0.00"),
            (1000, "1000.00"),
            ("1000", "1000.00"),
            ("  121.00  ", "121.00"),
        ],
    )
    def test_formatos_aceptados(self, entrada, esperado):
        assert importe(entrada) == esperado

    def test_siempre_casa_con_el_patron_oficial(self):
        for valor in (Decimal("121"), Decimal("-0.01"), 999999999999):
            assert IMPORTE_RE.match(importe(valor)), valor

    def test_nunca_notacion_cientifica(self):
        # Decimal("1E+3") formats as '1E+3' by default — the API refuses that.
        assert importe(Decimal("1E+3")) == "1000.00"

    def test_float_se_rechaza(self):
        with pytest.raises(errors.ImporteError, match="float is refused"):
            importe(121.0)

    def test_bool_no_es_un_importe(self):
        with pytest.raises(errors.ImporteError, match="boolean"):
            importe(True)

    def test_nan_se_rechaza(self):
        # Decimal("NaN") raises on neither construction nor quantize: only an
        # explicit is_finite() check stops it reaching a signed document.
        with pytest.raises(errors.ImporteError, match="finite"):
            importe(Decimal("NaN"))

    def test_infinito_se_rechaza(self):
        with pytest.raises(errors.ImporteError, match="finite"):
            importe(Decimal("Infinity"))

    def test_mas_de_dos_decimales_no_se_redondea_en_silencio(self):
        with pytest.raises(errors.ImporteError, match="more than 2 decimals"):
            importe(Decimal("100.555"))

    def test_decimales_que_no_cambian_el_valor_se_aceptan(self):
        assert importe(Decimal("100.5000")) == "100.50"

    def test_mas_de_doce_digitos_enteros(self):
        with pytest.raises(errors.ImporteError, match="integer digits"):
            importe(Decimal("1234567890123"))

    def test_texto_no_numerico(self):
        with pytest.raises(errors.ImporteError, match="not a decimal"):
            importe("mucho dinero")

    def test_texto_vacio(self):
        with pytest.raises(errors.ImporteError, match="empty"):
            importe("")

    def test_tipo_no_soportado(self):
        with pytest.raises(errors.ImporteError, match="expected Decimal"):
            importe(object())  # type: ignore[arg-type]


class TestCantidad:
    def test_ocho_decimales_se_conservan(self):
        # TicketBAI line quantities are ImporteSgn12.8, not 12.2.
        assert cantidad(Decimal("1.00000001")) == "1.00000001"

    def test_entero_sin_relleno(self):
        assert cantidad(1) == "1"

    def test_mas_de_ocho_decimales(self):
        with pytest.raises(errors.ImporteError, match="8"):
            cantidad(Decimal("1.000000001"))


class TestTipo:
    @pytest.mark.parametrize(
        ("entrada", "esperado"), [(21, "21"), (Decimal("7.5"), "7.5"), (0, "0")]
    )
    def test_formatos(self, entrada, esperado):
        assert tipo(entrada) == esperado
        assert TIPO_RE.match(tipo(entrada))

    def test_negativo_se_rechaza(self):
        # The official Tipo pattern is unsigned; a negative rate is not a thing.
        with pytest.raises(errors.ImporteError, match="negative"):
            tipo(Decimal("-21"))

    def test_demasiados_digitos(self):
        with pytest.raises(errors.ImporteError, match="Tipo pattern"):
            tipo(Decimal("1000"))


class TestFecha:
    def test_date(self):
        assert fecha(dt.date(2026, 1, 5)) == "05-01-2026"

    def test_dos_digitos_obligatorios(self):
        # '1-8-2026' is refused by the API; refuse it here too rather than
        # discovering it after a round trip.
        with pytest.raises(errors.FechaError, match="two digits"):
            fecha("1-8-2026")

    def test_cadena_valida_pasa(self):
        assert fecha("05-01-2026") == "05-01-2026"

    def test_datetime_se_rechaza(self):
        with pytest.raises(errors.FechaError, match="calendar dates"):
            fecha(dt.datetime(2026, 1, 5, 10, 0))

    def test_tipo_invalido(self):
        with pytest.raises(errors.FechaError, match="expected"):
            fecha(20260105)  # type: ignore[arg-type]


class TestHora:
    def test_time(self):
        assert hora(dt.time(10, 0, 0)) == "10:00:00"

    def test_cadena(self):
        assert hora("10:00:00") == "10:00:00"

    def test_formato_invalido(self):
        with pytest.raises(errors.FechaError, match="HH:MM:SS"):
            hora("9:05:00")

    def test_tipo_invalido(self):
        with pytest.raises(errors.FechaError):
            hora(100000)  # type: ignore[arg-type]


class TestPreparar:
    def test_convierte_en_profundidad(self):
        payload = {
            "cabecera": {"fechaExpedicion": dt.date(2026, 1, 5), "hora": dt.time(9, 30, 0)},
            "lineas": [{"importeTotal": Decimal("121"), "cantidad": Decimal("1.5")}],
        }
        assert preparar(payload) == {
            "cabecera": {"fechaExpedicion": "05-01-2026", "hora": "09:30:00"},
            "lineas": [{"importeTotal": "121.00", "cantidad": "1.50"}],
        }

    def test_booleanos_intactos(self):
        # Both `true` and `"S"` are valid on the wire; the library must not
        # "helpfully" convert either into the other.
        assert preparar({"subsanacion": True, "rechazoPrevio": "X"}) == {
            "subsanacion": True,
            "rechazoPrevio": "X",
        }

    def test_none_se_conserva(self):
        # `eventos: null` is meaningful — it clears a webhook subscription.
        assert preparar({"eventos": None}) == {"eventos": None}

    def test_float_se_rechaza_con_el_campo_nombrado(self):
        with pytest.raises(errors.ImporteError, match=r"totales\.importeTotal"):
            preparar({"totales": {"importeTotal": 121.0}})

    def test_datetime_se_rechaza_con_el_campo_nombrado(self):
        with pytest.raises(errors.FechaError, match=r"cabecera\.fechaExpedicion"):
            preparar({"cabecera": {"fechaExpedicion": dt.datetime(2026, 1, 5)}})

    def test_indice_de_lista_en_el_mensaje(self):
        with pytest.raises(errors.ImporteError, match=r"lineas\[1\].importeTotal"):
            preparar({"lineas": [{"importeTotal": Decimal("1")}, {"importeTotal": 2.0}]})

    def test_precision_alta_pasa_a_la_api_sin_redondear(self):
        # Deciding locally that 100.555 is invalid would mean mirroring a fiscal
        # rule. Pass it on; the API is the authority.
        assert preparar({"x": Decimal("100.555")}) == {"x": "100.555"}

    def test_tuplas_se_normalizan_a_listas(self):
        assert preparar({"nifs": ("A", "B")}) == {"nifs": ["A", "B"]}


def test_limpiar_descarta_none():
    assert limpiar({"a": 1, "b": None, "c": False}) == {"a": 1, "c": False}
