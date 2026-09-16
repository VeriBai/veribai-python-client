"""Alta capacidad: registering devices during the preparation window.

    python examples/04_alta_capacidad.py

A high-volume taxpayer can run one hash chain per device instead of one per NIF. The
preparation window is where you register them — and nothing about invoice routing
changes until VeriBai staff flip the account to `activa`.
"""

from __future__ import annotations

import os

import veribai

NIF_EMISOR = os.environ["VERIBAI_NIF_EMISOR"]
DISPOSITIVOS = {"TPV-BARRA-01": "Barra", "TPV-SALA-02": "Sala", "ERP-CENTRAL": "Oficina"}


def main() -> None:
    with veribai.Client() as client:
        estado = client.dispositivos.listar(NIF_EMISOR)
        fase = estado["faseAltaCapacidad"]
        print(f"fase: {fase} · modo de cadena: {estado['modoCadena']}")

        if fase == "no_contratada":
            raise SystemExit("Alta capacidad is a contracted option — talk to VeriBai first")

        for id_maquina, etiqueta in DISPOSITIVOS.items():
            try:
                respuesta = client.dispositivos.registrar(NIF_EMISOR, id_maquina, etiqueta=etiqueta)
                estado_alta = "reactivado" if respuesta.get("reactivado") else "registrado"
                print(f"  {id_maquina}: {estado_alta}")
            except veribai.ConflictError as exc:
                if exc.code != "MACHINE_ALREADY_REGISTERED":
                    raise
                print(f"  {id_maquina}: ya estaba activo")

        # The head office's own series, claimed before any device can take them.
        reserva = client.dispositivos.reservar_series_centralizadas(NIF_EMISOR, ["FC", "FR"])
        print(f"series centralizadas: {reserva['reservadas']}")
        for omitida in reserva["omitidas"]:
            print(f"  {omitida['serie']} ya es de {omitida.get('idMaquina')}")

        if fase == "preparacion":
            # What your systems ACTUALLY sent, versus what is registered. An empty list
            # is not proof nothing sends a tag — a nightly batch may not have run yet.
            estado = client.dispositivos.listar(NIF_EMISOR)
            print(f"\nobservando desde {estado.get('observandoDesde')}")
            for visto in estado.get("idsMaquinaVistos", []):
                marca = "ok" if visto["registrado"] else "SIN REGISTRAR"
                print(f"  {visto['idMaquina']}: {marca} (visto {visto['ultimaVez']})")

            # When everything reconciles, tell VeriBai. Idempotent: the first press is
            # the one the operator sees, so a second never resets their clock.
            # client.dispositivos.solicitar_activacion(NIF_EMISOR)


if __name__ == "__main__":
    main()
