"""TCP JSON por lineas, snapshots inmutables por ronda, sin coordinador."""
import json
import socket
import socketserver
import threading
import time

MAX_LINE = 8192


class ProtocolError(RuntimeError):
    """Indica que un mensaje recibido no cumple las reglas del protocolo."""
    pass


def encode(message):
    """Convierte un diccionario de Python en una linea JSON para enviarla."""
    return (json.dumps(message, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def read_message(stream):
    """Lee una linea recibida y la convierte nuevamente en diccionario."""
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
    """Guarda los estados recientes que esta placa ofrece a sus vecinos."""

    def __init__(self, model, node_id, run_id):
        self.model, self.node_id, self.run_id = model, node_id, run_id

        # Varios vecinos pueden preguntar al mismo tiempo; el candado evita choques.
        self.lock = threading.Lock()
        self.history = {}
        self.failed = None

    def publish(self, k, state):
        """Publica el estado de esta placa para la ronda k."""
        with self.lock:
            self.history[k] = dict(state)
            # Vecinos adyacentes difieren como maximo una ronda. Retenemos margen.
            for old in list(self.history):
                if old < k - 2:
                    del self.history[old]

    def fail(self, message):
        """Marca el nodo como fallido para avisar a sus vecinos."""
        with self.lock:
            self.failed = message

    def respond(self, request):
        """Construye la respuesta a la solicitud de un vecino."""
        with self.lock:
            # Rechazar placas que ejecuten otro ensayo o configuracion.
            if (request.get("protocol") != 1 or request.get("config") != self.model.fingerprint
                    or request.get("run") != self.run_id):
                return {"status": "error", "reason": "Configuracion, protocolo o run-id diferente"}

            # Solo un vecino declarado en la topologia puede pedir datos.
            sender = request.get("from")
            if type(sender) is not int or sender not in self.model.neighbors[self.node_id]:
                return {"status": "error", "reason": "Solicitante no es vecino"}
            k = request.get("round")
            if type(k) is not int or k < 0:
                return {"status": "error", "reason": "Ronda invalida"}

            # Informar si este nodo ya se detuvo por un error.
            if self.failed:
                return {"status": "error", "reason": "Nodo detenido: " + self.failed}

            # Entregar el estado si la ronda solicitada ya esta disponible.
            if k in self.history:
                return {"status": "ok", "protocol": 1, "run": self.run_id,
                        "config": self.model.fingerprint, "node": self.node_id,
                        "round": k, "state": self.history[k]}
            if self.history and k < min(self.history):
                return {"status": "error", "reason": "Ronda expirada; reiniciar TODOS con otro run-id"}

            # El vecino debe volver a preguntar porque esta placa aun no llega a k.
            return {"status": "wait"}


class PeerServer(socketserver.ThreadingTCPServer):
    """Servidor TCP que puede atender a varios vecinos simultaneamente."""
    allow_reuse_address = True
    daemon_threads = True


class Handler(socketserver.StreamRequestHandler):
    """Atiende una conexion entrante de otra placa."""

    def handle(self):
        self.connection.settimeout(5)
        try:
            while True:
                # Leer solicitud, buscar la respuesta y devolverla por TCP.
                request = read_message(self.rfile)
                self.wfile.write(encode(self.server.store.respond(request)))
                self.wfile.flush()
        except (OSError, EOFError, ValueError, ProtocolError):
            return


def serve(store, bind="0.0.0.0"):
    """Inicia en segundo plano el servidor de esta placa."""
    # Cada placa escucha en el host y puerto definidos para su nodo.
    address = (bind, store.model.nodes[store.node_id]["port"])
    server = PeerServer(address, Handler)
    server.store = store

    # El hilo permite que nodo.py siga calculando mientras el servidor responde.
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
    thread.start()
    return server


class PeerClient:
    """Cliente usado por esta placa para consultar a uno de sus vecinos."""

    def __init__(self, model, own_id, peer_id, run_id):
        self.model, self.own_id, self.peer_id, self.run_id = model, own_id, peer_id, run_id

        # Direccion .local y puerto del vecino.
        p = model.nodes[peer_id]
        self.address = (p["host"], p["port"])
        self.sock = self.stream = None

    def close(self):
        """Cierra la conexion actual con el vecino."""
        if self.stream:
            self.stream.close()
        if self.sock:
            self.sock.close()
        self.stream = self.sock = None

    def fetch(self, k, timeout):
        """Solicita al vecino su estado de la ronda k y espera hasta recibirlo."""
        deadline = time.monotonic() + timeout
        last_error = "el vecino aun no publica la ronda"

        # La solicitud identifica ensayo, configuracion, remitente y ronda.
        request = {"protocol": 1, "config": self.model.fingerprint, "run": self.run_id,
                   "from": self.own_id, "round": k}
        while time.monotonic() < deadline:
            try:
                remaining = max(.001, deadline - time.monotonic())
                if self.sock is None:
                    # Abrir la conexion TCP la primera vez o despues de un corte.
                    self.sock = socket.create_connection(self.address, timeout=min(1, remaining))
                    self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    self.stream = self.sock.makefile("rb")
                self.sock.settimeout(min(1, remaining))
                self.sock.sendall(encode(request))
                reply = read_message(self.stream)

                # Un error remoto detiene el ensayo para no mezclar datos incorrectos.
                if reply.get("status") == "error":
                    raise ProtocolError(f"Vecino {self.peer_id}: {reply.get('reason')}")
                if reply.get("status") == "ok":
                    # Confirmar que la respuesta pertenece al vecino y ronda esperados.
                    if (reply.get("protocol") != 1 or reply.get("config") != self.model.fingerprint
                            or reply.get("run") != self.run_id or reply.get("node") != self.peer_id
                            or type(reply.get("round")) is not int or reply["round"] != k):
                        raise ProtocolError("Identidad o ronda de respuesta incorrecta")
                    try:
                        # Recalcular hat y fitness para detectar un estado incoherente.
                        return self.model.check_state(self.peer_id, reply["state"])
                    except (KeyError, TypeError, ValueError) as exc:
                        raise ProtocolError("Estado remoto invalido") from exc
                if reply.get("status") != "wait":
                    raise ProtocolError("Respuesta desconocida")
            except (OSError, EOFError) as exc:
                # Si se corta la conexion, cerrarla e intentar nuevamente.
                last_error = str(exc)
                self.close()
            except (ValueError, KeyError, TypeError) as exc:
                raise ProtocolError("JSON remoto invalido") from exc
            time.sleep(.005)

        # No se recibio el estado antes de agotar el tiempo permitido.
        raise TimeoutError(f"Vecino {self.peer_id}, ronda {k}: {last_error}")
