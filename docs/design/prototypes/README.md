# Customer UI V2 — design prototypes

Static HTML/CSS mocks for visual review. **Not** production frontend.

## G2 Detail V2

| File | Purpose |
|------|---------|
| `detail.html?locale=en\|fa\|ps` | Movie Detail V2 (Interstellar fixture) |
| `series-detail.html?locale=en\|fa\|ps` | Series Detail V2 (Breaking Bad production artwork) |
| `series-data.json` | Series fixture |
| `capture-g2-screenshots.mjs` | Headless Chrome capture for G2 shots |
| Plan | [`../G2_DETAIL_V2_PLAN.md`](../G2_DETAIL_V2_PLAN.md) |
| Screenshots | [`../screenshots/g2/`](../screenshots/g2/) |

```bash
python3 -m http.server 8766
# open detail.html / series-detail.html with locale query
node capture-g2-screenshots.mjs
```

## G0 / G1 homepage

| File | Purpose |
|------|---------|
| `home.html?locale=en\|fa\|ps` | Homepage hero + shelves (G0) |
| `prototype.css` | Shared mock styles |
| `catalog-data.json` | Slim snapshot from `ifilm.af` |

Production homepage shipped in **G1** (`v1.15.0`). Do not treat these HTML files as runtime sources.

Artwork loads from production `/artwork/...` URLs (and TMDB profile CDN for cast). For offline captures, generate `catalog-data.local.json` + `assets/` (gitignored).
