import copy
import math
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crear_config import make_config
from modelo import Model, advance
from referencia import economic_dispatch, metrics
from simular import simulate


class ModelTests(unittest.TestCase):
    def test_feasible_random_states_preserve_mass_bounds_and_cost(self):
        rng = random.Random(12)
        for n in (4, 6):
            m = Model(make_config(n, "estrella"))
            for _ in range(100):
                # Invariantes se verifican para cualquier masa, incluso fuera de demanda.
                x = {i: p["pmin"] + (p["pmax"] - p["pmin"]) * rng.uniform(.000001, .999999)
                     for i, p in m.nodes.items()}
                y = advance(m, x)
                self.assertAlmostEqual(math.fsum(x.values()), math.fsum(y.values()), places=9)
                self.assertLessEqual(m.cost(y), m.cost(x) + 1e-7)
                for i in m.ids:
                    self.assertTrue(m.nodes[i]["pmin"] <= y[i] <= m.nodes[i]["pmax"])

    def test_only_exterior_substitution_does_not_conserve_mass(self):
        m = Model(make_config())
        x = m.initial()
        total = sum(m.hat(i, x[i]) * sum(w * x[j] * (m.fitness(i, x[i]) - m.fitness(j, x[j]))
                    for j, w in m.neighbors[i].items()) for i in m.ids)
        self.assertGreater(abs(total), 1e6)

    def test_no_automatic_balance_recovery(self):
        m = Model(make_config())
        x = m.initial()
        x[1] += 1
        for _ in range(100):
            x = advance(m, x)
        self.assertAlmostEqual(math.fsum(x.values()) - m.demand, 1.0, places=9)

    def test_constant_fitness_offset_cancels(self):
        config = make_config()
        m = Model(config)
        config = copy.deepcopy(config)
        config["fitness_offset"] = -123
        other = Model(config)
        self.assertEqual(m.alpha, other.alpha)
        a, b = advance(m, m.initial()), advance(other, other.initial())
        for i in m.ids:
            self.assertAlmostEqual(a[i], b[i], places=12)

    def test_connected_does_not_imply_optimum_when_saturated(self):
        for n, topology in ((6, "anillo"),):
            r = simulate(Model(make_config(n, topology)), 6000)
            self.assertLess(r["max_balance_error_kw"], 1e-6)
            self.assertGreater(r["max_dispatch_error_kw"], 1)

    def test_recommended_examples_match_reference(self):
        for n, topology in ((4, "anillo"), (6, "estrella")):
            m = Model(make_config(n, topology))
            r = simulate(m, 3000)
            self.assertLess(r["max_dispatch_error_kw"], 1e-5)
            self.assertLess(r["kkt_residual"], 1e-4)

    def test_reference_linear_generator_partial_dispatch(self):
        c = make_config(6, "estrella")
        # Demanda elegida sobre el salto de oferta del generador lineal 5.
        lam = 1150.5
        baseline = []
        for p in c["nodes"]:
            baseline.append(max(p["pmin"], min(p["pmax"], (lam - p["b"]) / (2*p["c"]))) if p["c"] else p["pmin"])
        demand = sum(baseline) + 30
        low = sum(p["pmin"] for p in c["nodes"])
        span = sum(p["pmax"] - p["pmin"] for p in c["nodes"])
        for p in c["nodes"]:
            p["x0"] = p["pmin"] + (p["pmax"] - p["pmin"]) * (demand-low)/span
        c["demand_kw"] = demand
        m = Model(c)
        x, price = economic_dispatch(m)
        self.assertAlmostEqual(price, lam)
        self.assertAlmostEqual(x[5], 30, places=8)
        self.assertAlmostEqual(sum(x.values()), demand)
        self.assertLess(metrics(m, x)["kkt_residual"], 1e-8)

    def test_invalid_config_rejected(self):
        base = make_config()
        mutations = [lambda c: c.update(demand_kw=99999),
                     lambda c: c.update(demand_kw=801),
                     lambda c: c.update(edges=[[1,2], [3,4]]),
                     lambda c: c["edges"].append([2,1]),
                     lambda c: c.update(alpha=1),
                     lambda c: c["nodes"][0].update(x0=100),
                     lambda c: c["nodes"][0].update(c=-1),
                     lambda c: c["nodes"][0].update(x0=float("nan"))]
        for mutate in mutations:
            c = copy.deepcopy(base)
            mutate(c)
            with self.assertRaises(ValueError):
                Model(c)


if __name__ == "__main__":
    unittest.main()
