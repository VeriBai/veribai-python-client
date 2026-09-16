"""Turning Python values into the exact shapes the API demands.

This module is **format only, never fiscal policy**. It knows that an amount
travels as a plain decimal string and that a date is ``DD-MM-YYYY``; it does not
know whether your invoice is legal. That line matters: the fiscal rules move
(they are set by the AEAT and three foral haciendas, and two of VeriBai's own
date rules are still open decisions), so a client that pre-judged them would go
stale and start rejecting invoices the API would have accepted. The API is the
authority on what is valid.

What it *will* refuse is input that cannot survive the trip:

* ``float`` — binary floating point cannot represent 0.10 exactly, and an
  invoice total that is off by a cent is a fiscal defect, not a rounding
  nuisance. Pass ``Decimal``, ``int`` or ``str``.
* ``NaN`` / ``Infinity`` — ``Decimal("NaN")`` raises on neither construction nor
  quantization, so only an explicit check stops it reaching the wire.
* more than 12 integer digits or more than 8 decimals, neither of which any
  VeriBai or authority schema accepts.
"""

from __future__ import annotations

import datetime as _dt
import re
from decimal import Decimal, DecimalException, InvalidOperation
from typing import Any, Dict, List, Union

from .errors import FechaError, ImporteError

Numerico = Union[Decimal, int, str]

#: ``ImporteSgn12.2Type`` — identical in the AEAT and TicketBAI schemas.
IMPORTE_RE = re.compile(r"^[+-]?\d{1,12}(\.\d{1,2})?$")
#: ``ImporteSgn12.8Type`` — TicketBAI line quantities and unit amounts.
IMPORTE_8_RE = re.compile(r"^[+-]?\d{1,12}(\.\d{1,8})?$")
#: ``Tipo2.2Type`` / ``Tipo3.2Type`` — a percentage, unsigned.
TIPO_RE = re.compile(r"^\d{1,3}(\.\d{1,2})?$")
FECHA_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")
HORA_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")

_MAX_DECIMALES = 8
_MAX_ENTEROS = 12


def _a_decimal(value: Numerico, campo: str) -> Decimal:
    if isinstance(value, bool):  # bool is an int subclass — catch it first
        raise ImporteError(f"{campo}: expected an amount, got a boolean")
    if isinstance(value, float):
        raise ImporteError(
            f"{campo}: float is refused for money — 0.1 is not exactly 0.1 in binary "
            f"floating point and a cent of drift is a fiscal defect. "
            f"Use Decimal({str(value)!r}), an int, or a string."
        )
    if isinstance(value, Decimal):
        dec = value
    elif isinstance(value, int):
        dec = Decimal(value)
    elif isinstance(value, str):
        texto = value.strip()
        if not texto:
            raise ImporteError(f"{campo}: empty string is not an amount")
        try:
            dec = Decimal(texto)
        except (InvalidOperation, DecimalException):
            raise ImporteError(f"{campo}: {value!r} is not a decimal number") from None
    else:
        raise ImporteError(f"{campo}: expected Decimal, int or str, got {type(value).__name__}")

    if not dec.is_finite():
        raise ImporteError(f"{campo}: {value!r} is not a finite number")
    return dec


def _formatear(dec: Decimal, campo: str, minimo_decimales: int) -> str:
    """Render without exponent, padded to at least ``minimo_decimales`` places.

    Never rounds and never truncates: an amount with more precision than the
    minimum is passed through as written, so the API — not this library — decides
    whether it is acceptable.
    """
    texto = format(dec, "f")  # no scientific notation, ever
    negativo = texto.startswith("-")
    if negativo:
        texto = texto[1:]
    entero, _, decimales = texto.partition(".")
    entero = entero or "0"
    if len(entero.lstrip("0") or "0") > _MAX_ENTEROS:
        raise ImporteError(f"{campo}: more than {_MAX_ENTEROS} integer digits ({dec})")
    if len(decimales) > _MAX_DECIMALES:
        raise ImporteError(
            f"{campo}: {dec} has {len(decimales)} decimals; no VeriBai or authority "
            f"schema accepts more than {_MAX_DECIMALES}. Quantize it yourself so the "
            f"rounding is your decision, not this library's."
        )
    decimales = decimales.ljust(minimo_decimales, "0")
    salida = f"{entero}.{decimales}" if decimales else entero
    return f"-{salida}" if negativo and dec != 0 else salida


def importe(value: Numerico, *, campo: str = "importe") -> str:
    """Render an amount as the API's decimal string, **exactly two decimals**.

    Raises :class:`~veribai.errors.ImporteError` rather than rounding when the
    value carries more precision: rounding a tax amount silently is how a cuota
    stops matching its desglose.

        >>> importe(Decimal("121"))
        '121.00'
        >>> importe(Decimal("100.5"))
        '100.50'
    """
    dec = _a_decimal(value, campo)
    exponente = -dec.as_tuple().exponent if dec.as_tuple().exponent < 0 else 0  # type: ignore[operator]
    if exponente > 2 and dec != dec.quantize(Decimal("0.01")):
        raise ImporteError(
            f"{campo}: {dec} has more than 2 decimals. Quantize it first — "
            f"Decimal({str(dec)!r}).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) — "
            f"so the rounding is your decision."
        )
    return _formatear(dec.quantize(Decimal("0.01")), campo, 2)


def cantidad(value: Numerico, *, campo: str = "cantidad") -> str:
    """Render a TicketBAI line quantity or unit amount (up to 8 decimals)."""
    return _formatear(_a_decimal(value, campo), campo, 0)


def tipo(value: Numerico, *, campo: str = "tipoImpositivo") -> str:
    """Render a tax rate. Unsigned, at most 3 integer digits and 2 decimals.

    >>> tipo(21)
    '21'
    >>> tipo(Decimal("7.5"))
    '7.5'
    """
    dec = _a_decimal(value, campo)
    if dec < 0:
        raise ImporteError(f"{campo}: a tax rate cannot be negative ({dec})")
    texto = _formatear(dec, campo, 0)
    if not TIPO_RE.match(texto):
        raise ImporteError(
            f"{campo}: {texto!r} does not match the official Tipo pattern "
            f"(up to 3 integer digits and 2 decimals, unsigned)"
        )
    return texto


def fecha(value: Union[_dt.date, str], *, campo: str = "fecha") -> str:
    """Render a date as ``DD-MM-YYYY`` with two digits for day and month.

    ``datetime`` is refused: an invoice date is a calendar date, and silently
    dropping a time component is how a timezone bug becomes a wrong fiscal date.
    """
    if isinstance(value, _dt.datetime):
        raise FechaError(
            f"{campo}: pass a datetime.date, not a datetime — fiscal dates are "
            f"calendar dates in Europe/Madrid, and dropping the time silently is "
            f"how they end up off by one day. Use value.date() if that is what you mean."
        )
    if isinstance(value, _dt.date):
        return value.strftime("%d-%m-%Y")
    if isinstance(value, str):
        texto = value.strip()
        if not FECHA_RE.match(texto):
            raise FechaError(
                f"{campo}: {value!r} is not DD-MM-YYYY with two digits for day and "
                f"month ('1-8-2026' is rejected by the API)"
            )
        return texto
    raise FechaError(f"{campo}: expected datetime.date or str, got {type(value).__name__}")


def hora(value: Union[_dt.time, str], *, campo: str = "horaExpedicion") -> str:
    """Render a time of day as ``HH:MM:SS`` (TicketBAI ``horaExpedicion``).

    Omit the field entirely to let the API stamp the current Europe/Madrid time,
    which is what matches the peninsular date beside it.
    """
    if isinstance(value, _dt.time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, str):
        texto = value.strip()
        if not HORA_RE.match(texto):
            raise FechaError(f"{campo}: {value!r} is not HH:MM:SS (24-hour, two digits each)")
        return texto
    raise FechaError(f"{campo}: expected datetime.time or str, got {type(value).__name__}")


def preparar(valor: Any, *, campo: str = "") -> Any:
    """Recursively convert a payload's Python values into wire form.

    Applied automatically to every request body, so you can hand the client
    ``Decimal`` amounts and ``date`` objects and they arrive in the shapes the
    API expects:

    * ``Decimal`` → decimal string, padded to at least 2 places, **never rounded**
      (a value with 3–8 decimals is passed through so the API can judge it, and
      the TicketBAI 8-decimal line fields keep their precision);
    * ``date`` → ``DD-MM-YYYY``; ``time`` → ``HH:MM:SS``;
    * ``float`` → refused (see the module docstring);
    * everything else — ``str``, ``int``, ``bool``, ``None``, lists, dicts —
      passes through untouched. Booleans in particular are left alone: both
      ``subsanacion: true`` and ``subsanacion: "S"`` are valid on the wire.
    """
    if isinstance(valor, dict):
        return {k: preparar(v, campo=f"{campo}.{k}" if campo else str(k)) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [preparar(v, campo=f"{campo}[{i}]") for i, v in enumerate(valor)]
    if isinstance(valor, bool) or valor is None:
        return valor
    if isinstance(valor, Decimal):
        return _formatear(_a_decimal(valor, campo or "importe"), campo or "importe", 2)
    if isinstance(valor, float):
        raise ImporteError(
            f"{campo or 'value'}: float is refused — use Decimal({str(valor)!r}) "
            f"so the amount is exact"
        )
    if isinstance(valor, _dt.datetime):
        raise FechaError(
            f"{campo or 'value'}: pass a datetime.date (or an explicit string), not a datetime"
        )
    if isinstance(valor, _dt.date):
        return valor.strftime("%d-%m-%Y")
    if isinstance(valor, _dt.time):
        return valor.strftime("%H:%M:%S")
    return valor


def limpiar(datos: Dict[str, Any]) -> Dict[str, Any]:
    """Drop ``None`` values from a flat dict of query parameters."""
    return {k: v for k, v in datos.items() if v is not None}


__all__: List[str] = [
    "cantidad",
    "fecha",
    "hora",
    "importe",
    "limpiar",
    "preparar",
    "tipo",
]
