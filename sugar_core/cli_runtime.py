"""User-facing process boundaries shared by the command-line applications."""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from collections.abc import Callable
from datetime import date

import requests


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def iso_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a valid date in YYYY-MM-DD format") from exc


def read_secret(prompt: str, env: str) -> str:
    value = os.environ.get(env, "").strip()
    if value:
        return value
    if not sys.stdin.isatty():
        raise ValueError(f"Set {env} before running this command without an interactive terminal.")
    value = getpass.getpass(prompt).strip()
    if not value:
        raise ValueError(f"A credential is required. Set {env} or enter it at the prompt.")
    return value


def run_cli(main: Callable, argv: list[str] | None = None, *, prog: str) -> int:
    """Keep expected input/access failures concise without hiding programming errors.

    Library ``main`` functions retain their exception behavior. Set SUGAR_DEBUG=1
    to see a traceback for expected failures at the console boundary as well.
    """
    try:
        return main(argv)
    except BrokenPipeError:
        # Avoid a second broken pipe while Python flushes redirected stdout.
        with open(os.devnull, "w") as sink:
            os.dup2(sink.fileno(), sys.stdout.fileno())
        return 0
    except KeyboardInterrupt:
        print(f"{prog}: interrupted", file=sys.stderr)
        return 130
    except (OSError, ValueError, EOFError, requests.RequestException) as exc:
        if os.environ.get("SUGAR_DEBUG") == "1":
            raise
        print(f"{prog}: error: {exc}", file=sys.stderr)
        return 2
