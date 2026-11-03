from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from mcp import Client

from minimax_h3.server import configure_client, mcp
from tests.test_client import TASK_ID, _client, _handler_factory


@pytest.fixture
def mock_api(tmp_path: Path):
    handler = _handler_factory(["running", "succeeded"])
    client = _client(tmp_path, handler)
    configure_client(client)
    yield handler, client
    configure_client(None)
    client.close()


async def test_tools_are_registered() -> None:
    async with Client(mcp) as session:
        tools = await session.list_tools()
        names = sorted(t.name for t in tools.tools)
        assert names == [
            "minimax_h3_create_video",
            "minimax_h3_get_task",
            "minimax_h3_wait_for_video",
        ]


async def test_create_tool_mocked(mock_api) -> None:
    async with Client(mcp) as session:
        result = await session.call_tool(
            "minimax_h3_create_video",
            {
                "model": "MiniMax-H3",
                "content": [{"type": "text", "text": "A boy playing basketball by the sea"}],
                "resolution": "768P",
                "duration": 5,
                "ratio": "16:9",
            },
        )
    data = result.structured_content or {}
    assert data.get("ok") is True
    assert data.get("task_id") == TASK_ID


async def test_create_tool_rejects_illegal_combo(mock_api) -> None:
    async with Client(mcp) as session:
        result = await session.call_tool(
            "minimax_h3_create_video",
            {
                "model": "MiniMax-H3-Max",
                "content": [
                    {"type": "text", "text": "go"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://cdn.example.com/a.png"},
                        "role": "reference_image",
                    },
                ],
                "resolution": "768P",
                "duration": 5,
                "ratio": "16:9",
            },
        )
    data = result.structured_content or {}
    assert data.get("ok") is False
    assert "reference" in (data.get("error") or "").lower()
    assert mock_api[0].calls["create"] == 0


async def test_get_and_wait_tools(mock_api, tmp_path: Path) -> None:
    async with Client(mcp) as session:
        got = await session.call_tool("minimax_h3_get_task", {"task_id": TASK_ID})
        wait = await session.call_tool(
            "minimax_h3_wait_for_video",
            {"task_id": TASK_ID, "poll_interval": 0.01, "timeout": 2.0},
        )
    assert (got.structured_content or {}).get("status") == "running"
    wait_data = wait.structured_content or {}
    assert wait_data.get("ok") is True
    assert wait_data.get("path", "").endswith(f"{TASK_ID}.mp4")
    assert Path(wait_data["path"]).exists()


def test_import_and_list_tools_without_live_http() -> None:
    import minimax_h3
    import minimax_h3.server as server
    from minimax_h3.config import Settings

    assert minimax_h3.__version__
    settings = Settings.from_env()
    assert settings.test_mode is True
    assert server._injected_client is None


def test_does_not_import_hailuo_package() -> None:
    import minimax_h3.server as server

    assert "minimax_mcp" not in dir(server)
    src = Path(server.__file__).read_text(encoding="utf-8")
    assert "minimax_mcp" not in src
    assert "T2V-01" in src  # mentioned only as what this is not
