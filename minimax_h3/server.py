"""stdio MCP server: MiniMax H3 / H3-Max official V2 video tools."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.mcpserver import MCPServer

from minimax_h3 import __version__
from minimax_h3.client import MiniMaxAPIError, MiniMaxH3Client
from minimax_h3.config import Settings
from minimax_h3.validation import ContentItem, ValidationError, content_as_dicts

INSTRUCTIONS = """\
MiniMax H3 / H3-Max video generation over the official V2 API (global host api.minimax.io).
This is NOT the Hailuo minimax-mcp package (T2V-01 / I2V-01). Do not use Hailuo models here.

COST WARNING: minimax_h3_create_video starts a paid pay-as-you-go job. Only call it when the
user explicitly asks for a generated clip.

Create: POST /v2/video_generation  Query: GET /v2/query/video_generation/{task_id}

Models:
- MiniMax-H3: T2V, I2V first/last frame, reference-to-video. resolution 768P|2K. duration 4-15.
- MiniMax-H3-Max: T2V + I2V first/last only. NO reference_image/video/audio. resolution 480P|768P
  (default 768P, no 2K). duration 5-15 (no 4).

content[] must include one non-empty text (max 7000 chars). Types: text, image_url, video_url,
audio_url. Roles: first_frame, last_frame, reference_image, reference_video, reference_audio.
I2V and reference_* are mutually exclusive.

Limits: first_frame<=1, last_frame<=1, reference_image<=9; images JPG/JPEG/PNG/WEBP/HEIC/HEIF <=30MB.
Video (reference only): <=3 clips, 2-15s each, total <=15s, <=50MB, mp4/mov.
Audio (reference only): <=3 clips, 2-15s each, total <=15s, <=15MB, wav/mp3.
Total request body <= 64 MB.

Ratio: T2V required and cannot be adaptive. I2V always adaptive (other values ignored).
R2V optional, default adaptive. Values: adaptive, 21:9, 16:9, 4:3, 1:1, 3:4, 9:16.

Succeeded query: task.content.url is time-limited; wait_for_video downloads to
MINIMAX_H3_OUTPUT_DIR (default: ./minimax-h3-output in the process working directory).
"""

mcp = MCPServer(
    "minimax-h3",
    instructions=INSTRUCTIONS,
    version=__version__,
)

_injected_client: MiniMaxH3Client | None = None


def configure_client(client: MiniMaxH3Client | None) -> None:
    global _injected_client
    _injected_client = client


def get_client() -> MiniMaxH3Client:
    if _injected_client is not None:
        return _injected_client
    return MiniMaxH3Client.from_settings(Settings.from_env())


def _err(exc: Exception) -> dict[str, Any]:
    return {"ok": False, "error": str(exc)}


@mcp.tool(
    name="minimax_h3_create_video",
    description=(
        "Create a MiniMax H3 / H3-Max video generation task (official V2 POST /v2/video_generation). "
        "COST WARNING: paid pay-as-you-go. Only use when the user explicitly asks. "
        "Required: model (MiniMax-H3 | MiniMax-H3-Max), content[] with one non-empty text, "
        "resolution, duration. Optional: ratio, callback_url. Rejects illegal model/mode/"
        "resolution/duration combinations. Returns task_id."
    ),
)
def minimax_h3_create_video(
    model: Literal["MiniMax-H3", "MiniMax-H3-Max"],
    content: list[ContentItem],
    resolution: Literal["480P", "768P", "2K"],
    duration: int,
    ratio: Literal["adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"]
    | None = None,
    callback_url: str | None = None,
) -> dict[str, Any]:
    try:
        result = get_client().create_video(
            model=model,
            content=content_as_dicts(content),
            resolution=resolution,
            duration=duration,
            ratio=ratio,
            callback_url=callback_url,
        )
        return {"ok": True, **result}
    except (ValidationError, MiniMaxAPIError, RuntimeError) as exc:
        return _err(exc)


@mcp.tool(
    name="minimax_h3_get_task",
    description=(
        "Query a MiniMax V2 video task by task_id "
        "(GET /v2/query/video_generation/{task_id}). "
        "Statuses: queued | running | succeeded | failed | cancelled. "
        "On succeeded, includes usage and the time-limited task.content.url (does not download)."
    ),
)
def minimax_h3_get_task(task_id: str) -> dict[str, Any]:
    try:
        data = get_client().get_task(task_id)
        summary = get_client().summarize_task(data)
        return {"ok": True, **summary, "raw": data}
    except (MiniMaxAPIError, RuntimeError) as exc:
        return _err(exc)


@mcp.tool(
    name="minimax_h3_wait_for_video",
    description=(
        "Poll a MiniMax V2 video task about every 12s until queued/running ends "
        "(succeeded | failed | cancelled). On succeeded, download the mp4 from "
        "task.content.url to MINIMAX_H3_OUTPUT_DIR/{task_id}.mp4 and return path + usage. "
        "Does not create a new paid job."
    ),
)
def minimax_h3_wait_for_video(
    task_id: str,
    poll_interval: float = 12.0,
    timeout: float = 1800.0,
) -> dict[str, Any]:
    try:
        result = get_client().wait_for_video(
            task_id, poll_interval=poll_interval, timeout=timeout
        )
        return {"ok": True, **result}
    except (MiniMaxAPIError, RuntimeError) as exc:
        return _err(exc)


def main() -> None:
    Settings.from_env()
    mcp.run()


if __name__ == "__main__":
    main()
