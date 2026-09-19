"""Run the agent host.

    DEMO=true python -m apps.host          # fake driver, no VM needed
    uvicorn apps.host.server:app --host 0.0.0.0 --port 8000

On the VM this runs under systemd (or tmux, across SSH drops).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402

from server import create_app  # noqa: E402


def main() -> None:
    uvicorn.run(
        create_app(),
        host=os.environ.get("HOST_BIND", "127.0.0.1"),
        port=int(os.environ.get("HOST_PORT", "8000")),
        log_level=os.environ.get("HOST_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
