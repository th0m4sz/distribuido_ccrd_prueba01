"""TCP JSON por lineas, snapshots inmutables por ronda, sin coordinador."""
import json
import socket
import socketserver
import threading
import time

MAX_LINE = 8192


class ProtocolError(RuntimeError):
    pass


def encode(message):
    return (json.dumps(message, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def read_message(stream):
    line = stream.readline(MAX_LINE + 1)
    if not line:
        raise EOFError("Conexion cerrada")
    if len(line) > MAX_LINE or not line.endswith(b"\n"):
        raise ProtocolError("Mensaje demasiado largo o sin delimitador")
    message = json.loads(line)
    if not isinstance(message, dict):
        raise ProtocolError("Se esperaba objeto JSON")
    return message


class SnapshotStore:
    def __init__(self, model, node_id, run_id):
        self.model, self.node_id, self.run_id = model, node_id, run_id
        self.lock = threading.Lock()
        self.history = {}
        self.failed = None

    def publish(self, k, state):
        with self.lock:
            self.history[k] = dict(state)
            # Vecinos adyacentes difieren como maximo una ronda. Retenemos margen.
            for old in list(self.history):
                if old < k - 2:
                    del self.history[old]

    def fail(self, message):
        with self.lock:
            self.failed = message

    def respond(self, request):
        with self.lock:
            if (request.get("protocol") != 1 or request.get("config") != self.model.fingerprint
                    or request.get("run") != self.run_id):
                return {"status": "error", "reason": "Configuracion, protocolo o run-id diferente"}
            sender = request.get("from")
            if type(sender) is not int or sender not in self.model.neighbors[self.node_id]:
                return {"status": "error", "reason": "Solicitante no es vecino"}
            k = request.get("round")
            if type(k) is not int or k < 0:
                return {"status": "error", "reason": "Ronda invalida"}
            if self.failed:
                return {"status": "error", "reason": "Nodo detenido: " + self.failed}
            if k in self.history:
                return {"status": "ok", "protocol": 1, "run": self.run_id,
                        "config": self.model.fingerprint, "node": self.node_id,
                        "round": k, "state": self.history[k]}
            if self.history and k < min(self.history):
                return {"status": "error", "reason": "Ronda expirada; reiniciar TODOS con otro run-id"}
            return {"status": "wait"}


class PeerServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(5)
        try:
            while True:
                request = read_message(self.rfile)
                self.wfile.write(encode(self.server.store.respond(request)))
                self.wfile.flush()
        except (OSError, EOFError, ValueError, ProtocolError):
            return


def serve(store, bind="0.0.0.0"):
    address = (bind, store.model.nodes[store.node_id]["port"])
    server = PeerServer(address, Handler)
    server.store = store
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
    thread.start()
    return server


class PeerClient:
    def __init__(self, model, own_id, peer_id, run_id):
        self.model, self.own_id, self.peer_id, self.run_id = model, own_id, peer_id, run_id
        p = model.nodes[peer_id]
        self.address = (p["host"], p["port"])
        self.sock = self.stream = None

    def close(self):
        if self.stream:
            self.stream.close()
        if self.sock:
            self.sock.close()
        self.stream = self.sock = None

    def fetch(self, k, timeout):
        deadline = time.monotonic() + timeout
        last_error = "el vecino aun no publica la ronda"
        request = {"protocol": 1, "config": self.model.fingerprint, "run": self.run_id,
                   "from": self.own_id, "round": k}
        while time.monotonic() < deadline:
            try:
                remaining = max(.001, deadline - time.monotonic())
                if self.sock is None:
                    self.sock = socket.create_connection(self.address, timeout=min(1, remaining))
                    self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    self.stream = self.sock.makefile("rb")
                self.sock.settimeout(min(1, remaining))
                self.sock.sendall(encode(request))
                reply = read_message(self.stream)
                if reply.get("status") == "error":
                    raise ProtocolError(f"Vecino {self.peer_id}: {reply.get('reason')}")
                if reply.get("status") == "ok":
                    if (reply.get("protocol") != 1 or reply.get("config") != self.model.fingerprint
                            or reply.get("run") != self.run_id or reply.get("node") != self.peer_id
                            or type(reply.get("round")) is not int or reply["round"] != k):
                        raise ProtocolError("Identidad o ronda de respuesta incorrecta")
                    try:
                        return self.model.check_state(self.peer_id, reply["state"])
                    except (KeyError, TypeError, ValueError) as exc:
                        raise ProtocolError("Estado remoto invalido") from exc
                if reply.get("status") != "wait":
                    raise ProtocolError("Respuesta desconocida")
            except (OSError, EOFError) as exc:
                last_error = str(exc)
                self.close()
            except (ValueError, KeyError, TypeError) as exc:
                raise ProtocolError("JSON remoto invalido") from exc
            time.sleep(.005)
        raise TimeoutError(f"Vecino {self.peer_id}, ronda {k}: {last_error}")
