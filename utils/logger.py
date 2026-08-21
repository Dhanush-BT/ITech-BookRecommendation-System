"""Timestamped console logger."""
import sys
import time

import config


def log(message: str) -> None:
    if not config.LOG_VERBOSE:
        return
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {message}", file=sys.stderr)


def section(title: str) -> None:
    if not config.LOG_VERBOSE:
        return
    bar = "=" * max(8, len(title))
    print(f"\n{bar}\n{title}\n{bar}", file=sys.stderr)
