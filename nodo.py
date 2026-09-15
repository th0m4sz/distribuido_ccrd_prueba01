"""Ejecutar una instancia por placa. Cada placa conserva y actualiza solo su x."""
import argparse
import csv
import json
from pathlib import Path
import sys
import time

from modelo import Model
from red import PeerClient, ProtocolError, SnapshotStore, serve


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--id", type=int, required=True)
    parser.add_argument("--run-id", required=True, help="Mismo identificador NUEVO en todas las placas")
    parser.add_argument("--salida", type=Path, default=Path("resultados/placas"))
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--startup-timeout", type=float, default=180)
    parser.add_argument("--grace", type=float, default=15, help="Segundos sirviendo tras terminar (>= timeout)")
    parser.add_argument("--delay-ms", type=float, default=0, help="Retardo local artificial para experimentos")
    args = parser.parse_args(argv)
    model = Model.load(args.config)
    if args.id not in model.nodes:
        parser.error("ID no configurado")
    if not args.run_id or len(args.run_id) > 100:
        parser.error("run-id debe contener entre 1 y 100 caracteres")
    if not (0 < args.timeout <= args.grace and args.startup_timeout > 0 and args.delay_ms >= 0):
        parser.error("Requiere 0 < timeout <= grace, startup-timeout > 0, delay-ms >= 0")
    args.salida.mkdir(parents=True, exist_ok=True)
    csv_path = args.salida / f"nodo_{args.id}.csv"
    # Crear exclusivamente: evita sobrescribir datos experimentales por accidente.
    log = csv_path.open("x", newline="", encoding="utf-8")
    store = SnapshotStore(model, args.id, args.run_id)
    x = model.initial()[args.id]
    store.publish(0, model.state(args.id, x))
    server = None
    clients = {j: PeerClient(model, args.id, j, args.run_id) for j in model.neighbors[args.id]}
    status, error, completed = "running", None, 0
    start = time.monotonic()
    metadata = {"node": args.id, "run_id": args.run_id, "config_sha256": model.fingerprint,
                "config": model.config, "alpha": model.alpha,
                "neighbors": list(model.neighbors[args.id]), "status": status}
    meta_path = args.salida / f"nodo_{args.id}.json"
    try:
        server = serve(store, args.bind)
        writer = csv.writer(log)
        writer.writerow(["round", "algorithm_time", "wall_s", "node", "x_kw", "hat", "fitness", "delta_kw"])

        def record(k, delta):
            s = model.state(args.id, x)
            writer.writerow([k, k * model.alpha, time.monotonic() - start, args.id,
                             x, s["hat"], s["fitness"], delta])
            log.flush()

        record(0, 0)
        print(f"Nodo {args.id}; vecinos {list(clients)}; alpha={model.alpha:.6g}; run={args.run_id}", flush=True)
        for k in range(model.steps):
            tick = time.monotonic()
            peers = {j: client.fetch(k, args.startup_timeout if k == 0 else args.timeout)
                     for j, client in clients.items()}
            old_x = x
            x = model.local_step(args.id, model.state(args.id, x), peers)
            completed = k + 1
            record(completed, x - old_x)
            store.publish(completed, model.state(args.id, x))
            if completed % 500 == 0 or completed == model.steps:
                print(f"Nodo {args.id} k={completed} x={x:.9f} kW", flush=True)
            pause = model.period + args.delay_ms / 1000 - (time.monotonic() - tick)
            if pause > 0:
                time.sleep(pause)
        status = "completed"  # Fin de rondas; NO significa convergencia al optimo.
    except KeyboardInterrupt:
        status, error = "interrupted", "Interrumpido por usuario"
        store.fail(error)
    except (OSError, ValueError, ProtocolError, TimeoutError) as exc:
        status, error = "failed", str(exc)
        store.fail(error)
        print(f"ERROR nodo {args.id}: {error}", file=sys.stderr, flush=True)
    finally:
        metadata.update(status=status, error=error, completed_rounds=completed,
                        x_final=x, wall_s=time.monotonic() - start)
        meta_path.write_text(json.dumps(metadata, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        log.close()
        for client in clients.values():
            client.close()
        if server:
            # Mantener disponibles las ultimas rondas y propagar fallos a los vecinos.
            try:
                time.sleep(args.grace)
            except KeyboardInterrupt:
                pass
            server.shutdown()
            server.server_close()
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
