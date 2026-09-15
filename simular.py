"""Simulacion sin red; evalua todas las actualizaciones desde la misma ronda."""
import argparse
import csv
import json
import math
from pathlib import Path

from modelo import Model, advance
from referencia import metrics


def simulate(model, steps=None, output=None, sample_every=10):
    steps = steps or model.steps
    x = model.initial()
    peak_balance, peak_bound, peak_cost_increase = 0.0, 0.0, 0.0
    previous_cost = model.cost(x)
    stream = None
    if output:
        output = Path(output)
        output.mkdir(parents=True, exist_ok=True)
        stream = (output / "serie.csv").open("w", newline="", encoding="utf-8")
        writer = csv.writer(stream)
        writer.writerow(["round"] + [f"x_{i}" for i in model.ids] + ["balance_error_kw", "cost"])
    try:
        for k in range(steps + 1):
            balance = math.fsum(x.values()) - model.demand
            cost = model.cost(x)
            peak_balance = max(peak_balance, abs(balance))
            peak_cost_increase = max(peak_cost_increase, cost - previous_cost)
            peak_bound = max(peak_bound, max(max(p["pmin"] - x[i], x[i] - p["pmax"], 0)
                                           for i, p in model.nodes.items()))
            if stream and (k % sample_every == 0 or k == steps):
                writer.writerow([k] + [x[i] for i in model.ids] + [balance, cost])
            previous_cost = cost
            if k < steps:
                x = advance(model, x)
        result = metrics(model, x)
        result.update(steps=steps, alpha=model.alpha, max_balance_error_kw=peak_balance,
                      max_bound_violation_all_kw=peak_bound, max_cost_increase=peak_cost_increase)
        if output:
            (output / "resumen.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            (output / "config.json").write_text(json.dumps(model.config, indent=2) + "\n", encoding="utf-8")
        return result
    finally:
        if stream:
            stream.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", required=True)
    p.add_argument("--pasos", type=int)
    p.add_argument("--salida", type=Path, default=Path("resultados/simulacion"))
    args = p.parse_args()
    if args.pasos is not None and args.pasos <= 0:
        p.error("pasos debe ser positivo")
    result = simulate(Model.load(args.config), args.pasos, args.salida)
    print(f"Simulacion terminada. Resultados: {args.salida}")
    if result["max_dispatch_error_kw"] >= .01:
        print("El reparto final no alcanza el optimo; ver nota de topologias en README.md.")


if __name__ == "__main__":
    main()
