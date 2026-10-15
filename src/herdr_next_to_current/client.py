"""Bounded, one-request Unix socket transport for Herdr 0.9.3."""

import json
import socket
import time
import uuid


class ClientError(Exception):
    def __init__(self, message: str, *, uncertain: bool = False):
        super().__init__(message)
        self.uncertain = uncertain


class Client:
    def __init__(self, path: str, *, timeout: float = 3.0, max_response: int = 4 * 1024 * 1024):
        self.path = path
        self.timeout = timeout
        self.max_response = max_response

    def call(self, method: str, params: dict, expected: str, *, mutation: bool = False) -> dict:
        request_id = uuid.uuid4().hex
        wire = json.dumps({"id": request_id, "method": method, "params": params}).encode() + b"\n"
        sent = False
        try:
            deadline = time.monotonic() + self.timeout
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(self.timeout)
                connection.connect(self.path)
                # sendall can fail after sending part or all of the request.
                sent = True
                connection.sendall(wire)
                data = bytearray()
                while b"\n" not in data:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("response deadline exceeded")
                    connection.settimeout(remaining)
                    chunk = connection.recv(min(65536, self.max_response + 1 - len(data)))
                    if not chunk:
                        raise ValueError("connection closed before a complete response")
                    data.extend(chunk)
                    if len(data) > self.max_response:
                        raise ValueError("response exceeds size limit")
                response = json.loads(data.split(b"\n", 1)[0])
            if not isinstance(response, dict) or response.get("id") != request_id:
                raise ValueError("response request ID does not match")
            if "error" in response:
                error = response["error"]
                if not isinstance(error, dict) or not isinstance(error.get("message"), str):
                    raise ValueError("malformed server error")
                raise ClientError(f"{method}: {error.get('code')}: {error['message']}")
            result = response.get("result")
            if not isinstance(result, dict) or result.get("type") != expected:
                raise ValueError(f"expected result type {expected}")
            return result
        except ClientError:
            raise
        except (OSError, ValueError, RecursionError) as error:
            raise ClientError(
                f"{method} on {self.path}: {error}", uncertain=mutation and sent
            ) from error

    def validate(self) -> None:
        metadata = self.call("ping", {}, "pong")
        # Protocol 22 / release 0.9.3 defines all operations and the sidebar projection we use.
        if metadata.get("version") != "0.9.3" or metadata.get("protocol") != 22:
            raise ClientError("unsupported Herdr server; expected version 0.9.3, protocol 22")
