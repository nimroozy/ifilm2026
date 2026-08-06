# Demo data seed (staging / UI validation)

Safe, idempotent demo catalog for reviewing the iFilm UI end-to-end.  
**Does not enable live Radius. Does not modify JWT/DB/Radius secrets. Does not delete real catalog rows.**

## Commands

Inside the API container (runtime.env sourced):

```bash
DEMO_SEED_ALLOW_PROD=true python -m scripts.seed_demo
python -m scripts.real_demo_dry_run      # dry-run summary (demo-owned only)
python -m scripts.remove_fake_demo       # dry-run alias
python -m scripts.remove_demo            # dry-run
python -m scripts.remove_fake_demo --confirm  # delete demo-owned data only
python -m scripts.remove_demo --confirm  # same cleanup path
```

On a Compose host:

```bash
sudo bash /opt/ifilm/current/packaging/scripts/run_demo_seed.sh
# TMDB-backed realistic catalog (v3):
sudo bash /opt/ifilm/current/packaging/scripts/run_real_demo_seed.sh
```

## Identity

Demo subscribers authenticate with local Argon2 hashes via:

- `SUBSCRIBER_IDENTITY_MODE=demo`
- `DEMO_ALLOW_LOCAL_AUTH=true`

This is **not** fixture auth and **not** live SAS Radius.

## Credentials

Generated passwords are written only to:

- container: `/data/artwork/.demo/credentials.txt`
- host (via wrapper): `/root/ifilm-demo-credentials.txt` (`chmod 600`)

Passwords are never printed by the seed command.

## Markers

`app_settings` keys:

- `DEMO_DATA_INSTALLED=true`
- `DEMO_SEED_VERSION`
- `DEMO_SEED_COMMIT_SHA`
- `DEMO_SEED_INSTALLED_AT`

Ownership JSON: `{ARTWORK_ROOT}/.demo/ownership.json`

## Cleanup

`python -m scripts.remove_demo` always prints a dry-run summary first.  
`--confirm` deletes only demo-owned users/content/media/files tracked by ownership (plus `demo-` slug fallback).
