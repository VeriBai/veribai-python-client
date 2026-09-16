"""Endpoint groups, one module per area of the API."""

from .clientes import ClientesRecurso
from .cuenta import CuentaRecurso
from .cumplimiento import CumplimientoRecurso
from .dispositivos import DispositivosRecurso
from .facturas import FacturasRecurso
from .nif import NifRecurso
from .registros import RegistrosRecurso
from .representacion import RepresentacionRecurso
from .ticketbai import TicketbaiRecurso
from .verifactu import VerifactuRecurso
from .webhooks import WebhooksRecurso

__all__ = [
    "ClientesRecurso",
    "CuentaRecurso",
    "CumplimientoRecurso",
    "DispositivosRecurso",
    "FacturasRecurso",
    "NifRecurso",
    "RegistrosRecurso",
    "RepresentacionRecurso",
    "TicketbaiRecurso",
    "VerifactuRecurso",
    "WebhooksRecurso",
]
