from __future__ import annotations

import pytest

from minimax_h3.validation import (
    MODEL_H3,
    MODEL_H3_MAX,
    ValidationError,
    validate_create,
)

T2V = [{"type": "text", "text": "A boy playing basketball by the sea"}]


def _create(**kwargs):
    defaults = dict(
        model=MODEL_H3,
        content=T2V,
        resolution="768P",
        duration=5,
        ratio="16:9",
    )
    defaults.update(kwargs)
    return validate_create(**defaults)


def test_t2v_ok():
    body = _create()
    assert body["model"] == MODEL_H3
    assert body["ratio"] == "16:9"
    assert body["content"][0]["text"].startswith("A boy")


def test_t2v_requires_ratio():
    with pytest.raises(ValidationError, match="ratio is required"):
        _create(ratio=None)


def test_t2v_rejects_adaptive():
    with pytest.raises(ValidationError, match="cannot be adaptive"):
        _create(ratio="adaptive")


def test_h3_rejects_480p():
    with pytest.raises(ValidationError, match="480P"):
        _create(resolution="480P")


def test_h3_max_rejects_2k():
    with pytest.raises(ValidationError, match="2K"):
        _create(model=MODEL_H3_MAX, resolution="2K")


def test_h3_max_defaults_768p():
    body = _create(model=MODEL_H3_MAX, resolution=None)
    assert body["resolution"] == "768P"


def test_h3_requires_resolution():
    with pytest.raises(ValidationError, match="resolution is required"):
        _create(resolution=None)


def test_h3_duration_4_ok():
    body = _create(duration=4)
    assert body["duration"] == 4


def test_h3_max_rejects_duration_4():
    with pytest.raises(ValidationError, match="duration 4"):
        _create(model=MODEL_H3_MAX, duration=4, resolution="768P")


def test_unknown_model():
    with pytest.raises(ValidationError, match="model must be"):
        _create(model="T2V-01")


def test_empty_text():
    with pytest.raises(ValidationError, match="non-empty"):
        _create(content=[{"type": "text", "text": "   "}])


def test_text_too_long():
    with pytest.raises(ValidationError, match="7000"):
        _create(content=[{"type": "text", "text": "x" * 7001}])


def test_i2v_first_frame():
    body = _create(
        content=[
            {"type": "text", "text": "steam rises"},
            {
                "type": "image_url",
                "image_url": {"url": "https://cdn.example.com/frame.png"},
                "role": "first_frame",
            },
        ],
        ratio="16:9",
    )
    assert body["ratio"] == "adaptive"
    assert body["content"][1]["role"] == "first_frame"


def test_i2v_unroled_image_defaults_first_frame():
    body = _create(
        content=[
            {"type": "text", "text": "go"},
            {"type": "image_url", "image_url": {"url": "https://cdn.example.com/a.jpg"}},
        ],
        ratio=None,
    )
    assert body["content"][1]["role"] == "first_frame"
    assert body["ratio"] == "adaptive"


def test_cannot_mix_i2v_and_r2v():
    with pytest.raises(ValidationError, match="cannot be mixed"):
        _create(
            content=[
                {"type": "text", "text": "go"},
                {
                    "type": "image_url",
                    "image_url": {"url": "https://cdn.example.com/a.png"},
                    "role": "first_frame",
                },
                {
                    "type": "image_url",
                    "image_url": {"url": "https://cdn.example.com/b.png"},
                    "role": "reference_image",
                },
            ]
        )


def test_h3_max_rejects_reference():
    with pytest.raises(ValidationError, match="does not support reference"):
        _create(
            model=MODEL_H3_MAX,
            resolution="768P",
            content=[
                {"type": "text", "text": "go"},
                {
                    "type": "image_url",
                    "image_url": {"url": "https://cdn.example.com/a.png"},
                    "role": "reference_image",
                },
            ],
        )


def test_r2v_ok_on_h3():
    body = _create(
        resolution="2K",
        content=[
            {"type": "text", "text": "character speaks"},
            {
                "type": "video_url",
                "video_url": {"url": "https://cdn.example.com/ref.mp4"},
                "role": "reference_video",
            },
            {
                "type": "audio_url",
                "audio_url": {"url": "https://cdn.example.com/ref.mp3"},
                "role": "reference_audio",
            },
        ],
        ratio=None,
    )
    assert body["ratio"] == "adaptive"
    assert body["resolution"] == "2K"


def test_too_many_first_frames():
    with pytest.raises(ValidationError, match="first_frame"):
        _create(
            content=[
                {"type": "text", "text": "go"},
                {
                    "type": "image_url",
                    "image_url": {"url": "https://cdn.example.com/a.png"},
                    "role": "first_frame",
                },
                {
                    "type": "image_url",
                    "image_url": {"url": "https://cdn.example.com/b.png"},
                    "role": "first_frame",
                },
            ]
        )


def test_too_many_reference_images():
    images = [
        {
            "type": "image_url",
            "image_url": {"url": f"https://cdn.example.com/{i}.png"},
            "role": "reference_image",
        }
        for i in range(10)
    ]
    with pytest.raises(ValidationError, match="reference_image"):
        _create(content=[{"type": "text", "text": "go"}, *images])


def test_too_many_videos():
    videos = [
        {
            "type": "video_url",
            "video_url": {"url": f"https://cdn.example.com/{i}.mp4"},
            "role": "reference_video",
        }
        for i in range(4)
    ]
    with pytest.raises(ValidationError, match="reference_video"):
        _create(content=[{"type": "text", "text": "go"}, *videos])


def test_rejects_gif_image():
    with pytest.raises(ValidationError, match="extension"):
        _create(
            content=[
                {"type": "text", "text": "go"},
                {
                    "type": "image_url",
                    "image_url": {"url": "https://cdn.example.com/a.gif"},
                    "role": "first_frame",
                },
            ]
        )


def test_callback_url_passthrough():
    body = _create(callback_url="https://example.com/hook")
    assert body["callback_url"] == "https://example.com/hook"


def test_drops_unofficial_fields():
    body = _create(
        content=[
            {"type": "text", "text": "go", "prompt_optimizer": True},
        ]
    )
    assert "prompt_optimizer" not in body["content"][0]


def test_t2v_two_texts_rejected():
    with pytest.raises(ValidationError, match="single text"):
        _create(
            content=[
                {"type": "text", "text": "one"},
                {"type": "text", "text": "two"},
            ]
        )
