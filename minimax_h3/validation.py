"""Official MiniMax H3 / H3-Max V2 create-body validation.

Only fields from
https://platform.minimax.io/docs/api-reference/video-generation-v2-create
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict

MODEL_H3 = "MiniMax-H3"
MODEL_H3_MAX = "MiniMax-H3-Max"
MODELS = (MODEL_H3, MODEL_H3_MAX)

RESOLUTIONS_H3 = frozenset({"768P", "2K"})
RESOLUTIONS_H3_MAX = frozenset({"480P", "768P"})
DEFAULT_RESOLUTION_H3_MAX = "768P"

DURATIONS_H3 = frozenset(range(4, 16))
DURATIONS_H3_MAX = frozenset(range(5, 16))

RATIOS = ("adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16")
T2V_RATIOS = frozenset(r for r in RATIOS if r != "adaptive")

CONTENT_TYPES = ("text", "image_url", "video_url", "audio_url")
I2V_ROLES = frozenset({"first_frame", "last_frame"})
R2V_ROLES = frozenset({"reference_image", "reference_video", "reference_audio"})
ROLES = I2V_ROLES | R2V_ROLES

MAX_TEXT_CHARS = 7000
MAX_FIRST_FRAME = 1
MAX_LAST_FRAME = 1
MAX_REFERENCE_IMAGES = 9
MAX_REFERENCE_VIDEOS = 3
MAX_REFERENCE_AUDIOS = 3
MAX_BODY_BYTES = 64 * 1024 * 1024
MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_VIDEO_BYTES = 50 * 1024 * 1024
MAX_AUDIO_BYTES = 15 * 1024 * 1024
CLIP_DURATION_MIN = 2
CLIP_DURATION_MAX = 15
CLIP_DURATION_TOTAL_MAX = 15

IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"})
VIDEO_EXTS = frozenset({".mp4", ".mov"})
AUDIO_EXTS = frozenset({".wav", ".mp3"})
IMAGE_MIMES = frozenset(
    {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/heic", "image/heif"}
)
VIDEO_MIMES = frozenset({"video/mp4", "video/quicktime"})
AUDIO_MIMES = frozenset({"audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp3", "audio/wave"})

Mode = Literal["t2v", "i2v", "r2v"]
ModelName = Literal["MiniMax-H3", "MiniMax-H3-Max"]
ResolutionName = Literal["480P", "768P", "2K"]
RatioName = Literal["adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"]
ContentTypeName = Literal["text", "image_url", "video_url", "audio_url"]
RoleName = Literal[
    "first_frame",
    "last_frame",
    "reference_image",
    "reference_video",
    "reference_audio",
]


class MediaUrl(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str


class ContentItem(BaseModel):
    """Official V2 content[] item. Extra fields are rejected."""

    model_config = ConfigDict(extra="forbid")
    type: ContentTypeName
    text: str | None = None
    image_url: MediaUrl | None = None
    video_url: MediaUrl | None = None
    audio_url: MediaUrl | None = None
    role: RoleName | None = None


def content_as_dicts(content: list[Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in content:
        if isinstance(item, ContentItem):
            items.append(item.model_dump(exclude_none=True))
        elif isinstance(item, dict):
            items.append(item)
        else:
            items.append(dict(item))
    return items

_DATA_URI_RE = re.compile(
    r"^data:(?P<mime>[\w.+-]+/[\w.+-]+)(?P<params>(?:;[\w.+-]+=[\w.+-]+)*)?(?P<base64>;base64)?,(?P<data>.*)$",
    re.IGNORECASE | re.DOTALL,
)


class ValidationError(ValueError):
    """Illegal model / mode / content combination (safe to show to the model)."""


def _require_mapping(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValidationError(f"content[{index}] must be an object")
    return item


def _url_from_media(obj: Any, field: str, index: int) -> str:
    if not isinstance(obj, dict):
        raise ValidationError(f"content[{index}].{field} must be an object with url")
    url = obj.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ValidationError(f"content[{index}].{field}.url is required")
    return url.strip()


def _path_ext(url: str) -> str:
    path = urlparse(url).path
    if "." not in path.rsplit("/", 1)[-1]:
        return ""
    return "." + path.rsplit(".", 1)[-1].lower()


def _parse_data_uri(url: str) -> tuple[str, bytes] | None:
    match = _DATA_URI_RE.match(url)
    if not match:
        return None
    mime = match.group("mime").lower()
    payload = match.group("data")
    if match.group("base64"):
        pad = "=" * (-len(payload) % 4)
        try:
            decoded = base64.b64decode(payload + pad, validate=False)
        except (ValueError, TypeError) as exc:
            raise ValidationError("invalid base64 in data URI") from exc
    else:
        decoded = payload.encode("utf-8")
    return mime, decoded


def _check_media_url(
    url: str,
    *,
    kind: Literal["image", "video", "audio"],
    index: int,
) -> None:
    parsed = _parse_data_uri(url)
    if parsed is not None:
        mime, decoded = parsed
        max_bytes = {
            "image": MAX_IMAGE_BYTES,
            "video": MAX_VIDEO_BYTES,
            "audio": MAX_AUDIO_BYTES,
        }[kind]
        if len(decoded) > max_bytes:
            raise ValidationError(
                f"content[{index}] {kind} data URI exceeds {max_bytes} bytes"
            )
        allowed = {"image": IMAGE_MIMES, "video": VIDEO_MIMES, "audio": AUDIO_MIMES}[kind]
        if mime not in allowed:
            raise ValidationError(
                f"content[{index}] {kind} data URI mime {mime!r} is not allowed"
            )
        return

    if url.startswith("mm_file://"):
        return

    ext = _path_ext(url)
    if not ext:
        return
    allowed_ext = {"image": IMAGE_EXTS, "video": VIDEO_EXTS, "audio": AUDIO_EXTS}[kind]
    if ext not in allowed_ext:
        raise ValidationError(
            f"content[{index}] {kind} URL extension {ext!r} is not allowed "
            f"(allowed: {sorted(allowed_ext)})"
        )


def _role_for_item(item: dict[str, Any], index: int) -> str | None:
    role = item.get("role")
    if role is None:
        return None
    if role not in ROLES:
        raise ValidationError(
            f"content[{index}].role must be one of {sorted(ROLES)}, got {role!r}"
        )
    return role


def classify_content(content: list[dict[str, Any]]) -> tuple[Mode, list[dict[str, Any]]]:
    """Normalize roles and return (mode, items ready to send)."""
    if not content:
        raise ValidationError("content must include one non-empty text item")

    texts = 0
    first = last = ref_img = ref_vid = ref_aud = 0
    has_i2v = False
    has_r2v = False
    normalized: list[dict[str, Any]] = []

    for index, raw in enumerate(content):
        item = _require_mapping(raw, index)
        ctype = item.get("type")
        if ctype not in CONTENT_TYPES:
            raise ValidationError(
                f"content[{index}].type must be one of {list(CONTENT_TYPES)}, got {ctype!r}"
            )
        role = _role_for_item(item, index)
        out: dict[str, Any] = {"type": ctype}

        if ctype == "text":
            text = item.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValidationError(
                    f"content[{index}].text is required and must be non-empty"
                )
            if len(text) > MAX_TEXT_CHARS:
                raise ValidationError(
                    f"content[{index}].text exceeds {MAX_TEXT_CHARS} characters"
                )
            if role is not None:
                raise ValidationError("text content items must not set role")
            out["text"] = text
            texts += 1
        elif ctype == "image_url":
            url = _url_from_media(item.get("image_url"), "image_url", index)
            _check_media_url(url, kind="image", index=index)
            if role in R2V_ROLES and role != "reference_image":
                raise ValidationError(
                    f"content[{index}]: image_url role must be first_frame, "
                    "last_frame, or reference_image"
                )
            if role is None:
                role = "first_frame"
            if role == "first_frame":
                first += 1
                has_i2v = True
            elif role == "last_frame":
                last += 1
                has_i2v = True
            elif role == "reference_image":
                ref_img += 1
                has_r2v = True
            else:
                raise ValidationError(
                    f"content[{index}]: image_url role {role!r} is not valid"
                )
            out["image_url"] = {"url": url}
            out["role"] = role
        elif ctype == "video_url":
            url = _url_from_media(item.get("video_url"), "video_url", index)
            _check_media_url(url, kind="video", index=index)
            if role is None:
                role = "reference_video"
            if role != "reference_video":
                raise ValidationError(
                    "video_url is reference-to-video only (role=reference_video)"
                )
            ref_vid += 1
            has_r2v = True
            out["video_url"] = {"url": url}
            out["role"] = role
        elif ctype == "audio_url":
            url = _url_from_media(item.get("audio_url"), "audio_url", index)
            _check_media_url(url, kind="audio", index=index)
            if role is None:
                role = "reference_audio"
            if role != "reference_audio":
                raise ValidationError(
                    "audio_url is reference-to-video only (role=reference_audio)"
                )
            ref_aud += 1
            has_r2v = True
            out["audio_url"] = {"url": url}
            out["role"] = role
        normalized.append(out)

    if texts < 1:
        raise ValidationError("content must include one non-empty text item")

    if has_i2v and has_r2v:
        raise ValidationError(
            "image-to-video (first_frame/last_frame) and reference-to-video "
            "(reference_image/reference_video/reference_audio) cannot be mixed"
        )

    if first > MAX_FIRST_FRAME:
        raise ValidationError(f"first_frame count must be ≤ {MAX_FIRST_FRAME}")
    if last > MAX_LAST_FRAME:
        raise ValidationError(f"last_frame count must be ≤ {MAX_LAST_FRAME}")
    if ref_img > MAX_REFERENCE_IMAGES:
        raise ValidationError(f"reference_image count must be ≤ {MAX_REFERENCE_IMAGES}")
    if ref_vid > MAX_REFERENCE_VIDEOS:
        raise ValidationError(f"reference_video count must be ≤ {MAX_REFERENCE_VIDEOS}")
    if ref_aud > MAX_REFERENCE_AUDIOS:
        raise ValidationError(f"reference_audio count must be ≤ {MAX_REFERENCE_AUDIOS}")

    if has_r2v:
        return "r2v", normalized
    if has_i2v:
        return "i2v", normalized
    if texts != 1 or len(normalized) != 1:
        raise ValidationError(
            "text-to-video content must be a single text item only"
        )
    return "t2v", normalized


def validate_create(
    *,
    model: str,
    content: list[Any],
    resolution: str | None,
    duration: int,
    ratio: str | None = None,
    callback_url: str | None = None,
) -> dict[str, Any]:
    """Return the official create JSON body, or raise ValidationError."""
    if model not in MODELS:
        raise ValidationError(f"model must be {MODEL_H3} or {MODEL_H3_MAX}, got {model!r}")

    if not isinstance(content, list):
        raise ValidationError("content must be an array")

    mode, items = classify_content(content)

    if model == MODEL_H3_MAX and mode == "r2v":
        raise ValidationError(
            "MiniMax-H3-Max does not support reference-to-video "
            "(no reference_image / reference_video / reference_audio)"
        )

    if model == MODEL_H3:
        allowed_res = RESOLUTIONS_H3
        allowed_dur = DURATIONS_H3
        if not resolution:
            raise ValidationError("resolution is required (768P or 2K for MiniMax-H3)")
    else:
        allowed_res = RESOLUTIONS_H3_MAX
        allowed_dur = DURATIONS_H3_MAX
        if not resolution:
            resolution = DEFAULT_RESOLUTION_H3_MAX

    if resolution not in allowed_res:
        raise ValidationError(
            f"resolution {resolution!r} is not valid for {model} "
            f"(allowed: {sorted(allowed_res)})"
        )

    if not isinstance(duration, int) or isinstance(duration, bool):
        raise ValidationError("duration must be an integer number of seconds")
    if duration not in allowed_dur:
        lo, hi = min(allowed_dur), max(allowed_dur)
        raise ValidationError(
            f"duration {duration} is not valid for {model} (allowed: {lo}-{hi})"
        )

    if ratio is not None and ratio not in RATIOS:
        raise ValidationError(f"ratio must be one of {list(RATIOS)}, got {ratio!r}")

    if mode == "t2v":
        if not ratio:
            raise ValidationError(
                "ratio is required for text-to-video and cannot be adaptive"
            )
        if ratio == "adaptive":
            raise ValidationError(
                "ratio cannot be adaptive for text-to-video; "
                f"use one of {sorted(T2V_RATIOS)}"
            )
    elif mode == "i2v":
        # Official: I2V ratio is always adaptive; other valid values are ignored.
        ratio = "adaptive"
    elif mode == "r2v":
        if ratio is None:
            ratio = "adaptive"

    body: dict[str, Any] = {
        "model": model,
        "content": items,
        "resolution": resolution,
        "duration": duration,
        "ratio": ratio,
    }
    if callback_url:
        if not isinstance(callback_url, str) or not callback_url.strip():
            raise ValidationError("callback_url must be a non-empty string")
        body["callback_url"] = callback_url.strip()

    encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
    if len(encoded) > MAX_BODY_BYTES:
        raise ValidationError(
            f"request body exceeds {MAX_BODY_BYTES} bytes (official limit 64 MB)"
        )
    return body
