"""Regression: fake-demo cleanup preserves admins/audit under admin FK pressure."""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.core.security import hash_password
from app.models.admin import AdminRole, AdminUser
from app.models.content import Movie, Series
from app.models.media_assets import MediaAsset
from app.models.publication import MediaPublicationEvent
from app.services.demo.cleanup import build_cleanup_plan, execute_cleanup
from app.services.demo.ownership import DemoOwnership, save_ownership
from app.services.storage import ensure_media_layout
from tests.conftest import TEST_JWT


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="test",
        jwt_secret=TEST_JWT,
        database_url="sqlite://",
        playback_token_secret="playback-token-secret-for-unit-tests-32",
        artwork_root=str(tmp_path / "artwork"),
        media_root=str(tmp_path / "media"),
        _env_file=None,
    )


def test_remove_fake_demo_preserves_admin_fk_and_audit(db_session, tmp_path: Path):
    """Reproduce production FK failure mode and prove fake-only cleanup succeeds.

    Production failed on:
      media_assets_created_by_admin_id_fkey
    when cleanup tried to DELETE fixture admins still referenced by preserved
    non-demo media_assets.created_by_admin_id.
    """
    settings = _settings(tmp_path)
    ensure_media_layout()

    role = AdminRole(name="Catalog Manager", permissions=["movies:write"])
    db_session.add(role)
    db_session.flush()
    fixture_admin = AdminUser(
        username="catalog_manager",
        email="catalog_manager@ifilm.demo",
        full_name="Catalog Manager",
        hashed_password=hash_password("fixture-admin-pass-ok"),
        role_id=role.id,
        is_active=True,
    )
    db_session.add(fixture_admin)
    db_session.flush()

    fake = Movie(
        title="Solid Color Fake",
        slug="demo-solid-color-fake",
        status="published",
        metadata_source="manual",
        demo_owned=True,
        poster_url="/artwork/posters/demo-demo-solid.png",
    )
    tmdb_demo = Movie(
        title="Inception",
        slug="inception",
        tmdb_id=27205,
        status="published",
        metadata_source="tmdb",
        demo_owned=True,
        demo_seed_version="3.0.0",
    )
    nondemo = Movie(
        title="Kabul Nights",
        slug="demo-kabul-nights",
        status="published",
        metadata_source="manual",
        demo_owned=False,
        poster_url="/artwork/posters/demo-demo-kabul-nights.png",
    )
    db_session.add_all([fake, tmdb_demo, nondemo])
    db_session.flush()

    # Non-demo media still references the demo fixture admin (production pattern).
    nondemo_asset = MediaAsset(
        original_filename="kabul.mp4",
        stored_filename="kabul.mp4",
        mime_type="video/mp4",
        extension=".mp4",
        size_bytes=2048,
        category="originals",
        upload_status="completed",
        movie_id=nondemo.id,
        created_by_admin_id=fixture_admin.id,
    )
    fake_asset = MediaAsset(
        original_filename="fake.mp4",
        stored_filename="fake.mp4",
        mime_type="video/mp4",
        extension=".mp4",
        size_bytes=1024,
        category="originals",
        upload_status="completed",
        movie_id=fake.id,
        created_by_admin_id=fixture_admin.id,
    )
    db_session.add_all([nondemo_asset, fake_asset])
    db_session.flush()

    pub = MediaPublicationEvent(
        entity_type="movie",
        entity_id=fake.id,
        from_status="draft",
        to_status="published",
        actor_user_id=fixture_admin.id,
        event_type="transition",
        reason="seed publish",
        metadata_json={"source": "demo_seed"},
    )
    db_session.add(pub)
    db_session.commit()

    ownership = DemoOwnership(
        seed_version="1.0.0",
        admin_usernames=["catalog_manager"],
        admin_role_names=["Catalog Manager"],
        movie_ids=[fake.id, tmdb_demo.id, nondemo.id],
        movie_slugs=[fake.slug, tmdb_demo.slug, nondemo.slug],
        media_asset_ids=[nondemo_asset.id, fake_asset.id],
    )
    save_ownership(settings, ownership)

    fake_id = fake.id
    tmdb_id = tmdb_demo.id
    nondemo_id = nondemo.id
    admin_id = fixture_admin.id
    role_id = role.id
    nondemo_asset_id = nondemo_asset.id
    fake_asset_id = fake_asset.id
    pub_id = pub.id

    plan = build_cleanup_plan(db_session, settings, fake_only=True)
    summary = "\n".join(plan.summary_lines())
    assert "RETAIN:" in summary
    assert "TOMBSTONE" in summary
    assert "media_assets_created_by_admin_id_fkey" in summary
    assert fake_id in plan.movie_ids
    assert tmdb_id not in plan.movie_ids
    assert nondemo_id not in plan.movie_ids
    assert "catalog_manager" in plan.retained_admin_usernames
    assert plan.publication_event_ids == [pub_id]
    assert not any("Kabul Nights" in t for t in plan.movie_titles)
    assert not any("Inception" in t for t in plan.movie_titles)

    execute_cleanup(db_session, settings, plan)
    db_session.expire_all()

    assert db_session.get(Movie, fake_id) is None
    assert db_session.get(Movie, tmdb_id) is not None
    assert db_session.get(Movie, nondemo_id) is not None
    assert db_session.get(AdminUser, admin_id) is not None
    assert db_session.get(AdminRole, role_id) is not None
    assert db_session.get(MediaAsset, nondemo_asset_id) is not None
    assert db_session.get(MediaAsset, nondemo_asset_id).created_by_admin_id == admin_id
    assert db_session.get(MediaAsset, fake_asset_id) is None

    kept_pub = db_session.get(MediaPublicationEvent, pub_id)
    assert kept_pub is not None
    assert kept_pub.metadata_json is not None
    assert kept_pub.metadata_json.get("tombstone") is True
    assert kept_pub.metadata_json.get("former_entity_id") == fake_id
    assert "tombstone" in (kept_pub.reason or "").lower()

    # Idempotent second run.
    plan2 = build_cleanup_plan(db_session, settings, fake_only=True)
    assert plan2.movie_ids == []
    execute_cleanup(db_session, settings, plan2)
    assert db_session.get(Movie, tmdb_id) is not None
    assert db_session.get(AdminUser, admin_id) is not None


def test_fake_only_dry_run_never_lists_nondemo_or_tmdb(db_session, tmp_path: Path):
    settings = _settings(tmp_path)
    fake = Movie(title="Fake", slug="demo-fake", status="draft", demo_owned=True, metadata_source="")
    tmdb = Movie(
        title="Matrix",
        slug="the-matrix",
        tmdb_id=603,
        status="published",
        metadata_source="tmdb",
        demo_owned=True,
    )
    real = Movie(title="Real", slug="real", status="published", demo_owned=False)
    series_fake = Series(title="Fake Series", slug="demo-series-x", status="draft", demo_owned=True)
    series_tmdb = Series(
        title="GoT",
        slug="game-of-thrones",
        tmdb_id=1399,
        status="published",
        metadata_source="tmdb",
        demo_owned=True,
    )
    db_session.add_all([fake, tmdb, real, series_fake, series_tmdb])
    db_session.commit()

    plan = build_cleanup_plan(db_session, settings, fake_only=True)
    assert plan.movie_ids == [fake.id]
    assert plan.series_ids == [series_fake.id]
    assert real.id in plan.retained_nondemo_movie_ids
    assert tmdb.id in plan.retained_tmdb_movie_ids
    assert series_tmdb.id in plan.retained_tmdb_series_ids
