"""Potencias individuales, fitness y potencia total frente a iteraciones."""
import argparse
import csv
import json
import math
from pathlib import Path


def plot(folder):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise SystemExit("Graficas opcionales: instalar matplotlib en el computador de analisis") from exc
    from modelo import Model

    folder = Path(folder)
    config_path = folder / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
    else:
        first = next(folder.glob("nodo_*.json"))
        config = json.loads(first.read_text(encoding="utf-8"))["config"]
    model = Model(config)
    if list(folder.glob("nodo_*.csv")):
        from analizar import analyze
        analyze(folder)
    with (folder / "serie.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    rounds = [int(r["round"]) for r in rows]
    fig, axes = plt.subplots(3, 1, figsize=(9, 10), constrained_layout=True)
    colors = ["#0072b2", "#d55e00", "#009e73", "#cc79a7", "#e69f00", "#56b4e9"]
    for pos, i in enumerate(model.ids):
        xs = [float(r[f"x_{i}"]) for r in rows]
        color = colors[pos % len(colors)]
        axes[0].plot(rounds, xs, label=f"G{i}", color=color, lw=1.8)
        axes[1].plot(rounds, [model.fitness(i, x) for x in xs], label=f"G{i}", color=color, lw=1.8)
    axes[0].set(title="Potencia de los generadores", ylabel="Potencia (kW)")
    axes[1].set(title="Fitness de los generadores", ylabel="Fitness")
    totals = [math.fsum(float(r[f"x_{i}"]) for i in model.ids) for r in rows]
    axes[2].plot(rounds, totals, color="#0072b2", lw=2.5, label="Suma de las potencias")
    axes[2].axhline(model.demand, color="#d55e00", ls="--", lw=1.8,
                   label=f"Demanda: {model.demand:g} kW")
    lower, upper = min(min(totals), model.demand), max(max(totals), model.demand)
    margin = max(1.0, .01 * abs(model.demand), .1 * (upper - lower))
    axes[2].set_ylim(lower - margin, upper + margin)
    axes[2].ticklabel_format(axis="y", style="plain", useOffset=False)
    axes[2].set(title="Suma de todas las potencias y demanda", ylabel="Potencia total (kW)")
    for ax in axes.flat:
        ax.set_xlabel("Iteraciones")
        ax.grid(alpha=.18)
        ax.legend(ncol=len(model.ids), fontsize=9)
    path = folder / "trayectorias.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    print(path)
    return path


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--carpeta", required=True, type=Path)
    plot(p.parse_args().carpeta)
