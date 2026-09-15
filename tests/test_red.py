import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import unittest
import uuid
from contextlib import contextmanager
import shutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from crear_config import make_config
from modelo import Model
from red import ProtocolError, SnapshotStore, read_message


@contextmanager
def scratch_directory():
    # mkdir normal hereda los permisos del workspace en Windows.
    root = (ROOT / "tmp").resolve()
    root.mkdir(exist_ok=True)
    folder = root / ("test_" + uuid.uuid4().hex)
    folder.mkdir()
    try:
        yield folder
    finally:
        target = folder.resolve()
        if target.parent != root or not target.name.startswith("test_"):
            raise RuntimeError("Ruta temporal fuera del workspace")
        shutil.rmtree(target)


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.model = Model(make_config())
        self.store = SnapshotStore(self.model, 1, "test")
        self.store.publish(0, self.model.state(1, 150))
        self.request = dict(protocol=1, config=self.model.fingerprint, run="test", **{"from": 2, "round": 0})

    def test_repeated_requests_are_idempotent_and_old_snapshots_immutable(self):
        first = self.store.respond(self.request)
        self.store.publish(1, self.model.state(1, 151))
        self.assertEqual(first, self.store.respond(self.request))
        self.assertEqual(first["state"]["x"], 150)

    def test_future_waits_and_stale_round_fails(self):
        self.assertEqual(self.store.respond(dict(self.request, round=1))["status"], "wait")
        for k in range(1, 5):
            self.store.publish(k, self.model.state(1, 150+k))
        self.assertEqual(self.store.respond(self.request)["status"], "error")

    def test_wrong_run_config_neighbor_and_invalid_numbers(self):
        for fields in ({"run": "old"}, {"config": "wrong"}, {"from": 3}, {"round": True}, {"round": -1}):
            self.assertEqual(self.store.respond(dict(self.request, **fields))["status"], "error")
        for value in (float("inf"), float("nan"), 900):
            with self.assertRaises(ValueError):
                self.model.check_state(2, dict(x=value, hat=1, fitness=1))

    def test_failure_propagates(self):
        self.store.fail("enlace perdido")
        self.assertEqual(self.store.respond(self.request)["status"], "error")

    def test_framing(self):
        stream = io.BytesIO(b'{"a":1}\n{"b":2}\n')
        self.assertEqual(read_message(stream), {"a":1})
        self.assertEqual(read_message(stream), {"b":2})
        with self.assertRaises(ProtocolError):
            read_message(io.BytesIO(b"x" * 9000))
        with self.assertRaises(ProtocolError):
            read_message(io.BytesIO(b"[]\n"))

    def test_missing_neighbor_stops_node_without_updating(self):
        # Puertos efimeros reservados durante seleccion; no existe servidor vecino.
        with scratch_directory() as temp:
            folder = Path(temp)
            c = make_config(4, "anillo", True)
            sockets = []
            try:
                for p in c["nodes"]:
                    s = socket.socket()
                    s.bind(("127.0.0.1", 0))
                    p["port"] = s.getsockname()[1]
                    sockets.append(s)
            finally:
                for s in sockets:
                    s.close()
            c["steps"] = 2
            path = folder / "config.json"
            path.write_text(json.dumps(c), encoding="utf-8")
            result = subprocess.run([sys.executable, str(ROOT / "nodo.py"), "--config", str(path),
                                     "--id", "1", "--run-id", "missing", "--salida", str(folder),
                                     "--startup-timeout", ".2", "--timeout", ".2", "--grace", ".2",
                                     "--bind", "127.0.0.1"], capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 1, result.stderr)
            meta = json.loads((folder / "nodo_1.json").read_text())
            self.assertEqual(meta["status"], "failed")
            self.assertEqual(meta["completed_rounds"], 0)
            self.assertEqual(meta["x_final"], 150)


if __name__ == "__main__":
    unittest.main()
