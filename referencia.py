"""Optimo KKT central SOLO para evaluacion offline; nunca lo importa nodo.py."""
import math


def economic_dispatch(model):
    def allocation(price, include_equal=False):
        result = {}
        for i, p in model.nodes.items():
            if p["c"] > 0:
                x = (price - p["b"]) / (2 * p["c"])
                result[i] = max(p["pmin"], min(p["pmax"], x))
            else:
                on = price > p["b"] or (include_equal and price == p["b"])
                result[i] = p["pmax"] if on else p["pmin"]
        return result

    # Un costo lineal (DG5 de la Tabla 1) produce un salto en la curva de oferta.
    for price in sorted({p["b"] for p in model.nodes.values() if p["c"] == 0}):
        x, high = allocation(price), allocation(price, True)
        if math.fsum(x.values()) <= model.demand <= math.fsum(high.values()):
            rest = model.demand - math.fsum(x.values())
            for i, p in model.nodes.items():
                if p["c"] == 0 and p["b"] == price:
                    delta = min(rest, p["pmax"] - x[i])
                    x[i] += delta
                    rest -= delta
            return x, price
    lo = min(p["b"] + 2 * p["c"] * p["pmin"] for p in model.nodes.values()) - 1
    hi = max(p["b"] + 2 * p["c"] * p["pmax"] for p in model.nodes.values()) + 1
    for _ in range(120):
        price = (lo + hi) / 2
        if math.fsum(allocation(price).values()) < model.demand:
            lo = price
        else:
            hi = price
    price = (lo + hi) / 2
    return allocation(price), price


def metrics(model, x):
    optimum, price = economic_dispatch(model)
    kkt = []
    for i, p in model.nodes.items():
        marginal = p["b"] + 2 * p["c"] * x[i]
        if x[i] <= p["pmin"] + 1e-5:
            kkt.append(max(0, price - marginal))
        elif x[i] >= p["pmax"] - 1e-5:
            kkt.append(max(0, marginal - price))
        else:
            kkt.append(abs(marginal - price))
    return {"generation_kw": math.fsum(x.values()),
            "balance_error_kw": math.fsum(x.values()) - model.demand,
            "max_dispatch_error_kw": max(abs(x[i] - optimum[i]) for i in model.ids),
            "cost": model.cost(x), "optimal_cost": model.cost(optimum),
            "cost_gap": model.cost(x) - model.cost(optimum),
            "kkt_residual": max(kkt), "lambda_reference": price,
            "x_final": x, "x_reference": optimum}
