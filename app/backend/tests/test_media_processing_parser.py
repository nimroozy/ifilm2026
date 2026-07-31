"""Unit tests for ffprobe metadata parsing."""

from __future__ import annotations

import pytest
from app.services.media_processing.errors import ProbeParseError, UnsupportedMediaError
from app.services.media_processing.parser import (
    parse_ffprobe_payload,
    parse_float,
    parse_int,
    parse_rational,
    select_stream,
)


def test_parse_rational_frame_rates():
    assert parse_rational("24000/1001") == pytest.approx(23.976, rel=1e-3)
    assert parse_rational("30/1") == 30.0
    assert parse_rational("0/1") is None
    assert parse_rational("1/0") is None
    assert parse_rational("N/A") is None
    assert parse_rational("") is None


def test_parse_duration_and_bitrate():
    assert parse_float("12.5") == 12.5
    assert parse_float("N/A") is None
    assert parse_int("128000") == 128000
    assert parse_int("bad") is None


def test_default_stream_selection_prefers_disposition_default():
    streams = [
        {"index": 0, "codec_type": "audio", "codec_name": "aac", "disposition": {"default": 0}},
        {"index": 1, "codec_type": "audio", "codec_name": "ac3", "disposition": {"default": 1}},
        {"index": 2, "codec_type": "video", "codec_name": "h264", "disposition": {"default": 0}},
        {"index": 3, "codec_type": "video", "codec_name": "hevc", "disposition": {"default": 1}},
    ]
    assert select_stream(streams, "audio")["codec_name"] == "ac3"
    assert select_stream(streams, "video")["codec_name"] == "hevc"


def test_parse_multiple_audio_and_subtitles():
    payload = {
        "format": {"format_name": "matroska,webm", "duration": "10.0", "bit_rate": "1000000"},
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "profile": "High",
                "width": 1280,
                "height": 720,
                "avg_frame_rate": "25/1",
                "pix_fmt": "yuv420p",
                "bit_rate": "800000",
                "display_aspect_ratio": "16:9",
                "disposition": {"default": 1},
            },
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
                "channels": 2,
                "channel_layout": "stereo",
                "sample_rate": "48000",
                "bit_rate": "128000",
                "disposition": {"default": 1},
            },
            {"index": 2, "codec_type": "audio", "codec_name": "ac3", "disposition": {"default": 0}},
            {"index": 3, "codec_type": "subtitle", "codec_name": "subrip"},
            {"index": 4, "codec_type": "subtitle", "codec_name": "ass"},
        ],
    }
    meta = parse_ffprobe_payload(payload, probe_version="test")
    assert meta.audio_stream_count == 2
    assert meta.subtitle_stream_count == 2
    assert meta.video_codec == "h264"
    assert meta.audio_codec == "aac"
    assert meta.video_width == 1280
    assert meta.video_frame_rate == 25.0
    assert meta.probe_version == "test"
    assert "streams" in meta.filtered_probe


def test_missing_values_and_audio_only():
    payload = {
        "format": {"format_name": "mp3", "duration": "N/A"},
        "streams": [
            {
                "index": 0,
                "codec_type": "audio",
                "codec_name": "mp3",
                "channels": "2",
                "sample_rate": "44100",
                "disposition": {"default": 1},
            }
        ],
    }
    meta = parse_ffprobe_payload(payload)
    assert meta.video_codec is None
    assert meta.duration_seconds is None
    assert meta.audio_codec == "mp3"


def test_no_streams_unsupported():
    with pytest.raises(UnsupportedMediaError):
        parse_ffprobe_payload({"format": {}, "streams": []})


def test_malformed_streams_type():
    with pytest.raises(ProbeParseError):
        parse_ffprobe_payload({"streams": "nope"})


def test_zero_duration_becomes_none():
    payload = {
        "format": {"format_name": "mp4", "duration": "0"},
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "width": 64,
                "height": 64,
                "disposition": {"default": 1},
            }
        ],
    }
    meta = parse_ffprobe_payload(payload)
    assert meta.duration_seconds is None
