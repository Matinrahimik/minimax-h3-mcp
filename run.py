#!/usr/bin/env python3
"""Load MiniMax secrets into the environment, then exec the stdio MCP server.

Does not hardcode an agent id. Secret resolution:

1. ``.env`` next to this file (does not override existing env vars)
2. ``MINIMAX_API_KEY`` already in the environment
3. ``MINIMAX_API_KEY_FILE`` (JSON ``{"api_key":"..."}`` or a one-line key file)
4. ``MINIMAX_CONNECTOR_SECRETS_ROOT/<id>/minimax.json`` when
   ``MINIMAX_AGENT_ID`` is set (field ``api_key``)
5. any ``MINIMAX_CONNECTOR_SECRETS_ROOT/*/minimax.json`` with ``api_key``
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
