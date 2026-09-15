"""Reune en pi-2 un ensayo de las placas 2, 4, 5 y 6 y crea la grafica."""
import argparse
import re
import shutil
import subprocess
import tarfile
from pathlib import Path


REMOTE_NODES = {
    2: ("pi-4.local", 2),
    3: ("pi-5.local", 3),
    4: ("pi-6.local", 4),
}


def valid_name(value):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise argparse.ArgumentTypeError("Use solo letras, numeros, guion y guion bajo")
    return value


def copy_local(source, destination):
    for suffix in ("csv", "json"):
        path = source / f"nodo_1.{suffix}"
        if not path.is_file():
            raise FileNotFoundError(f"No existe el resultado local: {path}")
        shutil.copy2(path, destination / path.name)


def copy_remote(user, host, node_id, project, experiment, destination):
    remote = f"{user}@{host}:{project}/resultados/{experiment}/nodo_{node_id}.*"
    print(f"Copiando nodo {node_id} desde {host} ...", flush=True)
    subprocess.run(["scp", remote, str(destination)], check=True)


def collect(experiment, user="admin", project="~/distribuido_ccrd_prueba01"):
    root = Path(__file__).resolve().parent
    results = root / "resultados"
    source = results / experiment
    name = f"RECOLECCION_{experiment}_4_PLACAS"
    destination = results / name
    archive = results / f"{name}.tar.gz"

    if destination.exists() or archive.exists():
        raise FileExistsError(
            f"Ya existe {destination} o su comprimido. Use otro nombre de ensayo."
        )
    destination.mkdir(parents=True)
    try:
        print("Copiando nodo 1 desde esta placa (pi-2) ...", flush=True)
        copy_local(source, destination)
        for _, (host, node_id) in REMOTE_NODES.items():
            copy_remote(user, host, node_id, project, experiment, destination)

        expected = {
            destination / f"nodo_{node}.{suffix}"
            for node in range(1, 5)
            for suffix in ("csv", "json")
        }
        missing = sorted(str(path.name) for path in expected if not path.is_file())
        if missing:
            raise RuntimeError("Faltan archivos: " + ", ".join(missing))

        # graficar llama primero al analizador, que verifica IDs, rondas y run-id.
        from graficar import plot
        plot(destination)

        with tarfile.open(archive, "w:gz") as package:
            package.add(destination, arcname=name)
    except Exception:
        # Conserva lo copiado para diagnosticar, pero nunca crea un paquete incompleto.
        if archive.exists():
            archive.unlink()
        raise

    print("\nRECOLECCION TERMINADA")
    print(f"Carpeta: {destination}")
    print(f"Grafica: {destination / 'trayectorias.png'}")
    print(f"Archivo para llevar al PC: {archive}")
    return destination, archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ensayo", required=True, type=valid_name,
                        help="Nombre usado en --run-id y --salida, por ejemplo ensayo_003")
    parser.add_argument("--usuario", default="admin", type=valid_name)
    parser.add_argument("--proyecto-remoto", default="~/distribuido_ccrd_prueba01")
    args = parser.parse_args()
    collect(args.ensayo, args.usuario, args.proyecto_remoto)


if __name__ == "__main__":
    main()
