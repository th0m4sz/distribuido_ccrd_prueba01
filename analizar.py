"""Analisis posterior de CSV de las placas. No participa en el algoritmo."""
import argparse
import csv
import json
import math
from pathlib import Path

from modelo import Model
from referencia import metrics


def analyze(folder, dispatch_tolerance=.01):
    folder = Path(folder)
    files = sorted(folder.glob("nodo_*.json"))
    if not files:
        raise ValueError("Faltan metadatos nodo_*.json")
    metadata = [json.loads(p.read_text(encoding="utf-8")) for p in files]
    model = Model(metadata[0]["config"])
    by_id = {m["node"]: m for m in metadata}
    if len(by_id) != len(metadata) or set(by_id) != set(model.ids):
        raise ValueError("Faltan nodos o hay metadatos duplicados")
    runs = {m["run_id"] for m in metadata}
    if len(runs) != 1 or any(m["config_sha256"] != model.fingerprint or
                             Model(m["config"]).fingerprint != model.fingerprint for m in metadata):
        raise ValueError("No se pueden mezclar configuraciones o ejecuciones")
    if any(m["status"] != "completed" or m["completed_rounds"] != model.steps for m in metadata):
        raise ValueError("Ejecucion incompleta/fallida: no se certifica balance ni convergencia")
    logs = {}
    for i in model.ids:
        with (folder / f"nodo_{i}.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        if [int(r["round"]) for r in rows] != list(range(model.steps + 1)):
            raise ValueError(f"Nodo {i}: rondas incompletas, duplicadas o desordenadas")
        for row in rows:
            if int(row["node"]) != i:
                raise ValueError("ID del CSV incorrecto")
            model.check_state(i, {"x": float(row["x_kw"]), "hat": float(row["hat"]),
                                  "fitness": float(row["fitness"])})
        if float(rows[-1]["x_kw"]) != by_id[i]["x_final"]:
            raise ValueError("CSV final y metadatos no coinciden")
        logs[i] = rows
    peak_balance, peak_increase, recurrence_error = 0.0, 0.0, 0.0
    previous_cost, previous_states = None, None
    with (folder / "serie.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["round"] + [f"x_{i}" for i in model.ids] + ["balance_error_kw", "cost"])
        for k in range(model.steps + 1):
            x = {i: float(logs[i][k]["x_kw"]) for i in model.ids}
            states = {i: model.state(i, x[i]) for i in model.ids}
            if previous_states:
                for i in model.ids:
                    expected = model.local_step(i, previous_states[i],
                                                {j: previous_states[j] for j in model.neighbors[i]})
                    recurrence_error = max(recurrence_error, abs(expected - x[i]))
            else:
                if any(x[i] != model.nodes[i]["x0"] for i in model.ids):
                    raise ValueError("CSV no empieza en la condicion inicial configurada")
            cost = model.cost(x)
            balance = math.fsum(x.values()) - model.demand
            peak_balance = max(peak_balance, abs(balance))
            if previous_cost is not None:
                peak_increase = max(peak_increase, cost - previous_cost)
            writer.writerow([k] + [x[i] for i in model.ids] + [balance, cost])
            previous_cost, previous_states = cost, states
    result = metrics(model, x)
    result.update(run_id=next(iter(runs)), config_sha256=model.fingerprint, steps=model.steps,
                  max_balance_error_kw=peak_balance, max_cost_increase=peak_increase,
                  max_recurrence_error_kw=recurrence_error,
                  max_wall_s=max(m["wall_s"] for m in metadata), alpha=model.alpha)
    result["passed"] = (peak_balance < 1e-6 and result["max_dispatch_error_kw"] < dispatch_tolerance
                        and recurrence_error < 1e-9 and peak_increase < 1e-6)
    result["dispatch_tolerance_kw"] = dispatch_tolerance
    (folder / "resumen.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("carpeta", type=Path)
    args = p.parse_args()
    result = analyze(args.carpeta)
    print(f"Resultados: {args.carpeta}")
    print("Ensayo verificado." if result["passed"] else "Ensayo terminado; revisar el reparto final en resumen.json.")
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
