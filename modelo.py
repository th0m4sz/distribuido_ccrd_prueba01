"""CCRD entre vecinos. Nucleo compartido por simulador y nodos (solo stdlib)."""
import hashlib
import json
import math
from pathlib import Path


def finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name}: se requiere un numero finito")
    return float(value)


def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name}: se requiere entero >= {minimum}")
    return value


class Model:
    def __init__(self, config):
        self.config = config
        if config.get("version") != 1:
            raise ValueError("Version de configuracion no soportada")
        self.demand = finite(config["demand_kw"], "demand_kw")
        self.B = finite(config.get("fitness_offset", 3000.0), "fitness_offset")
        self.steps = integer(config.get("steps", 10000), "steps", 1)
        self.period = finite(config.get("period_s", 0.01), "period_s")
        if self.period < 0:
            raise ValueError("period_s debe ser >= 0")
        self.nodes = {}
        endpoints = set()
        for raw in config["nodes"]:
            p = dict(raw)
            i = integer(p["id"], "id", 1)
            if i in self.nodes:
                raise ValueError("ID repetido")
            for key in ("pmin", "pmax", "a", "b", "c", "x0"):
                p[key] = finite(p.get(key, 0) if key == "a" else p[key], key)
            if not (0 <= p["pmin"] < p["x0"] < p["pmax"]):
                raise ValueError(f"Nodo {i}: requiere 0 <= pmin < x0 < pmax")
            if p["c"] < 0:
                raise ValueError("Costos convexos requieren c >= 0")
            if not isinstance(p["host"], str) or not p["host"].strip():
                raise ValueError("host vacio")
            integer(p["port"], "port", 1)
            if p["port"] > 65535 or (p["host"], p["port"]) in endpoints:
                raise ValueError("Puerto invalido o endpoint repetido")
            endpoints.add((p["host"], p["port"]))
            self.nodes[i] = p
        if len(self.nodes) < 2:
            raise ValueError("Se requieren al menos dos nodos")
        self.ids = sorted(self.nodes)
        self.neighbors = {i: {} for i in self.ids}
        self.edges = []
        for edge in config["edges"]:
            if len(edge) not in (2, 3):
                raise ValueError("Arista: [i, j] o [i, j, peso]")
            i, j = edge[:2]
            integer(i, "extremo", 1)
            integer(j, "extremo", 1)
            w = finite(edge[2] if len(edge) == 3 else 1.0, "peso")
            if i == j or i not in self.nodes or j not in self.nodes or w <= 0:
                raise ValueError("Arista invalida")
            if j in self.neighbors[i]:
                raise ValueError("Arista duplicada (se declara una sola vez, es bidireccional)")
            self.neighbors[i][j] = self.neighbors[j][i] = w
            self.edges.append((min(i, j), max(i, j), w))
        seen, pending = set(), [self.ids[0]]
        while pending:
            i = pending.pop()
            if i not in seen:
                seen.add(i)
                pending.extend(self.neighbors[i])
        if seen != set(self.ids):
            raise ValueError("El grafo debe ser conexo")
        lo = sum(p["pmin"] for p in self.nodes.values())
        hi = sum(p["pmax"] for p in self.nodes.values())
        if not lo < self.demand < hi:
            raise ValueError("Demanda no factible en el interior de los limites")
        if abs(math.fsum(p["x0"] for p in self.nodes.values()) - self.demand) > 1e-8:
            raise ValueError("La suma de x0 debe coincidir con la demanda; este mix no recupera desbalances")
        eta = finite(config.get("step_safety", 0.8), "step_safety")
        if not 0 < eta < 1:
            raise ValueError("step_safety debe estar entre 0 y 1")
        self.alpha_limit = self.safe_step_bound()
        self.alpha = finite(config.get("alpha", eta * self.alpha_limit), "alpha")
        if not 0 < self.alpha <= eta * self.alpha_limit:
            raise ValueError("alpha excede la cota conservadora de limites y descenso de costo")
        self.fingerprint = hashlib.sha256(json.dumps(config, sort_keys=True, allow_nan=False,
                                                     separators=(",", ":")).encode()).hexdigest()

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text(encoding="utf-8-sig")))

    def fitness(self, i, x):
        p = self.nodes[i]
        return self.B - p["b"] - 2 * p["c"] * x

    def hat(self, i, x):
        p = self.nodes[i]
        return (x - p["pmin"]) * (p["pmax"] - x)

    def state(self, i, x):
        x = finite(x, "x")
        p = self.nodes[i]
        if not p["pmin"] <= x <= p["pmax"]:
            raise ValueError(f"Nodo {i}: potencia fuera de limites, x={x}")
        return {"x": x, "hat": self.hat(i, x), "fitness": self.fitness(i, x)}

    def check_state(self, i, state):
        expected = self.state(i, state["x"])
        for key in ("hat", "fitness"):
            value = finite(state[key], key)
            if not math.isclose(value, expected[key], rel_tol=1e-12, abs_tol=1e-9):
                raise ValueError(f"Estado incoherente de nodo {i}: {key}")
        return expected

    def local_step(self, i, own, peers):
        """Usa exclusivamente el estado propio y los vecinos de la MISMA ronda."""
        if set(peers) != set(self.neighbors[i]):
            raise ValueError("Faltan vecinos o se incluyeron nodos ajenos a la topologia")
        # Orden canonico por arista: ambos extremos calculan el mismo flujo y signo opuesto.
        flows = []
        for j, weight in sorted(self.neighbors[i].items()):
            left, right = (own, peers[j]) if i < j else (peers[j], own)
            flow = self.alpha * weight * left["hat"] * right["hat"] * (left["fitness"] - right["fitness"])
            flows.append(flow if i < j else -flow)
        new_x = own["x"] + math.fsum(flows)
        self.state(i, new_x)  # Rechazo explicito: no recortar x ni alterar el balance.
        return new_x

    def safe_step_bound(self):
        """Cota suficiente global, calculada una vez a partir de parametros estaticos."""
        width = {i: p["pmax"] - p["pmin"] for i, p in self.nodes.items()}
        hmax = {i: width[i] ** 2 / 4 for i in self.ids}
        max_box_rate, max_degree = 0.0, 0.0
        for i in self.ids:
            fi = [self.fitness(i, self.nodes[i][k]) for k in ("pmin", "pmax")]
            rate, degree = 0.0, 0.0
            for j, w in self.neighbors[i].items():
                fj = [self.fitness(j, self.nodes[j][k]) for k in ("pmin", "pmax")]
                delta_f = max(abs(a - b) for a in fi for b in fj)
                rate += w * hmax[j] * delta_f
                degree += w * hmax[i] * hmax[j]
            max_box_rate = max(max_box_rate, width[i] * rate)
            max_degree = max(max_degree, degree)
        cmax = max(p["c"] for p in self.nodes.values())
        denominator = max(max_box_rate, 2 * cmax * max_degree)
        return 1.0 / denominator if denominator > 0 else 1.0

    def initial(self):
        return {i: self.nodes[i]["x0"] for i in self.ids}

    def cost(self, x):
        return math.fsum(p["a"] + p["b"] * x[i] + p["c"] * x[i] ** 2
                         for i, p in self.nodes.items())


def advance(model, x):
    states = {i: model.state(i, x[i]) for i in model.ids}
    return {i: model.local_step(i, states[i], {j: states[j] for j in model.neighbors[i]})
            for i in model.ids}
