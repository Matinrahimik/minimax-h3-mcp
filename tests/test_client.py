from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from minimax_h3.client import LiveHttpRefused, MiniMaxH3Client
from minimax_h3.config import Settings

FAKE_MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32
TASK_ID = "424010985738629"


def _handler_factory(states: list[str]):
    calls = {"create": 0, "query": 0, "download": 0, "bodies": []}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path.endswith("/v2/video_generation"):
            calls["create"] += 1
            calls["bodies"].append(json.loads(request.content.decode("utf-8")))
            auth = request.headers.get("authorization", "")
            assert auth.startswith("Bearer ")
            return httpx.Response(200, json={"task_id": TASK_ID})
        if request.method == "GET" and "/v2/query/video_generation/" in path:
            calls["query"] += 1
            status = states.pop(0) if states else "succeeded"
            body = {
                "task": {
                    "id": TASK_ID,
                    "model": "MiniMax-H3",
                    "status": status,
                    "content": {"url": "https://cdn.example.com/out.mp4"}
                    if status == "succeeded"
                    else {},
                    "resolution": "768P",
                    "duration": 5,
                    "usage": {
                        "total_seconds": 5,
                        "input_seconds": 0,
                        "output_seconds": 5,
                        "input_image_count": 0,
                    },
                    "ratio": "16:9",
                    "task_type": "generation",
                    "modality": "video",
                }
            }
            return httpx.Response(200, json=body)
        if request.method == "GET" and request.url.host == "cdn.example.com":
            calls["download"] += 1
            return httpx.Response(200, content=FAKE_MP4, headers={"content-type": "video/mp4"})
        return httpx.Response(404, json={"error": {"message": f"unexpected {request.url}"}})

    handler.calls = calls  # type: ignore[attr-defined]
    return handler


def _client(tmp_path: Path, handler) -> MiniMaxH3Client:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport, timeout=5.0)
    return MiniMaxH3Client(
        "test-key-not-real",
        "https://api.minimax.io",
        output_dir=tmp_path,
        http_client=http,
        sleep=lambda _s: None,
        poll_interval=0.01,
        wait_timeout=2.0,
    )


def test_create_mocked(tmp_path: Path) -> None:
    handler = _handler_factory(["succeeded"])
    client = _client(tmp_path, handler)
    result = client.create_video(
        model="MiniMax-H3",
        content=[{"type": "text", "text": "A boy playing basketball by the sea"}],
        resolution="768P",
        duration=5,
        ratio="16:9",
    )
    assert result["task_id"] == TASK_ID
    assert handler.calls["create"] == 1
    body = handler.calls["bodies"][0]
    assert body["model"] == "MiniMax-H3"
    assert "prompt" not in body


def test_get_task_mocked(tmp_path: Path) -> None:
    handler = _handler_factory(["running"])
    client = _client(tmp_path, handler)
    data = client.get_task(TASK_ID)
    summary = client.summarize_task(data)
    assert summary["status"] == "running"
    assert summary["url"] is None
    assert handler.calls["create"] == 0


def test_wait_downloads_mp4(tmp_path: Path) -> None:
    handler = _handler_factory(["queued", "running", "succeeded"])
    client = _client(tmp_path, handler)
    result = client.wait_for_video(TASK_ID)
    assert result["status"] == "succeeded"
    assert result["usage"]["output_seconds"] == 5
    path = Path(result["path"])
    assert path.exists()
    assert path.read_bytes() == FAKE_MP4
    assert handler.calls["query"] == 3
    assert handler.calls["download"] == 1
    assert handler.calls["create"] == 0


def test_test_mode_refuses_live_http(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINIMAX_H3_TEST_MODE", "1")
    settings = Settings(
        api_key="x",
        api_host="https://api.minimax.io",
        output_dir=tmp_path,
        test_mode=True,
    )
    with pytest.raises(LiveHttpRefused, match="refuses live HTTP"):
        MiniMaxH3Client.from_settings(settings)


def test_client_repr_hides_key(tmp_path: Path) -> None:
    handler = _handler_factory([])
    client = _client(tmp_path, handler)
    assert "test-key-not-real" not in repr(client)


def test_api_error_message_has_no_bearer(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={
                "type": "error",
                "error": {
                    "type": "authorized_error",
                    "message": "login fail (1004)",
                    "http_code": "401",
                },
            },
        )

    client = _client(tmp_path, handler)
    with pytest.raises(Exception, match="401") as exc:
        client.get_task("x")
    assert "Bearer" not in str(exc.value)
    assert "test-key-not-real" not in str(exc.value)
