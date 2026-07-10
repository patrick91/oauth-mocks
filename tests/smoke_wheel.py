from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def find_consecutive_ports() -> int:
    for _ in range(100):
        with socket.socket() as first:
            first.bind(("127.0.0.1", 0))
            port = first.getsockname()[1]

        if port >= 65535:
            continue

        with socket.socket() as second:
            try:
                second.bind(("127.0.0.1", port + 1))
            except OSError:
                continue

        return port

    raise RuntimeError("could not find two consecutive free ports")


def wait_for_response(url: str, process: subprocess.Popen[str]) -> bytes:
    deadline = time.monotonic() + 15
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise RuntimeError(
                f"wheel CLI exited with {process.returncode}\n"
                f"stdout:\n{stdout}\nstderr:\n{stderr}"
            )

        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                return response.read()
        except (OSError, urllib.error.URLError) as error:
            last_error = error
            time.sleep(0.05)

    raise RuntimeError(f"timed out waiting for {url}: {last_error}")


def executable_path(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "oauth-mocks.exe"
    return venv / "bin" / "oauth-mocks"


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: smoke_wheel.py PATH_TO_WHEEL")

    wheel = Path(sys.argv[1]).resolve()
    if not wheel.is_file():
        raise SystemExit(f"wheel not found: {wheel}")

    with tempfile.TemporaryDirectory(prefix="oauth-mocks-wheel-") as temp_dir:
        venv = Path(temp_dir) / "venv"
        subprocess.run(
            ["uv", "venv", "--python", sys.executable, str(venv)], check=True
        )
        subprocess.run(
            ["uv", "pip", "install", "--python", str(venv), str(wheel)],
            check=True,
        )

        executable = executable_path(venv)
        subprocess.run([executable, "--help"], check=True)

        port = find_consecutive_ports()
        process = subprocess.Popen(
            [executable, "--host", "127.0.0.1", "--port", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            github_page = wait_for_response(f"http://127.0.0.1:{port}/", process)
            google_page = wait_for_response(f"http://127.0.0.1:{port + 1}/", process)
            discovery = json.loads(
                wait_for_response(
                    f"http://127.0.0.1:{port + 1}/.well-known/openid-configuration",
                    process,
                )
            )
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=10)

        if process.returncode != 0:
            raise RuntimeError(
                f"wheel CLI exited with {process.returncode}\n"
                f"stdout:\n{stdout}\nstderr:\n{stderr}"
            )
        if b"GitHub OAuth Mock" not in github_page:
            raise RuntimeError("GitHub template was not served from the wheel")
        if b"Google OAuth Mock" not in google_page:
            raise RuntimeError("Google template was not served from the wheel")
        if discovery["token_endpoint"] != f"http://127.0.0.1:{port + 1}/token":
            raise RuntimeError("Google discovery document advertised the wrong URL")

    print(f"Wheel smoke test passed: {wheel.name}")


if __name__ == "__main__":
    main()
