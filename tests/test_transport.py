import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from herdr_next_to_current.client import Client, ClientError


class Transport(unittest.TestCase):
    def exchange(self, reply, *, mutation=False, limit=1024, timeout=0.1):
        with tempfile.TemporaryDirectory(prefix="hntc-") as directory:
            path = str(Path(directory) / "api.sock")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(path)
                server.listen(1)

                def serve():
                    connection, _ = server.accept()
                    with connection:
                        request = json.loads(connection.makefile("rb").readline())
                        try:
                            reply(connection, request)
                        except (BrokenPipeError, ConnectionResetError):
                            pass

                thread = threading.Thread(target=serve)
                thread.start()
                try:
                    return Client(path, timeout=timeout, max_response=limit).call(
                        "workspace.create", {}, "workspace_created", mutation=mutation
                    )
                finally:
                    thread.join(timeout=1)
                    self.assertFalse(thread.is_alive())

    def test_fragmented_response(self):
        def reply(connection, request):
            data = json.dumps(
                {"id": request["id"], "result": {"type": "workspace_created"}}
            ).encode()
            for chunk in (data[:9], data[9:], b"\n"):
                connection.sendall(chunk)

        self.assertEqual(self.exchange(reply)["type"], "workspace_created")

    def test_malformed_responses_mark_sent_mutation_uncertain(self):
        for wire in (
            b"not json\n",
            b"[]\n",
            b'{"id":"wrong","result":{}}\n',
            b"x" * 1025,
            b'{"id":',
            b'{"id":"wrong","error":null}\n',
        ):
            with self.subTest(wire=wire[:30]), self.assertRaises(ClientError) as caught:
                self.exchange(lambda c, r, wire=wire: c.sendall(wire), mutation=True)
            self.assertTrue(caught.exception.uncertain)

    def test_wrong_result_type(self):
        def reply(connection, request):
            connection.sendall(
                json.dumps({"id": request["id"], "result": {"type": "pong"}}).encode() + b"\n"
            )

        with self.assertRaises(ClientError) as caught:
            self.exchange(reply, mutation=True)
        self.assertTrue(caught.exception.uncertain)

    def test_definitive_server_rejection(self):
        def reply(connection, request):
            connection.sendall(
                json.dumps(
                    {"id": request["id"], "error": {"code": "denied", "message": "blocked"}}
                ).encode()
                + b"\n"
            )

        with self.assertRaises(ClientError) as caught:
            self.exchange(reply, mutation=True)
        self.assertFalse(caught.exception.uncertain)

    def test_response_deadline(self):
        def reply(connection, request):
            for _ in range(30):
                connection.sendall(b" ")
                time.sleep(0.01)

        start = time.monotonic()
        with self.assertRaises(ClientError) as caught:
            self.exchange(reply, mutation=True, timeout=0.05)
        self.assertTrue(caught.exception.uncertain)
        self.assertLess(time.monotonic() - start, 0.5)

    def test_connect_failure_is_safe_before_mutation(self):
        with self.assertRaises(ClientError) as caught:
            Client("/nonexistent/herdr-test.sock").call(
                "workspace.create", {}, "workspace_created", mutation=True
            )
        self.assertFalse(caught.exception.uncertain)
