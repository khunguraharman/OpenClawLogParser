#!/usr/bin/env python3
from __future__ import annotations

import sys


def _ensure_supported_python() -> None:
    if sys.version_info < (3, 12):
        raise SystemExit("OpenClaw Log Parser requires Python 3.12 or newer.")


if __name__ == "__main__":
    _ensure_supported_python()
    from openclaw_log_ingestor.__main__ import main

    raise SystemExit(main())
