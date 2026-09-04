#!/usr/bin/env python3
"""Load MiniMax secrets into the environment, then exec the stdio MCP server.

Does not hardcode an agent id. Secret resolution:

1. ``MINIMAX_API_KEY`` already in the environment
2. ``/home/box/agent-data/connector-secrets/<id>/minimax.json`` when
   ``MINIMAX_AGENT_ID`` is set (field ``api_key``)
3. any ``.../connector-secrets/*/minimax.json`` with ``api_key``
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from minimax_h3.config import load_secrets_into_env

    load_secrets_into_env()
    env = os.environ.copy()
    pythonpath = str(ROOT)
    existing = env.get("PYTHONPATH")
    if existing:
        pythonpath = pythonpath + os.pathsep + existing
    env["PYTHONPATH"] = pythonpath
    os.execve(
        sys.executable,
        [sys.executable, "-m", "minimax_h3.server"],
        env,
    )


if __name__ == "__main__":
    main()
