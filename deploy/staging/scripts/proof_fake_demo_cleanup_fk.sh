#!/usr/bin/env bash
# Staging-equivalent FK cleanup proof (local postgres).
set -eu
set +H
ROOT="${IFILM_ROOT:-/workspace}"
if [[ ! -d "$ROOT/app/backend" ]]; then
  ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
fi
ART="${ART_DIR:-/opt/cursor/artifacts/pr45-cleanup}"
mkdir -p "$ART"
NAME="ifilm-staging-cleanup-proof"
PORT="${PROOF_PG_PORT:-55432}"
PGPASS="StagingProofPass2026"
export APP_ENV=staging
export DEBUG=false
export STAGING_ALLOW_FIXTURE_AUTH=true
export JWT_SECRET="staging-proof-jwt-secret-value-32chars"
export PLAYBACK_TOKEN_SECRET="staging-proof-playback-secret-32ch"
export DATABASE_URL="postgresql+psycopg2://ifilm:${PGPASS}@127.0.0.1:${PORT}/ifilm"
export REDIS_REQUIRED=false
export RADIUS_MODE=mock
export ENABLE_RADIUS_LOGIN=false
export MEDIA_ROOT="$ART/media"
export ARTWORK_ROOT="$ART/artwork"
mkdir -p "$MEDIA_ROOT" "$ARTWORK_ROOT"

proof_cleanup() {
  docker rm -f "$NAME" >/dev/null 2>&1 || true
}
trap proof_cleanup EXIT

proof_cleanup
docker run -d --name "$NAME" \
  -e "POSTGRES_PASSWORD=${PGPASS}" \
  -e POSTGRES_USER=ifilm \
  -e POSTGRES_DB=ifilm \
  -p "127.0.0.1:${PORT}:5432" \
  postgres:16-alpine >/dev/null

echo "Waiting for postgres..."
for _ in $(seq 1 60); do
  if docker exec "$NAME" pg_isready -U ifilm -d ifilm >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

cd "$ROOT/app/backend"
python - <<'PY'
import os, time
import psycopg2
url = os.environ["DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://")
for _ in range(30):
    try:
        psycopg2.connect(url).close()
        break
    except Exception:
        time.sleep(1)
else:
    raise SystemExit("postgres not ready")
print("postgres ready")
PY

python -m alembic upgrade head

python - <<'PY'
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import SessionLocal, get_engine
from app.models.admin import AdminRole, AdminUser
from app.models.content import Movie
from app.models.media_assets import MediaAsset
from app.models.publication import MediaPublicationEvent
from app.services.demo.ownership import DemoOwnership, save_ownership
from app.services.storage import ensure_media_layout

get_engine()
ensure_media_layout()
db = SessionLocal()
settings = get_settings()
role = AdminRole(name="Catalog Manager", permissions=["movies:write"])
db.add(role)
db.flush()
admin = AdminUser(
    username="catalog_manager",
    email="catalog_manager@ifilm.demo",
    full_name="Catalog Manager",
    hashed_password=hash_password("staging-proof-admin-pass"),
    role_id=role.id,
    is_active=True,
)
db.add(admin)
db.flush()
fake = Movie(title="Solid Fake", slug="demo-solid-fake", status="published", metadata_source="manual", demo_owned=True)
tmdb = Movie(title="Inception", slug="inception", tmdb_id=27205, status="published", metadata_source="tmdb", demo_owned=True, demo_seed_version="3.0.0")
nondemo = Movie(title="Kabul Nights", slug="demo-kabul-nights", status="published", metadata_source="manual", demo_owned=False)
db.add_all([fake, tmdb, nondemo])
db.flush()
nondemo_asset = MediaAsset(
    original_filename="kabul.mp4", stored_filename="kabul.mp4", mime_type="video/mp4",
    extension=".mp4", size_bytes=100, category="originals", upload_status="completed",
    movie_id=nondemo.id, created_by_admin_id=admin.id,
)
fake_asset = MediaAsset(
    original_filename="fake.mp4", stored_filename="fake.mp4", mime_type="video/mp4",
    extension=".mp4", size_bytes=100, category="originals", upload_status="completed",
    movie_id=fake.id, created_by_admin_id=admin.id,
)
db.add_all([nondemo_asset, fake_asset])
db.flush()
db.add(MediaPublicationEvent(
    entity_type="movie", entity_id=fake.id, from_status="draft", to_status="published",
    actor_user_id=admin.id, event_type="transition", reason="seed",
))
db.commit()
save_ownership(settings, DemoOwnership(
    seed_version="1.0.0",
    admin_usernames=["catalog_manager"],
    admin_role_names=["Catalog Manager"],
    movie_ids=[fake.id, tmdb.id, nondemo.id],
    media_asset_ids=[nondemo_asset.id, fake_asset.id],
))
print("SEED_OK", fake.id, tmdb.id, nondemo.id, admin.id)
PY

echo "== dry-run =="
python -m scripts.real_demo_dry_run | tee "$ART/staging_dry_run.txt"
python - <<'PY'
from pathlib import Path
t = Path("/opt/cursor/artifacts/pr45-cleanup/staging_dry_run.txt").read_text()
assert "RETAIN:" in t and "TOMBSTONE" in t
assert "Kabul Nights" not in t
assert "Solid Fake" in t
assert "catalog_manager" in t
assert "media_assets_created_by_admin_id_fkey" in t
# Inception may appear only under RETAIN tmdb counts, not DELETE movie lines
delete_section = t.split("RETAIN:")[0]
assert "Inception" not in delete_section
print("DRYRUN_ASSERT_OK")
PY

echo "== confirm =="
python -m scripts.remove_fake_demo --confirm | tee "$ART/staging_confirm.txt"
python - <<'PY'
from app.db.session import SessionLocal, get_engine
from app.models.admin import AdminUser
from app.models.content import Movie
from app.models.media_assets import MediaAsset
from app.models.publication import MediaPublicationEvent
get_engine()
db = SessionLocal()
assert db.query(Movie).filter(Movie.slug == "demo-solid-fake").count() == 0
assert db.query(Movie).filter(Movie.slug == "inception").count() == 1
assert db.query(Movie).filter(Movie.slug == "demo-kabul-nights").count() == 1
assert db.query(AdminUser).filter(AdminUser.username == "catalog_manager").count() == 1
assert db.query(MediaAsset).filter(MediaAsset.original_filename == "kabul.mp4").count() == 1
assert db.query(MediaAsset).filter(MediaAsset.original_filename == "fake.mp4").count() == 0
pub = db.query(MediaPublicationEvent).one()
assert pub.metadata_json and pub.metadata_json.get("tombstone") is True
print("CONFIRM_ASSERT_OK")
PY

echo "== idempotent confirm =="
python -m scripts.remove_fake_demo --confirm | tee "$ART/staging_confirm2.txt"
python - <<'PY'
from app.db.session import SessionLocal, get_engine
from app.models.admin import AdminUser
from app.models.content import Movie
get_engine()
db = SessionLocal()
assert db.query(Movie).filter(Movie.demo_owned.is_(True), Movie.metadata_source == "tmdb").count() == 1
assert db.query(Movie).filter(Movie.demo_owned.is_(False)).count() == 1
assert db.query(AdminUser).count() == 1
print("IDEMPOTENT_OK")
PY

echo "STAGING_PROOF_OK" | tee "$ART/staging_proof_status.txt"
