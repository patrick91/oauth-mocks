from __future__ import annotations

import signal
import sys
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from types import FrameType

import uvicorn

STARTUP_TIMEOUT_SECONDS = 10.0
SHUTDOWN_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True, slots=True)
class Provider:
    name: str
    label: str
    app: str


PROVIDERS: dict[str, Provider] = {
    "github": Provider(
        name="github",
        label="GitHub OAuth mock",
        app="oauth_mocks.github.app:app",
    ),
    "google": Provider(
        name="google",
        label="Google OAuth mock",
        app="oauth_mocks.google.app:app",
    ),
}


@dataclass(slots=True)
class _ServerThread:
    provider: Provider
    host: str
    port: int
    server: uvicorn.Server = field(init=False)
    thread: threading.Thread = field(init=False)
    error: BaseException | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        config = uvicorn.Config(
            app=self.provider.app,
            host=self.host,
            port=self.port,
            log_level="info",
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(
            target=self._serve,
            name=f"oauth-mocks-{self.provider.name}",
            daemon=True,
        )

    @property
    def started(self) -> bool:
        return self.server.started

    @property
    def is_alive(self) -> bool:
        return self.thread.is_alive()

    def start(self) -> None:
        self.thread.start()

    def stop(self, *, force: bool = False) -> None:
        self.server.should_exit = True
        if force:
            self.server.force_exit = True

    def join(self, timeout: float | None = None) -> None:
        if self.thread.ident is not None:
            self.thread.join(timeout)

    def _serve(self) -> None:
        try:
            self.server.run()
        except BaseException as error:
            # Uvicorn reports startup failures such as a port collision with
            # SystemExit. Preserve it so the supervising thread can fail the CLI.
            self.error = error


def _stop_servers(servers: Sequence[_ServerThread], *, force: bool = False) -> None:
    for server in servers:
        server.stop(force=force)


def _join_servers(servers: Sequence[_ServerThread], timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    for server in servers:
        remaining = max(0.0, deadline - time.monotonic())
        server.join(remaining)
    return all(not server.is_alive for server in servers)


def _wait_until_started(
    servers: Sequence[_ServerThread], stop_requested: threading.Event
) -> str | None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        if stop_requested.is_set():
            return None

        if all(server.started for server in servers):
            return None

        for server in servers:
            if server.error is not None:
                return f"{server.provider.label} failed to start: {server.error}"
            if not server.is_alive and not server.started:
                return f"{server.provider.label} stopped before it was ready"

        time.sleep(0.01)

    waiting_for = ", ".join(
        server.provider.name for server in servers if not server.started
    )
    return f"timed out waiting for providers to start: {waiting_for}"


def _print_banner(servers: Sequence[_ServerThread]) -> None:
    print("\noauth-mocks\n")
    for server in servers:
        print(f"  {server.provider.name:<8} http://{server.host}:{server.port}")
    print("\nPress Ctrl+C to stop.\n", flush=True)


def serve_providers(
    provider_names: Sequence[str],
    *,
    host: str,
    base_port: int,
) -> int:
    servers = [
        _ServerThread(PROVIDERS[name], host, base_port + offset)
        for offset, name in enumerate(provider_names)
    ]
    stop_requested = threading.Event()
    signal_count = 0

    def handle_signal(signum: int, frame: FrameType | None) -> None:
        del signum, frame
        nonlocal signal_count
        signal_count += 1
        stop_requested.set()
        if signal_count > 1:
            _stop_servers(servers, force=True)

    handled_signals = (signal.SIGINT, signal.SIGTERM)
    previous_handlers = {
        handled_signal: signal.signal(handled_signal, handle_signal)
        for handled_signal in handled_signals
    }

    exit_code = 0

    try:
        for server in servers:
            server.start()

        startup_error = _wait_until_started(servers, stop_requested)
        if stop_requested.is_set():
            return 0
        if startup_error is not None:
            print(f"oauth-mocks: {startup_error}", file=sys.stderr)
            return 1

        _print_banner(servers)

        while not stop_requested.wait(0.1):
            stopped = [server for server in servers if not server.is_alive]
            if not stopped:
                continue

            for server in stopped:
                detail = f": {server.error}" if server.error is not None else ""
                print(
                    f"oauth-mocks: {server.provider.label} stopped unexpectedly{detail}",
                    file=sys.stderr,
                )
            exit_code = 1
            break
    finally:
        _stop_servers(servers)
        if not _join_servers(servers, SHUTDOWN_TIMEOUT_SECONDS):
            _stop_servers(servers, force=True)
            _join_servers(servers, 1.0)

        for handled_signal, previous_handler in previous_handlers.items():
            signal.signal(handled_signal, previous_handler)

    return exit_code
