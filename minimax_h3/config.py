"""Env, host, output dir, and MiniMax secret resolution.

Secret lookup order (never prints the key):
1. ``MINIMAX_API_KEY`` already in the environment
2. ``MINIMAX_API_KEY_FILE`` (JSON ``{"api_key":"..."}`` or a one-line key file)
3. ``MINIMAX_CONNECTOR_SECRETS_ROOT/<id>/minimax.json`` when
   ``MINIMAX_AGENT_ID`` is set (field ``api_key``)
4. any ``MINIMAX_CONNECTOR_SECRETS_ROOT/*/minimax.json`` that contains ``api_key``

A ``.env`` file next to ``run.py`` is loaded first when using the process
environment, and does not override variables that are already set.

Does not hardcode an agent id. JSON key file shape: ``{"api_key":"..."}``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_API_HOST = "https://api.minimax.io"
DEFAULT_OUTPUT_DIRNAME = "minimax-h3-output"
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
    raw = env.get("MINIMAX_H3_OUTPUT_DIR")
    if isinstance(raw, str) and raw.strip():
        return Path(raw.strip()).expanduser()
    return Path.cwd() / DEFAULT_OUTPUT_DIRNAME


def connector_secrets_root(
    environ: dict[str, str] | None = None,
    secrets_root: Path | None = None,
) -> Path | None:
    if secrets_root is not None:
        return secrets_root
    env = environ if environ is not None else os.environ
    raw = env.get("MINIMAX_CONNECTOR_SECRETS_ROOT")
    if isinstance(raw, str) and raw.strip():
        return Path(raw.strip()).expanduser()
    return None


def load_dotenv(
    path: Path | None = None,
    environ: dict[str, str] | None = None,
) -> None:
    """Load KEY=VALUE pairs from a .env file without overriding existing vars."""
    env = environ if environ is not None else os.environ
    dotenv_path = path if path is not None else PACKAGE_ROOT / ".env"
    try:
        text = dotenv_path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in env:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        env[key] = value


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


def _api_key_from_file(path: Path) -> str | None:
    keyed = _api_key_from_json(path)
    if keyed:
        return keyed
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text or text.startswith("{") or text.startswith("["):
        return None
    first = text.splitlines()[0].strip()
    if not first or first.startswith("#") or "=" in first:
        return None
    return first


def resolve_api_key(
    environ: dict[str, str] | None = None,
    secrets_root: Path | None = None,
) -> str | None:
    """Return the MiniMax API key or None. Never logs the value."""
    env = environ if environ is not None else os.environ
    existing = env.get("MINIMAX_API_KEY")
    if isinstance(existing, str) and existing.strip():
        return existing.strip()

    key_file = env.get("MINIMAX_API_KEY_FILE")
    if isinstance(key_file, str) and key_file.strip():
        keyed = _api_key_from_file(Path(key_file.strip()).expanduser())
        if keyed:
            return keyed

    root = connector_secrets_root(environ=env, secrets_root=secrets_root)
    if root is None:
        return None

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
    if env is os.environ:
        load_dotenv(PACKAGE_ROOT / ".env", environ=env)
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
                "MINIMAX_API_KEY is not set. Set it in the environment, a .env "
                "file, MINIMAX_API_KEY_FILE, or a minimax.json under "
                "MINIMAX_CONNECTOR_SECRETS_ROOT"
            )
        return cls(
            api_key=key,
            api_host=api_host(env),
            output_dir=output_dir(env),
            test_mode=test,
        )
