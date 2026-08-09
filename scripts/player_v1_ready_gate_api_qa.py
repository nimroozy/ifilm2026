#!/usr/bin/env python3
"""API-level Ready Gate checks for Player Experience V1 (PR #62)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

API = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8020/api"
FIX = Path("/tmp/ifilm-player-v1-verify.json")
OUT = Path("/opt/cursor/artifacts/pr62-ready-gate-api.json")
OUT.parent.mkdir(parents=True, exist_ok=True)


def main() -> int:
    fixture = json.loads(FIX.read_text(encoding="utf-8"))
    sub = fixture["subscriber"]["token"]
    admin = fixture["admin"]["token"]
    movie_a = fixture["movie_a"]
    movie_b = fixture["movie_b"]
    episode = fixture["episode"]
    report: dict = {"api": API, "checks": [], "ok": True}

    def check(name: str, cond: bool, detail: object = None) -> None:
        report["checks"].append({"name": name, "ok": bool(cond), "detail": detail})
        if not cond:
            report["ok"] = False

    with httpx.Client(timeout=30.0) as client:
        # Catalog availability
        ma = client.get(f"{API}/movies/{movie_a['id']}").json()
        check(
            "movie_a_playable",
            ma.get("playable") is True,
            {"playable": ma.get("playable"), "audio": ma.get("audio_availability")},
        )
        audio = ma.get("audio_availability") or {}
        check("movie_a_audio_langs", set(audio.get("languages") or []) == {"en", "fa", "ps"}, audio)
        check(
            "movie_a_dubbed_langs",
            set(audio.get("dubbed_languages") or []) == {"fa", "ps"},
            audio,
        )
        check("movie_a_selectable", audio.get("selectable_in_player") is True, audio)
        check("movie_a_no_persian_literal_in_api", "دوبله" not in json.dumps(ma, ensure_ascii=False))

        mb = client.get(f"{API}/movies/{movie_b['id']}").json()
        check("movie_b_playable", mb.get("playable") is True, mb.get("audio_availability"))
        b_audio = mb.get("audio_availability") or {}
        check(
            "movie_b_not_multi_selectable",
            b_audio.get("selectable_in_player") is False or len(b_audio.get("languages") or []) <= 1,
            b_audio,
        )

        # Unauthorized session
        unauth = client.post(
            f"{API}/playback/sessions",
            json={"content_type": "movie", "content_id": movie_a["id"]},
        )
        check("session_requires_auth", unauth.status_code in {401, 403}, unauth.status_code)

        # Create session movie A
        sess = client.post(
            f"{API}/playback/sessions",
            headers={"Authorization": f"Bearer {sub}"},
            json={"content_type": "movie", "content_id": movie_a["id"]},
        )
        check("session_movie_a", sess.status_code == 201, sess.status_code)
        body = sess.json()
        check("session_has_audio_tracks", len(body.get("audio_tracks") or []) == 3, body.get("audio_tracks"))
        check(
            "session_has_subtitle_tracks",
            len(body.get("subtitle_tracks") or []) == 3,
            body.get("subtitle_tracks"),
        )
        check(
            "session_tracks_use_codes_not_ui",
            all("دوبله" not in json.dumps(t, ensure_ascii=False) for t in body.get("audio_tracks") or []),
            body.get("audio_tracks"),
        )
        check("session_no_storage_path", "packages/" not in json.dumps(body) and "MEDIA_ROOT" not in json.dumps(body))
        token = body["playback_token"]
        master_url = body["master_playlist_url"]
        if master_url.startswith("/"):
            master_url = API.replace("/api", "") + master_url

        master = client.get(master_url)
        check("master_200", master.status_code == 200, master.status_code)
        text = master.text
        check("master_has_ext_x_media_audio", "#EXT-X-MEDIA:TYPE=AUDIO" in text)
        check("master_has_ext_x_media_subs", "#EXT-X-MEDIA:TYPE=SUBTITLES" in text)
        check("master_one_default_audio", text.count("DEFAULT=YES") == 1, text.count("DEFAULT=YES"))
        check("master_rewrites_audio_uri", "/audio_en/index.m3u8" in text and "URI=" in text)
        check("master_no_packages_path", "packages/" not in text and ".." not in text)
        report["master_excerpt"] = "\n".join(text.splitlines()[:14])

        # Fetch audio + subtitle playlists via rewritten URIs
        base = master_url.rsplit("/", 1)[0]
        for label in ("audio_en", "audio_fa", "audio_ps", "subs_en", "subs_fa", "subs_ps", "240p"):
            r = client.get(f"{base}/{label}/index.m3u8")
            check(f"playlist_{label}", r.status_code == 200, r.status_code)

        # Missing rendition fails without crashing
        missing = client.get(f"{base}/audio_missing/index.m3u8")
        check("missing_rendition_not_200", missing.status_code in {400, 404}, missing.status_code)
        check("missing_no_fs_path_leak", "/tmp/" not in missing.text and "packages/" not in missing.text)

        # Segment delivery
        seg_list = client.get(f"{base}/audio_en/index.m3u8").text
        seg_name = None
        for line in seg_list.splitlines():
            if line and not line.startswith("#") and line.endswith(".ts"):
                seg_name = line.rsplit("/", 1)[-1]
                break
        if seg_name:
            seg = client.get(f"{base}/audio_en/{seg_name}")
            check("audio_segment_200", seg.status_code == 200, seg.status_code)
        else:
            check("audio_segment_200", False, "no segment in playlist")

        vtt = client.get(f"{base}/subs_fa/cue.vtt")
        check("subtitle_vtt_200", vtt.status_code == 200, vtt.status_code)
        check("subtitle_vtt_has_persian", "فارسی" in vtt.text, vtt.text[:200])

        # Movie B session — no multi tracks metadata required
        sess_b = client.post(
            f"{API}/playback/sessions",
            headers={"Authorization": f"Bearer {sub}"},
            json={"content_type": "movie", "content_id": movie_b["id"]},
        )
        check("session_movie_b", sess_b.status_code == 201, sess_b.status_code)
        body_b = sess_b.json()
        check("movie_b_no_extra_audio_tracks", len(body_b.get("audio_tracks") or []) == 0, body_b.get("audio_tracks"))

        # Episode session
        sess_e = client.post(
            f"{API}/playback/sessions",
            headers={"Authorization": f"Bearer {sub}"},
            json={"content_type": "episode", "content_id": episode["id"]},
        )
        check("session_episode", sess_e.status_code == 201, sess_e.status_code)
        body_e = sess_e.json()
        check("episode_audio_tracks", len(body_e.get("audio_tracks") or []) == 3, body_e.get("audio_tracks"))

        # Watch progress resume
        asset_a = movie_a["asset_id"]
        put = client.put(
            f"{API}/me/watch-progress/{asset_a}",
            headers={"Authorization": f"Bearer {sub}"},
            json={
                "position_seconds": 45,
                "duration_seconds": 90,
                "playback_session_id": body["id"],
                "event_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )
        check("progress_save", put.status_code == 200, put.status_code)
        got = client.get(
            f"{API}/me/watch-progress/{asset_a}",
            headers={"Authorization": f"Bearer {sub}"},
        )
        check(
            "progress_load",
            got.status_code == 200 and float(got.json().get("position_seconds") or 0) >= 40,
            got.json(),
        )
        cw = client.get(f"{API}/me/continue-watching", headers={"Authorization": f"Bearer {sub}"})
        check("continue_watching", cw.status_code == 200)
        cw_ids = {item.get("media_asset_id") for item in cw.json()}
        check("continue_watching_contains_movie_a", asset_a in cw_ids, list(cw_ids))

        # Episode progress isolation
        asset_e = episode["asset_id"]
        put_e = client.put(
            f"{API}/me/watch-progress/{asset_e}",
            headers={"Authorization": f"Bearer {sub}"},
            json={
                "position_seconds": 50,
                "duration_seconds": 90,
                "playback_session_id": body_e["id"],
                "event_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )
        check("episode_progress_save", put_e.status_code == 200, put_e.status_code)
        got_e = client.get(
            f"{API}/me/watch-progress/{asset_e}",
            headers={"Authorization": f"Bearer {sub}"},
        )
        check(
            "episode_progress_isolated",
            got_e.json().get("media_asset_id") == asset_e
            and float(got_e.json().get("position_seconds") or 0) >= 45
            and got_e.json().get("episode_number") == 3,
            got_e.json(),
        )

        # Admin track CRUD
        listed = client.get(
            f"{API}/admin/media/assets/{asset_a}/tracks",
            headers={"Authorization": f"Bearer {admin}"},
        )
        check("admin_list_tracks", listed.status_code == 200, listed.status_code)
        items = listed.json().get("items") or []
        check("admin_tracks_count", len(items) >= 6, len(items))

        # Default conflict: set second audio default clears first
        fa = next(t for t in items if t["track_type"] == "audio" and t["language_code"] == "fa")
        en = next(t for t in items if t["track_type"] == "audio" and t["language_code"] == "en")
        patched = client.patch(
            f"{API}/admin/media/tracks/{fa['id']}",
            headers={"Authorization": f"Bearer {admin}"},
            json={"is_default": True},
        )
        check("admin_set_default", patched.status_code == 200, patched.status_code)
        listed2 = client.get(
            f"{API}/admin/media/assets/{asset_a}/tracks",
            headers={"Authorization": f"Bearer {admin}"},
            ).json()["audio"]
        defaults = [t for t in listed2 if t["is_default"]]
        check("admin_single_default_audio", len(defaults) == 1 and defaults[0]["language_code"] == "fa", defaults)
        # restore en default
        client.patch(
            f"{API}/admin/media/tracks/{en['id']}",
            headers={"Authorization": f"Bearer {admin}"},
            json={"is_default": True},
        )

        # Forbidden without permission
        forbidden = client.post(
            f"{API}/admin/media/assets/{asset_a}/tracks",
            headers={"Authorization": f"Bearer {sub}"},
            json={"track_type": "audio", "language_code": "ar"},
        )
        check("admin_tracks_rbac", forbidden.status_code in {401, 403}, forbidden.status_code)

        # Content requests / browse still OK
        movies = client.get(f"{API}/movies")
        check("browse_movies", movies.status_code == 200 and movies.json()["meta"]["total"] >= 2)
        series = client.get(f"{API}/series")
        check("browse_series", series.status_code == 200)

    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    failed = [c for c in report["checks"] if not c["ok"]]
    print(json.dumps({"ok": report["ok"], "failed": failed, "passed": len(report["checks"]) - len(failed), "out": str(OUT)}, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
