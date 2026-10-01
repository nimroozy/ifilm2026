# Customer UI V2 — G0 prototypes

Static HTML/CSS mocks for visual review. **Not** production frontend.

| File | Purpose |
|---|---|
| `home.html?locale=en\|fa\|ps` | Homepage hero + shelves |
| `detail.html?locale=en\|fa\|ps` | Movie detail (Interstellar #14) |
| `prototype.css` | V2 token/layout mock styles |
| `catalog-data.json` | Slim snapshot from `ifilm.af` production APIs |
| `capture-screenshots.mjs` | Headless Chrome capture helper |

```bash
python3 -m http.server 8765
# open home.html / detail.html with locale query
```

Artwork loads from production `/artwork/...` URLs (and TMDB profile CDN for cast). For offline captures, generate `catalog-data.local.json` + `assets/` (gitignored).
