"""Language normalization and catalog availability semantics."""

from __future__ import annotations

from app.services.catalog_availability import (
    build_audio_availability,
    build_subtitle_availability,
    derive_dubbed_languages,
    item_has_dub,
    item_has_subtitles,
)
from app.services.languages import (
    language_label,
    normalize_language_code,
    normalize_language_list,
    resolve_original_language_code,
)
from app.services.media_processing.parser import filter_probe_json, parse_ffprobe_payload


def test_normalize_aliases_keep_dari_and_persian_distinct():
    assert normalize_language_code("Persian") == "fa"
    assert normalize_language_code("Farsi") == "fa"
    assert normalize_language_code("Dari") == "prs"
    assert normalize_language_code("Pashto") == "ps"
    assert normalize_language_code("Pushto") == "ps"
    assert normalize_language_code("en") == "en"
    assert normalize_language_code("English") == "en"
    assert normalize_language_code("fa") != normalize_language_code("Dari")


def test_normalize_list_dedupes_and_handles_unknown():
    assert normalize_language_list(["English", "en", "Persian", "Farsi", "xx-unknown"]) == [
        "en",
        "fa",
        "xx",
    ]
    assert normalize_language_list(None) == []
    assert normalize_language_list("") == []
    assert language_label("fa") == "Persian"
    assert language_label("zz") == "zz"


def test_original_language_from_tmdb_does_not_invent_audio():
    code, source = resolve_original_language_code(
        language="English",
        spoken_languages=[{"iso_639_1": "en", "name": "English"}],
        metadata_source="tmdb",
    )
    assert code == "en"
    assert source == "tmdb_metadata"
    audio = build_audio_availability(
        language="English",
        spoken_languages=[{"iso_639_1": "en"}],
        metadata_source="tmdb",
    )
    assert audio.original_language == "en"
    assert audio.languages == []
    assert audio.dubbed_languages == []
    assert audio.source == "tmdb_metadata"
    assert not item_has_dub(audio)


def test_english_plus_persian_dub():
    audio = build_audio_availability(
        language="English",
        admin_audio=["English", "Persian"],
        admin_dubbed=["Persian"],
    )
    assert audio.original_language == "en"
    assert audio.languages == ["en", "fa"]
    assert audio.dubbed_languages == ["fa"]
    assert audio.source == "admin_metadata"
    assert item_has_dub(audio)


def test_persian_original_not_dubbed_when_only_persian_audio():
    audio = build_audio_availability(
        language="Persian",
        admin_audio=["Persian"],
        admin_dubbed=["Persian"],
    )
    assert audio.original_language == "fa"
    assert audio.dubbed_languages == []
    assert not item_has_dub(audio)


def test_dari_original_pashto_dub():
    audio = build_audio_availability(
        language="Dari",
        admin_audio=["Dari", "Pashto"],
        admin_dubbed=["Pashto"],
    )
    assert audio.original_language == "prs"
    assert audio.dubbed_languages == ["ps"]
    assert "prs" in audio.languages
    assert "ps" in audio.languages


def test_subtitles_from_admin_not_from_translated_metadata():
    subs = build_subtitle_availability(admin_subtitles=["English", "Persian"])
    assert subs.languages == ["en", "fa"]
    assert subs.source == "admin_metadata"
    assert item_has_subtitles(subs)
    empty = build_subtitle_availability()
    assert not item_has_subtitles(empty)


def test_probe_languages_priority_over_admin():
    probe = {
        "streams": [
            {
                "codec_type": "audio",
                "tags": {"language": "eng"},
                "disposition": {"default": 1, "dub": 0},
            },
            {
                "codec_type": "audio",
                "tags": {"language": "fas"},
                "disposition": {"default": 0, "dub": 1},
            },
            {
                "codec_type": "subtitle",
                "tags": {"language": "per"},
                "disposition": {"default": 0},
            },
        ]
    }
    audio = build_audio_availability(
        language="English",
        admin_audio=["Dari"],  # ignored when probe languages present
        admin_dubbed=["Persian"],
        probe_json=probe,
        audio_stream_count=2,
    )
    assert audio.source == "media_probe"
    assert audio.languages == ["en", "fa"]
    assert audio.dubbed_languages == ["fa"]
    assert audio.track_count == 2
    assert audio.selectable_in_player is False  # packaging deferred

    subs = build_subtitle_availability(
        admin_subtitles=["English"],
        probe_json=probe,
        subtitle_stream_count=1,
    )
    assert subs.source == "media_probe"
    assert subs.languages == ["fa"]
    assert subs.selectable_in_player is False


def test_legacy_probe_without_tags_does_not_invent_languages():
    # Old probe_json without tags key — count only
    probe = {"streams": [{"codec_type": "audio", "disposition": {"default": 1}}]}
    audio = build_audio_availability(
        language="English",
        metadata_source="tmdb",
        probe_json=probe,
        audio_stream_count=1,
    )
    # No tags → not probe_language_ready; falls through to original-only / admin
    assert audio.languages == []
    assert audio.original_language == "en"
    assert audio.dubbed_languages == []


def test_filter_probe_json_retains_language_tags():
    raw = {
        "format": {"format_name": "matroska"},
        "streams": [
            {
                "index": 0,
                "codec_type": "audio",
                "codec_name": "aac",
                "tags": {"language": "prs", "title": "Dari"},
                "disposition": {"default": 1, "dub": 0, "forced": 0},
            }
        ],
    }
    filtered = filter_probe_json(raw)
    assert filtered["streams"][0]["tags"]["language"] == "prs"
    assert filtered["streams"][0]["disposition"]["dub"] == 0
    meta = parse_ffprobe_payload(raw, probe_version="ffprobe-json-v2")
    assert meta.audio_track_languages == ["prs"]


def test_derive_dubbed_requires_mark_and_difference():
    assert derive_dubbed_languages(
        audio_languages=["en", "fa"],
        original_language="en",
        admin_dubbed=["fa"],
    ) == ["fa"]
    assert (
        derive_dubbed_languages(
            audio_languages=["en", "fa"],
            original_language="en",
            admin_dubbed=[],
        )
        == []
    )
