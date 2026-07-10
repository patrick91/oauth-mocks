from __future__ import annotations

from collections.abc import Sequence

import pytest

from oauth_mocks import cli


def test_cli_starts_both_providers_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: tuple[Sequence[str], str, int] | None = None

    def fake_serve_providers(
        providers: Sequence[str], *, host: str, base_port: int
    ) -> int:
        nonlocal received
        received = providers, host, base_port
        return 0

    monkeypatch.setattr(cli, "serve_providers", fake_serve_providers)

    assert cli.main([]) == 0
    assert received == (["github", "google"], "127.0.0.1", 9001)


def test_cli_accepts_start_alias_and_provider_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: tuple[Sequence[str], str, int] | None = None

    def fake_serve_providers(
        providers: Sequence[str], *, host: str, base_port: int
    ) -> int:
        nonlocal received
        received = providers, host, base_port
        return 0

    monkeypatch.setattr(cli, "serve_providers", fake_serve_providers)

    assert (
        cli.main(
            [
                "start",
                "--provider",
                "google,github",
                "--host",
                "0.0.0.0",
                "--port",
                "9100",
            ]
        )
        == 0
    )
    assert received == (["google", "github"], "0.0.0.0", 9100)


def test_cli_accepts_start_alias_from_process_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: tuple[Sequence[str], str, int] | None = None

    def fake_serve_providers(
        providers: Sequence[str], *, host: str, base_port: int
    ) -> int:
        nonlocal received
        received = providers, host, base_port
        return 0

    monkeypatch.setattr(cli, "serve_providers", fake_serve_providers)
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["oauth-mocks", "start", "--provider", "google", "--port", "9002"],
    )

    assert cli.main() == 0
    assert received == (["google"], "127.0.0.1", 9002)


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--provider", "unknown"], "unknown provider: unknown"),
        (["--provider", "github,github"], "duplicate provider: github"),
        (["--provider", ""], "must contain at least one provider"),
        (["--port", "0"], "must be between 1 and 65535"),
        (["--port", "65535"], "require ports through 65536"),
    ],
)
def test_cli_rejects_invalid_arguments(
    arguments: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(arguments)

    assert exc_info.value.code == 2
    assert message in capsys.readouterr().err


def test_cli_reports_installed_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out == "oauth-mocks 0.0.0\n"
