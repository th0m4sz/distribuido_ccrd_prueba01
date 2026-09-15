"""Ejemplos trazables a Tabla 1, notas_documento_base.pdf, pagina PDF 20."""
import argparse
import json
from pathlib import Path

TABLE = [
    (100, 500, 64.67, 795.5, 1.15), (82, 362, 65.46, 1448.6, .82),
    (65, 315, 190.92, 838.1, 1.53), (50, 271, 39.19, 696.1, 2.46),
    (0, 60, 104.44, 1150.5, 0), (20, 260, 28.77, 903.2, .71),
]


def make_config(n=4, topology="anillo", local=False):
    ids = list(range(1, n + 1))
    if n not in (4, 6):
        raise ValueError("El generador de ejemplos ofrece 4 o 6; el motor admite mas nodos")
    if topology == "estrella":
        edges = [[1, j] for j in ids[1:]]
    elif topology == "anillo":
        edges = [[i, i + 1] for i in ids[:-1]] + [[1, n]]
    else:
        raise ValueError("Elegir anillo o estrella")
    initial = [150, 300, 100, 250] if n == 4 else [300, 250, 200, 200, 40, 160]
    # ID del generador != numero fisico de la placa. Placas disponibles: 2, 4, 5, 6.
    physical_boards = [2, 4, 5, 6] if n == 4 else ids
    nodes = []
    for i, row in enumerate(TABLE[:n], 1):
        lo, hi, a, b, c = row
        nodes.append(dict(id=i, host="127.0.0.1" if local else f"pi-{physical_boards[i - 1]}.local",
                          port=5100 + i if local else 5100,
                          pmin=lo, pmax=hi, a=a, b=b, c=c, x0=initial[i - 1]))
    return dict(version=1, description=f"{n} DG, {topology}; datos Tabla 1, DRE 2019",
                demand_kw=sum(initial), fitness_offset=3000, step_safety=.8,
                steps=3000, period_s=.01, nodes=nodes, edges=edges)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--nodos", type=int, choices=(4, 6), default=4)
    p.add_argument("--topologia", choices=("anillo", "estrella"), default="anillo")
    p.add_argument("--local", action="store_true")
    p.add_argument("--salida", type=Path, required=True)
    args = p.parse_args()
    config = make_config(args.nodos, args.topologia, args.local)
    from modelo import Model
    Model(config)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(args.salida)


if __name__ == "__main__":
    main()
