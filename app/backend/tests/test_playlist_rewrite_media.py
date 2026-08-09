"""EXT-X-MEDIA URI rewriting for multi-audio / subtitle masters."""

from __future__ import annotations

from app.services.streaming.playlist_rewrite import rewrite_master_playlist


def test_rewrite_master_rewrites_ext_x_media_uris():
    master = """#EXTM3U
#EXT-X-VERSION:4
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="English",LANGUAGE="en",DEFAULT=YES,AUTOSELECT=YES,URI="audio_en/index.m3u8"
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="Persian Dub",LANGUAGE="fa",DEFAULT=NO,AUTOSELECT=YES,URI="audio_fa/index.m3u8"
#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="English",LANGUAGE="en",DEFAULT=NO,AUTOSELECT=YES,URI="subs_en/index.m3u8"
#EXT-X-STREAM-INF:BANDWIDTH=400000,RESOLUTION=426x240,AUDIO="audio",SUBTITLES="subs"
240p/index.m3u8
"""
    out = rewrite_master_playlist(master, stream_base="/api/stream/tokensecret/master")
    assert 'URI="/api/stream/tokensecret/master/audio_en/index.m3u8"' in out
    assert 'URI="/api/stream/tokensecret/master/audio_fa/index.m3u8"' in out
    assert 'URI="/api/stream/tokensecret/master/subs_en/index.m3u8"' in out
    assert "/api/stream/tokensecret/master/240p/index.m3u8" in out
    assert "packages/" not in out
    assert ".." not in out


def test_rewrite_master_rejects_parent_traversal_in_media_uri():
    master = """#EXTM3U
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="Bad",LANGUAGE="en",URI="../escape/index.m3u8"
#EXT-X-STREAM-INF:BANDWIDTH=400000
240p/index.m3u8
"""
    out = rewrite_master_playlist(master, stream_base="/api/stream/tok/m")
    # Parent traversal URI is left untouched (not rewritten onto stream base).
    assert "../escape" in out or 'URI="../escape/index.m3u8"' in out
    assert "/api/stream/tok/m/../" not in out
