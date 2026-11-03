from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _iter_source_files():
    yield ROOT / "run.py"
    yield ROOT / "pyproject.toml"
    yield ROOT / "README.md"
    yield ROOT / ".env.example"
    yield ROOT / ".gitignore"
    yield ROOT / ".github" / "workflows" / "tests.yml"
    for path in (ROOT / "minimax_h3").glob("*.py"):
        yield path
    for path in (ROOT / "tests").glob("*.py"):
        yield path


def test_layout_files_exist() -> None:
    for name in (
        "run.py",
        "LICENSE",
        ".env.example",
        "assets/cover.png",
        "minimax_h3/config.py",
        "minimax_h3/client.py",
        "minimax_h3/validation.py",
        "minimax_h3/server.py",
    ):
        assert (ROOT / name).is_file(), name
    cover = ROOT / "assets/cover.png"
    assert cover.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_readme_has_public_mcp_snippets() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert readme.startswith("![minimax-h3-mcp](assets/cover.png)")
    assert "MiniMax H3 video generation for AI assistants" in readme
    assert '"minimax-h3"' in readme
    assert "~/.cursor/mcp.json" in readme
    assert "claude_desktop_config.json" in readme
    assert "/absolute/path/to/minimax-h3-mcp/run.py" in readme
    assert "MINIMAX_API_KEY" in readme
    assert "minimax_h3_create_video" in readme
    assert "minimax_h3_get_task" in readme
    assert "minimax_h3_wait_for_video" in readme
    assert "\u2014" not in readme
    assert "\u2013" not in readme


def test_gitignore_keeps_env_example() -> None:
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in text
    assert ".env.*" in text
    assert "!.env.example" in text


def test_no_homebooks_or_hardcoded_machine_paths() -> None:
    banned = ("HomeBooks", "/home/box", "/workspace/")
    for path in _iter_source_files():
        if path.resolve() == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{token!r} found in {path.relative_to(ROOT)}"
