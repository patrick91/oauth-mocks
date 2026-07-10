from __future__ import annotations

import os
import signal
import socket
import threading

import pytest

from oauth_mocks import _runner


def test_startup_failure_stops_the_cli() -> None:
    with socket.socket() as occupied_socket:
        occupied_socket.bind(("127.0.0.1", 0))
        occupied_socket.listen()
        port = occupied_socket.getsockname()[1]

        assert (
            _runner.serve_providers(["github"], host="127.0.0.1", base_port=port) == 1
        )


def test_signal_during_startup_stops_servers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SlowStartingServer:
        def __init__(self, provider: _runner.Provider, host: str, port: int) -> None:
            self.provider = provider
            self.host = host
            self.port = port
            self.started = False
            self.is_alive = True
            self.error: BaseException | None = None

        def start(self) -> None:
            pass

        def stop(self, *, force: bool = False) -> None:
            del force
            self.is_alive = False

        def join(self, timeout: float | None = None) -> None:
            del timeout

    monkeypatch.setattr(_runner, "_ServerThread", SlowStartingServer)
    timer = threading.Timer(0.05, lambda: os.kill(os.getpid(), signal.SIGTERM))
    timer.start()

    try:
        assert (
            _runner.serve_providers(["github"], host="127.0.0.1", base_port=9001) == 0
        )
    finally:
        timer.cancel()
        timer.join()
