from __future__ import annotations

import json
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _find_consecutive_ports() -> int:
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


def _wait_for_response(url: str, process: subprocess.Popen[str]) -> bytes:
    deadline = time.monotonic() + 10
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(
                f"server exited with {process.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}"
            )

        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                return response.read()
        except (OSError, urllib.error.URLError) as error:
            last_error = error
            time.sleep(0.05)

    raise AssertionError(f"timed out waiting for {url}: {last_error}")


def _stop_process(process: subprocess.Popen[str]) -> tuple[str, str]:
    if process.poll() is None:
        process.send_signal(signal.SIGTERM)
    return process.communicate(timeout=10)


def test_cli_serves_both_providers_and_shuts_down() -> None:
    port = _find_consecutive_ports()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "oauth_mocks",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        github_info = json.loads(
            _wait_for_response(f"http://127.0.0.1:{port}/api", process)
        )
        google_discovery = json.loads(
            _wait_for_response(
                f"http://127.0.0.1:{port + 1}/.well-known/openid-configuration",
                process,
            )
        )
        github_page = _wait_for_response(f"http://127.0.0.1:{port}/", process)
        google_page = _wait_for_response(f"http://127.0.0.1:{port + 1}/", process)
    finally:
        stdout, stderr = _stop_process(process)

    assert process.returncode == 0, f"stdout:\n{stdout}\nstderr:\n{stderr}"
    assert github_info["service"] == "GitHub OAuth Mock"
    assert google_discovery["token_endpoint"] == f"http://127.0.0.1:{port + 1}/token"
    assert b"GitHub OAuth Mock" in github_page
    assert b"Google OAuth Mock" in google_page
    assert f"github   http://127.0.0.1:{port}" in stdout
    assert f"google   http://127.0.0.1:{port + 1}" in stdout


@pytest.mark.parametrize(
    ("provider", "expected_text"),
    [
        ("github", b"GitHub OAuth Mock"),
        ("google", b"Google OAuth Mock"),
    ],
)
def test_provider_folder_entrypoint(provider: str, expected_text: bytes) -> None:
    port = _find_consecutive_ports()
    process = subprocess.Popen(
        [
            "uv",
            "run",
            "fastapi",
            "dev",
            "--reload-dir",
            "../src",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT / provider,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        page = _wait_for_response(f"http://127.0.0.1:{port}/", process)
    finally:
        stdout, stderr = _stop_process(process)

    # `uv run` preserves the terminating signal as 128 + SIGTERM even though
    # the FastAPI child completes its graceful shutdown successfully.
    assert process.returncode in {0, 128 + signal.SIGTERM, -signal.SIGTERM}, (
        f"stdout:\n{stdout}\nstderr:\n{stderr}"
    )
    assert expected_text in page
