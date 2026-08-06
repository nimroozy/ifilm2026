# TMDB-backed demo catalog

The realistic demo catalog can import metadata and artwork from TMDB, then serve
the public catalog from local database/artwork rows even if TMDB is later
offline.

Current curated seed version: **3.0.0** (≥15 movies, ≥5 series, ≥6 movie demo
clips, ≥6 episode demo clips). Records are marked `demo_owned=true` with
`demo_seed_version=3.0.0`.

## Environment

Set these only on hosts where the TMDB demo import/admin tooling is needed:

```env
TMDB_ENABLED=true
TMDB_API_READ_TOKEN=
TMDB_IMAGE_BASE_URL=https://image.tmdb.org/t/p/
TMDB_LANGUAGE=en-US
TMDB_FALLBACK_LANGUAGE=en-US
TMDB_REQUEST_TIMEOUT_SECONDS=15
TMDB_CACHE_TTL_SECONDS=86400
```

Do not commit real TMDB tokens. Keep live Radius and CDN feature flags on their
normal deployment defaults; the TMDB demo seed does not enable Radius or start
CDN work.

## Seed, dry-run, and cleanup

On a Compose host (recommended):

```bash
# Token must already be present in /etc/ifilm/ifilm.env
sudo bash /opt/ifilm/current/packaging/scripts/run_real_demo_seed.sh
```

From inside the API container runtime environment:

```bash
set -a; . /run/ifilm/runtime.env; set +a

# Dry-run: list fake-demo rows that would be removed (never deletes).
# Retains TMDB real demo, non-demo catalog, admins, and audit tombstones.
python -m scripts.real_demo_dry_run
# Alias of remove_demo --fake-only without --confirm
python -m scripts.remove_fake_demo

# Apply fake-demo cleanup only (preserves TMDB demo catalog + admins/audit)
python -m scripts.remove_fake_demo --confirm

DEMO_SEED_ALLOW_PROD=true python -m scripts.seed_real_demo
python -m scripts.refresh_real_demo_metadata
```

Use `DEMO_SKIP_MEDIA=1` or `--skip-media` to skip synthetic Demo Clip media
generation. Generated media is synthetic ffmpeg output only, burns in a visible
`iFilm Demo Playback Clip` overlay, and carries matching title metadata.

## Media policy

- TMDB artwork downloads are allowlisted to TMDB image hosts and stored under
  `/artwork`.
- Trailers store YouTube metadata/embed URLs only (`youtube-nocookie.com`).
- Do not use `yt-dlp`; do not download, rehost, or transcode commercial trailer
  media.
- Admin imports are created as drafts and are never auto-published.
- For titles with only a synthetic demo clip, the public UI shows **Play Demo Clip**
  (never “Watch Full Movie”). Titles without a local package show **Watch Trailer**
  and/or **Full Movie Unavailable**.
