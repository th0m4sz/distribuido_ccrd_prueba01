"""Lanza procesos TCP independientes en loopback y analiza sus CSV al terminar."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

from analizar import analyze
from crear_config import make_config
from modelo import Model


def run_local(n=4, topology="anillo", steps=2000, output=None, delay_ms=0,
              base_port=15100, startup_stagger=.05):
    run_id = "local-" + uuid.uuid4().hex
    folder = Path(output or Path("resultados") / run_id).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    config = make_config(n, topology, True)
    config.update(steps=steps, period_s=0)
    for p in config["nodes"]:
        p["port"] = base_port + p["id"]
    Model(config)
    config_path = folder / "config.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    processes, streams = [], []
    script = Path(__file__).with_name("nodo.py")
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        for i in range(1, n + 1):
            stream = (folder / f"consola_{i}.txt").open("w", encoding="utf-8")
            streams.append(stream)
            cmd = [sys.executable, str(script), "--config", str(config_path), "--id", str(i),
                   "--run-id", run_id, "--salida", str(folder), "--bind", "127.0.0.1",
                   "--timeout", "3", "--startup-timeout", "30", "--grace", "3",
                   "--delay-ms", str(delay_ms if i == n else 0)]
            processes.append(subprocess.Popen(cmd, stdout=stream, stderr=subprocess.STDOUT, creationflags=flags))
            time.sleep(startup_stagger)
        deadline = time.monotonic() + max(90, steps * (.05 + delay_ms / 1000))
        while any(p.poll() is None for p in processes):
            if time.monotonic() > deadline:
                raise TimeoutError("Prueba TCP excedio el tiempo esperado")
            if any(p.poll() not in (None, 0) for p in processes):
                raise RuntimeError(f"Fallo un nodo; consultar consolas en {folder}")
            time.sleep(.05)
        if any(p.returncode != 0 for p in processes):
            raise RuntimeError(f"Fallo un nodo; consultar consolas en {folder}")
        result = analyze(folder)
        print(f"Resultados: {folder}", flush=True)
        print("Ensayo verificado." if result["passed"] else "Ensayo terminado; revisar el reparto final en resumen.json.", flush=True)
        return result
    finally:
        for p in processes:
            if p.poll() is None:
                p.terminate()
        for p in processes:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        for stream in streams:
            stream.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--nodos", type=int, choices=(4, 6), default=4)
    p.add_argument("--topologia", choices=("anillo", "estrella"), default="anillo")
    p.add_argument("--pasos", type=int, default=2000)
    p.add_argument("--salida", type=Path)
    p.add_argument("--retardo-ms", type=float, default=0)
    p.add_argument("--puerto-base", type=int, default=15100)
    args = p.parse_args()
    if args.pasos <= 0 or args.retardo_ms < 0:
        p.error("pasos > 0 y retardo-ms >= 0")
    r = run_local(args.nodos, args.topologia, args.pasos, args.salida, args.retardo_ms, args.puerto_base)
    return 0 if r["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
