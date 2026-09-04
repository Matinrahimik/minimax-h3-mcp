from __future__ import annotations

from pathlib import Path


def test_layout_files_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    for name in (
        "run.py",
        "minimax_h3/config.py",
        "minimax_h3/client.py",
        "minimax_h3/validation.py",
        "minimax_h3/server.py",
    ):
        assert (root / name).is_file(), name


def test_readme_has_exact_add_mcp_server() -> None:
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    assert '"name": "minimax-h3"' in readme
    assert (
        '"command": "/home/box/mcp-servers/minimax-h3/.venv/bin/python"' in readme
    )
    assert (
        '"args": ["/home/box/mcp-servers/minimax-h3/run.py"]' in readme
    )
