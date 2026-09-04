"""httpx client for MiniMax video generation V2 (create / query / download)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

import httpx

from minimax_h3.config import Settings, is_test_mode
from minimax_h3.validation import validate_create

CREATE_PATH = "/v2/video_generation"
QUERY_PATH = "/v2/query/video_generation/{task_id}"
TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})
DEFAULT_POLL_SECONDS = 12.0
DEFAULT_WAIT_TIMEOUT = 1800.0
DEFAULT_API_TIMEOUT = 60.0
DEFAULT_DOWNLOAD_TIMEOUT = 300.0


class MiniMaxAPIError(RuntimeError):
    """HTTP or API error from MiniMax. Message must never include secrets."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class LiveHttpRefused(RuntimeError):
    """``MINIMAX_H3_TEST_MODE=1`` refuses live HTTP unless a client is injected."""


class MiniMaxH3Client:
    def __init__(
        self,
        api_key: str,
        api_host: str,
        *,
        output_dir: Path,
        http_client: httpx.Client | None = None,
        test_mode: bool = False,
        sleep: Callable[[float], None] = time.sleep,
        poll_interval: float = DEFAULT_POLL_SECONDS,
        wait_timeout: float = DEFAULT_WAIT_TIMEOUT,
    ) -> None:
        self._api_key = api_key
        self.api_host = api_host.rstrip("/")
        self.output_dir = Path(output_dir)
        self._sleep = sleep
        self.poll_interval = poll_interval
        self.wait_timeout = wait_timeout
        self._owns_http = http_client is None
        if http_client is None:
            if test_mode or is_test_mode():
                raise LiveHttpRefused(
                    "MINIMAX_H3_TEST_MODE=1 refuses live HTTP unless an httpx "
                    "client is injected"
                )
            self._http = httpx.Client(
                base_url=self.api_host,
                headers=self._headers(),
                timeout=httpx.Timeout(DEFAULT_API_TIMEOUT),
            )
        else:
            self._http = http_client

    def __repr__(self) -> str:
        return (
            f"MiniMaxH3Client(api_host={self.api_host!r}, "
            f"output_dir={str(self.output_dir)!r})"
        )

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> MiniMaxH3Client:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        http_client: httpx.Client | None = None,
        **kwargs: Any,
    ) -> MiniMaxH3Client:
        return cls(
            settings.api_key,
            settings.api_host,
            output_dir=settings.output_dir,
            http_client=http_client,
            test_mode=settings.test_mode,
            **kwargs,
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _error_message(self, response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return f"MiniMax HTTP {response.status_code}"
        err = data.get("error") if isinstance(data, dict) else None
        if isinstance(err, dict):
            message = err.get("message") or err.get("type") or "error"
            return f"MiniMax HTTP {response.status_code}: {message}"
        return f"MiniMax HTTP {response.status_code}"

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._http.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise MiniMaxAPIError(f"MiniMax request failed: {exc.__class__.__name__}") from exc
        if response.status_code >= 400:
            raise MiniMaxAPIError(
                self._error_message(response), status_code=response.status_code
            )
        return response

    def create_video(self, **kwargs: Any) -> dict[str, Any]:
        body = validate_create(**kwargs)
        response = self._request(
            "POST",
            f"{self.api_host}{CREATE_PATH}",
            json=body,
            headers=self._headers(),
        )
        try:
            data = response.json()
        except ValueError as exc:
            raise MiniMaxAPIError("MiniMax create returned non-JSON") from exc
        if not isinstance(data, dict) or not data.get("task_id"):
            raise MiniMaxAPIError("MiniMax create did not return task_id")
        return data

    def get_task(self, task_id: str) -> dict[str, Any]:
        if not task_id or not str(task_id).strip():
            raise MiniMaxAPIError("task_id is required")
        path = QUERY_PATH.format(task_id=str(task_id).strip())
        response = self._request(
            "GET",
            f"{self.api_host}{path}",
            headers=self._headers(),
        )
        try:
            data = response.json()
        except ValueError as exc:
            raise MiniMaxAPIError("MiniMax query returned non-JSON") from exc
        if not isinstance(data, dict):
            raise MiniMaxAPIError("MiniMax query returned an unexpected body")
        return data

    def summarize_task(self, data: dict[str, Any]) -> dict[str, Any]:
        task = data.get("task") if isinstance(data.get("task"), dict) else {}
        content = task.get("content") if isinstance(task.get("content"), dict) else {}
        usage = task.get("usage") if isinstance(task.get("usage"), dict) else {}
        error = task.get("error") if isinstance(task.get("error"), dict) else None
        return {
            "task_id": task.get("id") or data.get("task_id"),
            "status": task.get("status"),
            "model": task.get("model"),
            "resolution": task.get("resolution"),
            "duration": task.get("duration"),
            "ratio": task.get("ratio"),
            "usage": usage,
            "url": content.get("url"),
            "error": error,
            "task_type": task.get("task_type"),
            "modality": task.get("modality"),
        }

    def download_video(self, url: str, task_id: str) -> Path:
        if not url:
            raise MiniMaxAPIError("no video URL to download")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        dest = self.output_dir / f"{task_id}.mp4"
        try:
            with self._http.stream(
                "GET",
                url,
                timeout=httpx.Timeout(DEFAULT_DOWNLOAD_TIMEOUT),
                follow_redirects=True,
            ) as response:
                if response.status_code >= 400:
                    raise MiniMaxAPIError(
                        f"video download HTTP {response.status_code}",
                        status_code=response.status_code,
                    )
                with dest.open("wb") as handle:
                    for chunk in response.iter_bytes():
                        handle.write(chunk)
        except MiniMaxAPIError:
            raise
        except httpx.HTTPError as exc:
            raise MiniMaxAPIError(
                f"video download failed: {exc.__class__.__name__}"
            ) from exc
        return dest

    def wait_for_video(
        self,
        task_id: str,
        *,
        poll_interval: float | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        interval = self.poll_interval if poll_interval is None else poll_interval
        limit = self.wait_timeout if timeout is None else timeout
        deadline = time.monotonic() + limit
        last: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            last = self.get_task(task_id)
            summary = self.summarize_task(last)
            status = summary.get("status")
            if status in TERMINAL_STATUSES:
                if status != "succeeded":
                    err = summary.get("error") or {}
                    detail = err.get("message") if isinstance(err, dict) else status
                    raise MiniMaxAPIError(
                        f"task {task_id} ended with status {status}: {detail}"
                    )
                url = summary.get("url")
                if not url:
                    raise MiniMaxAPIError(
                        f"task {task_id} succeeded but task.content.url is missing"
                    )
                path = self.download_video(str(url), str(summary.get("task_id") or task_id))
                return {
                    **summary,
                    "path": str(path),
                }
            self._sleep(interval)
        raise MiniMaxAPIError(
            f"timed out waiting for task {task_id} after {limit}s "
            f"(last status: {(self.summarize_task(last) if last else {}).get('status')})"
        )
