import sys
import time

_START = time.time()


def log(msg: str, level: str = "INFO"):
    elapsed = time.time() - _START
    print(f"[{elapsed:7.2f}s] [{level}] {msg}", file=sys.stdout, flush=True)


def section(title: str):
    log("=" * 60)
    log(title.upper())
    log("=" * 60)
