"""Env, host, output dir, and MiniMax secret resolution.

Secret lookup order (never prints the key):
1. ``MINIMAX_API_KEY`` already in the environment
2. ``/home/box/agent-data/connector-secrets/<id>/minimax.json`` when
   ``MINIMAX_AGENT_ID`` is set (field ``api_key``)
3. any ``.../connector-secrets/*/minimax.json`` that contains ``api_key``

Does not hardcode an agent id. PAYG key file shape: ``{"api_key":"..."}``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_API_HOST = "https://api.minimax.io"
DEFAULT_OUTPUT_DIR = "/workspace/minimax-h3-output"
CONNECTOR_SECRETS_ROOT = Path("/home/box/agent-data/connector-secrets")
SECRET_FILENAME = "minimax.json"


class ConfigError(RuntimeError):
    """Missing or unreadable configuration (message must never include secrets)."""


def is_test_mode(environ: dict[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    return env.get("MINIMAX_H3_TEST_MODE") == "1"


def api_host(environ: dict[str, str] | None = None) -> str:
    env = environ if environ is not None else os.environ
    return (env.get("MINIMAX_API_HOST") or DEFAULT_API_HOST).rstrip("/")


def output_dir(environ: dict[str, str] | None = None) -> Path:
    env = environ if environ is not None else os.environ
    return Path(env.get("MINIMAX_H3_OUTPUT_DIR") or DEFAULT_OUTPUT_DIR)


def _api_key_from_json(path: Path) -> str | None:
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    key = data.get("api_key")
    if isinstance(key, str) and key.strip():
        return key.strip()
    return None


def resolve_api_key(
    environ: dict[str, str] | None = None,
    secrets_root: Path | None = None,
) -> str | None:
    """Return the MiniMax API key or None. Never logs the value."""
    env = environ if environ is not None else os.environ
    existing = env.get("MINIMAX_API_KEY")
    if isinstance(existing, str) and existing.strip():
        return existing.strip()

    root = secrets_root if secrets_root is not None else CONNECTOR_SECRETS_ROOT
    agent_id = env.get("MINIMAX_AGENT_ID")
    if isinstance(agent_id, str) and agent_id.strip():
        keyed = _api_key_from_json(root / agent_id.strip() / SECRET_FILENAME)
        if keyed:
            return keyed

    if not root.is_dir():
        return None
    for path in sorted(root.glob(f"*/{SECRET_FILENAME}")):
        keyed = _api_key_from_json(path)
        if keyed:
            return keyed
    return None


def load_secrets_into_env(
    environ: dict[str, str] | None = None,
    secrets_root: Path | None = None,
) -> None:
    """Copy a resolved key into ``MINIMAX_API_KEY`` when it is not already set."""
    env = environ if environ is not None else os.environ
    if env.get("MINIMAX_API_KEY", "").strip():
        return
    key = resolve_api_key(environ=env, secrets_root=secrets_root)
    if key:
        env["MINIMAX_API_KEY"] = key


@dataclass(frozen=True)
class Settings:
    api_key: str
    api_host: str
    output_dir: Path
    test_mode: bool

    def __repr__(self) -> str:
        return (
            f"Settings(api_key=***, api_host={self.api_host!r}, "
            f"output_dir={str(self.output_dir)!r}, test_mode={self.test_mode})"
        )

    @classmethod
    def from_env(
        cls,
        environ: dict[str, str] | None = None,
        secrets_root: Path | None = None,
        require_key: bool = True,
    ) -> Settings:
        env = environ if environ is not None else os.environ
        load_secrets_into_env(environ=env, secrets_root=secrets_root)
        key = (env.get("MINIMAX_API_KEY") or "").strip()
        test = is_test_mode(env)
        if require_key and not key and not test:
            raise ConfigError(
                "MINIMAX_API_KEY is not set and no connector-secrets "
                "minimax.json with api_key was found"
            )
        return cls(
            api_key=key,
            api_host=api_host(env),
            output_dir=output_dir(env),
            test_mode=test,
        )
