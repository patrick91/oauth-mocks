from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version

from ._runner import PROVIDERS, serve_providers


def _package_version() -> str:
    try:
        return version("oauth-mocks")
    except PackageNotFoundError:
        return "0.0.0"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oauth-mocks",
        description="Run local GitHub and Google OAuth provider mocks.",
    )
    parser.add_argument(
        "-s",
        "--provider",
        default=",".join(PROVIDERS),
        metavar="NAME[,NAME...]",
        help="providers to start (default: github,google)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="host interface to bind (default: 127.0.0.1)",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=9001,
        help="port for the first selected provider (default: 9001)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_package_version()}",
    )
    return parser


def _parse_providers(raw_providers: str, parser: argparse.ArgumentParser) -> list[str]:
    providers = [provider.strip().lower() for provider in raw_providers.split(",")]

    if not providers or any(not provider for provider in providers):
        parser.error("--provider must contain at least one provider name")

    duplicates = sorted(
        provider for provider in set(providers) if providers.count(provider) > 1
    )
    if duplicates:
        parser.error(f"duplicate provider: {', '.join(duplicates)}")

    unknown = [provider for provider in providers if provider not in PROVIDERS]
    if unknown:
        parser.error(
            f"unknown provider: {', '.join(unknown)}; "
            f"available providers: {', '.join(PROVIDERS)}"
        )

    return providers


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(argv) if argv is not None else sys.argv[1:]
    if arguments and arguments[0] == "start":
        arguments.pop(0)

    parser = _build_parser()
    args = parser.parse_args(arguments)
    providers = _parse_providers(args.provider, parser)

    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    last_port = args.port + len(providers) - 1
    if last_port > 65535:
        parser.error(
            f"selected providers require ports through {last_port}, which exceeds 65535"
        )

    return serve_providers(providers, host=args.host, base_port=args.port)
