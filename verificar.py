"""Verificacion interna de los cuatro ejemplos, con salida breve."""
from pathlib import Path
from crear_config import make_config
from modelo import Model
from simular import simulate


def main():
    output = Path(__file__).parent / "resultados"
    for n in (4, 6):
        for topology in ("anillo", "estrella"):
            result = simulate(Model(make_config(n, topology)), output=output / f"{n}_{topology}")
            assert abs(result["balance_error_kw"]) < 1e-6
            reached = result["max_dispatch_error_kw"] < .01
            assert reached == (not (n == 6 and topology == "anillo"))
            print(f"{n} nodos, {topology}: " + ("correcto" if reached else "balance conservado; bloqueo por saturacion"))


if __name__ == "__main__":
    main()
