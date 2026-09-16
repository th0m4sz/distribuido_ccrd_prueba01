"""CCRD entre vecinos. Nucleo compartido por simulador y nodos (solo stdlib)."""
import hashlib
import json
import math
from pathlib import Path


# Comprueba que un dato sea un numero valido (no infinito ni NaN).
def finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name}: se requiere un numero finito")
    return float(value)


# Comprueba que un dato sea un numero entero mayor o igual al minimo indicado.
def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name}: se requiere entero >= {minimum}")
    return value


class Model:
    """Guarda la configuracion y aplica las ecuaciones del algoritmo."""

    def __init__(self, config):
        # Guardamos la configuracion completa para incluirla luego en los resultados.
        self.config = config

        # Solo conocemos el formato numero 1 de los archivos JSON.
        if config.get("version") != 1:
            raise ValueError("Version de configuracion no soportada")

        # Parametros generales del experimento.
        self.demand = finite(config["demand_kw"], "demand_kw")
        self.B = finite(config.get("fitness_offset", 3000.0), "fitness_offset")
        self.steps = integer(config.get("steps", 10000), "steps", 1)
        self.period = finite(config.get("period_s", 0.01), "period_s")
        if self.period < 0:
            raise ValueError("period_s debe ser >= 0")
        # Leer y validar los datos de cada generador.
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

        # Lista ordenada de identificadores: [1, 2, 3, ...].
        self.ids = sorted(self.nodes)

        # Crear la lista de vecinos a partir de las conexiones del JSON.
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

        # Recorrer la red para comprobar que ningun nodo quede aislado.
        seen, pending = set(), [self.ids[0]]
        while pending:
            i = pending.pop()
            if i not in seen:
                seen.add(i)
                pending.extend(self.neighbors[i])
        if seen != set(self.ids):
            raise ValueError("El grafo debe ser conexo")

        # La demanda debe poder cubrirse respetando los limites de potencia.
        lo = sum(p["pmin"] for p in self.nodes.values())
        hi = sum(p["pmax"] for p in self.nodes.values())
        if not lo < self.demand < hi:
            raise ValueError("Demanda no factible en el interior de los limites")
        if abs(math.fsum(p["x0"] for p in self.nodes.values()) - self.demand) > 1e-8:
            raise ValueError("La suma de x0 debe coincidir con la demanda; este mix no recupera desbalances")

        # Calcular automaticamente un alpha pequeno y conservador.
        # step_safety=0.8 significa usar el 80 % de la cota calculada.
        eta = finite(config.get("step_safety", 0.8), "step_safety")
        if not 0 < eta < 1:
            raise ValueError("step_safety debe estar entre 0 y 1")
        self.alpha_limit = self.safe_step_bound()
        self.alpha = finite(config.get("alpha", eta * self.alpha_limit), "alpha")
        if not 0 < self.alpha <= eta * self.alpha_limit:
            raise ValueError("alpha excede la cota conservadora de limites y descenso de costo")

        # Huella unica de la configuracion. Todos los nodos deben tener la misma.
        self.fingerprint = hashlib.sha256(json.dumps(config, sort_keys=True, allow_nan=False,
                                                     separators=(",", ":")).encode()).hexdigest()

    @classmethod
    def load(cls, path):
        """Lee un JSON y construye el modelo."""
        return cls(json.loads(Path(path).read_text(encoding="utf-8-sig")))

    def fitness(self, i, x):
        """Calcula f_i = B - (b_i + 2*c_i*x_i)."""
        p = self.nodes[i]
        return self.B - p["b"] - 2 * p["c"] * x

    def hat(self, i, x):
        """Calcula el factor que reduce el movimiento cerca de Pmin y Pmax."""
        p = self.nodes[i]
        return (x - p["pmin"]) * (p["pmax"] - x)

    def state(self, i, x):
        """Construye el mensaje local: potencia, factor de capacidad y fitness."""
        x = finite(x, "x")
        p = self.nodes[i]
        if not p["pmin"] <= x <= p["pmax"]:
            raise ValueError(f"Nodo {i}: potencia fuera de limites, x={x}")
        return {"x": x, "hat": self.hat(i, x), "fitness": self.fitness(i, x)}

    def check_state(self, i, state):
        """Comprueba que el estado recibido de un vecino sea coherente."""
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
        # Calculamos por separado el intercambio de potencia con cada vecino.
        # Ambos extremos usan el mismo valor, pero con signo contrario. Asi, lo que
        # gana un nodo lo pierde el otro y la potencia total se conserva.
        flows = []
        for j, weight in sorted(self.neighbors[i].items()):
            # Ordenar los extremos evita pequeñas diferencias numericas entre placas.
            left, right = (own, peers[j]) if i < j else (peers[j], own)

            # Ecuacion distribuida para una conexion entre dos nodos.
            flow = self.alpha * weight * left["hat"] * right["hat"] * (left["fitness"] - right["fitness"])
            flows.append(flow if i < j else -flow)

        # Sumar todos los intercambios a la potencia actual.
        new_x = own["x"] + math.fsum(flows)

        # Si la nueva potencia viola un limite, detener el ensayo y mostrar el error.
        self.state(i, new_x)  # Rechazo explicito: no recortar x ni alterar el balance.
        return new_x

    def safe_step_bound(self):
        """Cota suficiente global, calculada una vez a partir de parametros estaticos."""
        # Ancho del intervalo permitido para cada generador.
        width = {i: p["pmax"] - p["pmin"] for i, p in self.nodes.items()}

        # Valor maximo posible de hat dentro de ese intervalo.
        hmax = {i: width[i] ** 2 / 4 for i in self.ids}
        max_box_rate, max_degree = 0.0, 0.0
        for i in self.ids:
            # Fitness del nodo i en ambos extremos de su intervalo.
            fi = [self.fitness(i, self.nodes[i][k]) for k in ("pmin", "pmax")]
            rate, degree = 0.0, 0.0
            for j, w in self.neighbors[i].items():
                # Buscar la mayor diferencia de fitness posible con el vecino j.
                fj = [self.fitness(j, self.nodes[j][k]) for k in ("pmin", "pmax")]
                delta_f = max(abs(a - b) for a in fi for b in fj)
                rate += w * hmax[j] * delta_f
                degree += w * hmax[i] * hmax[j]
            max_box_rate = max(max_box_rate, width[i] * rate)
            max_degree = max(max_degree, degree)
        cmax = max(p["c"] for p in self.nodes.values())
        denominator = max(max_box_rate, 2 * cmax * max_degree)

        # Cuanto mayor puede ser la actualizacion, menor debe ser alpha.
        return 1.0 / denominator if denominator > 0 else 1.0

    def initial(self):
        """Devuelve las potencias iniciales configuradas."""
        return {i: self.nodes[i]["x0"] for i in self.ids}

    def cost(self, x):
        """Calcula la suma de los costos cuadraticos de todos los generadores."""
        return math.fsum(p["a"] + p["b"] * x[i] + p["c"] * x[i] ** 2
                         for i, p in self.nodes.items())


def advance(model, x):
    """Avanza una ronda completa en la simulacion ejecutada en un solo PC."""
    # Primero se toma una fotografia de todos los estados en la ronda actual.
    states = {i: model.state(i, x[i]) for i in model.ids}

    # Despues todos calculan la ronda siguiente usando esa misma fotografia.
    return {i: model.local_step(i, states[i], {j: states[j] for j in model.neighbors[i]})
            for i in model.ids}
