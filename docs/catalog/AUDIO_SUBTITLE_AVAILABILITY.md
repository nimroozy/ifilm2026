# Catalog audio / subtitle availability

## Source of truth

| Field | Location | Classification |
| --- | --- | --- |
| `language` | movies/series | Admin + TMDB display language (not a track proof) |
| `spoken_languages` | movies/series | TMDB import; unused for dub/sub claims |
| `audio`, `subtitles`, `dubbed` | movies/series JSON | Manually administered catalog claims |
| `audio_stream_count`, `subtitle_stream_count` | media_assets | Probe-derived counts |
| `probe_json.streams[].tags.language` | media_assets | Probe-derived track languages (v2+) |
| Package HLS tracks | media_packages | **Deferred** — encoder maps `0:a:0` only |

There is **no** `original_language` DB column. Original language is resolved from
`language` / `spoken_languages` at serialization time.

## Public API shape (backward compatible)

Legacy arrays (`audio`, `subtitles`, `dubbed`) remain.

New fields on movie / series / episode responses:

```json
{
  "audio_availability": {
    "original_language": "en",
    "languages": ["en", "fa"],
    "dubbed_languages": ["fa"],
    "track_count": null,
    "source": "admin_metadata",
    "selectable_in_player": false
  },
  "subtitle_availability": {
    "languages": ["en"],
    "track_count": null,
    "source": "admin_metadata",
    "selectable_in_player": false
  }
}
```

`source` ∈ `media_probe | package_manifest | admin_metadata | tmdb_metadata | unknown`

### Priority
1. `package_manifest` (not emitted until multi-track packaging ships)
2. `media_probe`
3. `admin_metadata`
4. `tmdb_metadata` — **original language only**
5. `unknown`

TMDB never invents local dub or subtitle availability.

### Dubbing rule
Dubbed only when an audio language differs from the original **and** is marked
as a dub (admin `dubbed` list and/or probe `disposition.dub`).

### Filters
`GET /api/movies?has_dubbed=true` and `?has_subtitles=true` (same on `/api/series`).

## Player

Local packaging does not emit `EXT-X-MEDIA` audio/subtitle groups yet.
`selectable_in_player` is therefore `false` for packaged content.
HLS.js selectors remain wired for external manifests that already carry tracks.
Multi-track packaging is deferred (see `docs/media/HLS_ENCODING_PIPELINE.md`).

## Language codes

Canonical: `en`, `fa`, `prs` (Dari), `ps`, `ar`, `hi`, `ur`, `ko`, `ja`, `zh`, `tr`, `ru`.

Dari and Persian/Farsi are **not** merged.
