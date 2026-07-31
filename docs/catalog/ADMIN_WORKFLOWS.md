# Admin catalog workflows

## Login
1. Open `/admin/login`
2. Authenticate with an admin account (explicit `seed_dev` in development)
3. Token stored in `localStorage` key `ifilm_admin_token`
4. 401 responses clear the admin session and redirect to login

## Movies
1. `/admin/movies` — search, status/genre/year filters, pagination
2. Create via `/admin/movies/new` (URL artwork fields + preview)
3. Edit via `/admin/movies/:id/edit`
4. Publish / unpublish from list or detail actions
5. Archive/delete soft-deletes the row

## Series hierarchy
1. Create/edit series
2. Manage seasons at `/admin/series/:id/seasons` (ordered by season number)
3. Manage episodes at `/admin/seasons/:id/episodes` (ordered by episode number)
4. Publish series → publish season → publish episode (episode publish blocked otherwise)

## Genres
1. `/admin/genres` create/edit
2. Usage counts show movies/series links
3. Delete blocked while still assigned; detach or soft-delete content first

## Publishing rules
- Only `published` content appears on public endpoints
- Soft-deleted rows are hidden everywhere except internal DB state
- Artwork is URL-only in this milestone (no binary upload)
