from __future__ import annotations

import json
from pathlib import Path

from minimax_h3.config import Settings, load_secrets_into_env, resolve_api_key


def test_env_key_wins(tmp_path: Path) -> None:
    env = {"MINIMAX_API_KEY": "from-env"}
    assert resolve_api_key(environ=env, secrets_root=tmp_path) == "from-env"


def test_agent_id_file(tmp_path: Path) -> None:
    agent = tmp_path / "agent-xyz"
    agent.mkdir()
    (agent / "minimax.json").write_text(json.dumps({"api_key": "from-agent"}), encoding="utf-8")
    env = {"MINIMAX_AGENT_ID": "agent-xyz"}
    assert resolve_api_key(environ=env, secrets_root=tmp_path) == "from-agent"


def test_glob_any_minimax_json(tmp_path: Path) -> None:
    other = tmp_path / "some-connector"
    other.mkdir()
    (other / "minimax.json").write_text(json.dumps({"api_key": "from-glob"}), encoding="utf-8")
    assert resolve_api_key(environ={}, secrets_root=tmp_path) == "from-glob"


def test_load_secrets_does_not_override_env(tmp_path: Path) -> None:
    env = {"MINIMAX_API_KEY": "keep-me"}
    other = tmp_path / "c"
    other.mkdir()
    (other / "minimax.json").write_text(json.dumps({"api_key": "nope"}), encoding="utf-8")
    load_secrets_into_env(environ=env, secrets_root=tmp_path)
    assert env["MINIMAX_API_KEY"] == "keep-me"


def test_settings_repr_hides_key() -> None:
    settings = Settings(
        api_key="super-secret-key-value",
        api_host="https://api.minimax.io",
        output_dir=Path("/tmp"),
        test_mode=True,
    )
    text = repr(settings)
    assert "super-secret-key-value" not in text
    assert "***" in text


def test_no_hardcoded_agent_id_in_run_py() -> None:
    run = Path(__file__).resolve().parents[1] / "run.py"
    src = run.read_text(encoding="utf-8")
    assert "MINIMAX_AGENT_ID" in src
    assert "hardcode" in src.lower() or "Does not hardcode" in src or "does not hardcode" in src.lower()
    # no UUID-looking agent id literals
    import re

    assert not re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-", src)
