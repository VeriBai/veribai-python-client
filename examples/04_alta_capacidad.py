"""Alta capacidad: registrar dispositivos durante la ventana de preparación.

    python examples/04_alta_capacidad.py

Un obligado tributario de mucho volumen puede llevar una cadena de hash por dispositivo en
lugar de una por NIF. La ventana de preparación es donde se registran, y nada del
enrutado de facturas cambia hasta que VeriBai pasa la cuenta a `activa`.
"""

from __future__ import annotations

import os

import veribai

NIF_EMISOR = os.environ["VERIBAI_NIF_EMISOR"]
DISPOSITIVOS = {"TPV-BARRA-01": "Barra", "TPV-SALA-02": "Sala", "ERP-CENTRAL": "Oficina"}


def main() -> None:
    # `environment` explícito a propósito: ver examples/01_primera_factura.py.
    with veribai.Client(environment="test") as client:
        estado = client.dispositivos.listar(NIF_EMISOR)
        fase = estado["faseAltaCapacidad"]
        print(f"fase: {fase} · modo de cadena: {estado['modoCadena']}")

        if fase == "no_contratada":
            raise SystemExit("Alta capacidad es una opción contratada: habla antes con VeriBai")

        for id_maquina, etiqueta in DISPOSITIVOS.items():
            try:
                respuesta = client.dispositivos.registrar(NIF_EMISOR, id_maquina, etiqueta=etiqueta)
                estado_alta = "reactivado" if respuesta.get("reactivado") else "registrado"
                print(f"  {id_maquina}: {estado_alta}")
            except veribai.ConflictError as exc:
                if exc.code != "MACHINE_ALREADY_REGISTERED":
                    raise
                print(f"  {id_maquina}: ya estaba activo")

        # Las series de la central, reclamadas antes de que ningún dispositivo las coja.
        reserva = client.dispositivos.reservar_series_centralizadas(NIF_EMISOR, ["FC", "FR"])
        print(f"series centralizadas: {reserva['reservadas']}")
        for omitida in reserva["omitidas"]:
            print(f"  {omitida['serie']} ya es de {omitida.get('idMaquina')}")

        if fase == "preparacion":
            # Lo que tus sistemas mandan DE VERDAD, frente a lo que está registrado. Una lista
            # vacía no prueba que nadie envíe etiqueta: puede que un batch nocturno no haya
            # llegado a ejecutarse.
            estado = client.dispositivos.listar(NIF_EMISOR)
            print(f"\nobservando desde {estado.get('observandoDesde')}")
            for visto in estado.get("idsMaquinaVistos", []):
                marca = "ok" if visto["registrado"] else "SIN REGISTRAR"
                print(f"  {visto['idMaquina']}: {marca} (visto {visto['ultimaVez']})")

            # Cuando todo cuadre, avisa a VeriBai. Es idempotente: la primera solicitud es la
            # que vale, así que pulsarlo otra vez nunca reinicia el reloj del operador.
            # client.dispositivos.solicitar_activacion(NIF_EMISOR)


if __name__ == "__main__":
    main()
