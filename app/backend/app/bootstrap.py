"""Explicit development seed helpers.

Never invoked automatically on API startup.
"""

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.runtime import require_admin_bootstrap_password
from app.core.security import hash_password
from app.models.admin import AdminRole, AdminUser
from app.models.cdn import Branch, CDNNode
from app.models.content import Genre, Movie, Series
from app.models.media_assets import new_uuid
from app.models.media_encoding import MediaEncodingProfile
from app.models.user import Subscriber
from app.services.catalog import utcnow
from app.utils.slug import normalize_slug

SUPER_PERMISSIONS = [
    "dashboard",
    "movies",
    "movies.read",
    "movies.manage",
    "series",
    "series.read",
    "series.manage",
    "genres",
    "genres.read",
    "genres.manage",
    "catalog.read",
    "catalog.edit",
    "catalog.review",
    "catalog.approve",
    "catalog.publish",
    "catalog.archive",
    "upload",
    "upload.read",
    "upload.manage",
    "processing",
    "processing.read",
    "processing.manage",
    "streaming",
    "streaming.read",
    "streaming.manage",
    "encoding",
    "cdn",
    "users",
    "branches",
    "reports",
    "settings",
]

# Default HLS ladder (same seed as migration 006_hls_encoding).
DEFAULT_ENCODING_PROFILES = [
    ("hls_240p", "240p", 240, 400_000, 64_000, 440_000, 800_000, 10),
    ("hls_360p", "360p", 360, 800_000, 96_000, 880_000, 1_600_000, 20),
    ("hls_480p", "480p", 480, 1_400_000, 128_000, 1_540_000, 2_800_000, 30),
    ("hls_720p", "720p", 720, 2_800_000, 128_000, 3_080_000, 5_600_000, 40),
    ("hls_1080p", "1080p", 1080, 5_000_000, 192_000, 5_500_000, 10_000_000, 50),
]


def seed_encoding_profiles(db: Session) -> int:
    """Insert missing default encoding profiles. Returns count inserted."""
    inserted = 0
    for name, label, height, vbr, abr, maxrate, bufsize, sort_order in DEFAULT_ENCODING_PROFILES:
        existing = (
            db.query(MediaEncodingProfile).filter(MediaEncodingProfile.name == name).one_or_none()
        )
        if existing is not None:
            continue
        db.add(
            MediaEncodingProfile(
                id=new_uuid(),
                name=name,
                label=label,
                height=height,
                video_bitrate=vbr,
                audio_bitrate=abr,
                maxrate=maxrate,
                bufsize=bufsize,
                video_codec="h264",
                audio_codec="aac",
                video_profile="main",
                preset="veryfast",
                enabled=True,
                sort_order=sort_order,
            )
        )
        inserted += 1
    if inserted:
        db.flush()
    return inserted


def _ensure_genres(db: Session, names: list[str]) -> list[Genre]:
    genres: list[Genre] = []
    for name in names:
        slug = normalize_slug(name)
        genre = db.query(Genre).filter(Genre.slug == slug).one_or_none()
        if genre is None:
            genre = Genre(name=name, slug=slug, description="")
            db.add(genre)
            db.flush()
        genres.append(genre)
    return genres


def seed_development_data(db: Session, *, include_demo_catalog: bool = True) -> None:
    settings = get_settings()
    admin_password = require_admin_bootstrap_password(settings)
    seed_encoding_profiles(db)

    role = db.query(AdminRole).filter(AdminRole.name == "Super Admin").one_or_none()
    if role is None:
        role = AdminRole(name="Super Admin", permissions=SUPER_PERMISSIONS)
        db.add(role)
        db.flush()
    else:
        # Merge newly introduced catalog permissions into existing Super Admin roles.
        merged = list(dict.fromkeys([*(role.permissions or []), *SUPER_PERMISSIONS]))
        role.permissions = merged
        db.add(role)
        db.flush()

    admin = (
        db.query(AdminUser)
        .filter(AdminUser.username == settings.admin_bootstrap_username)
        .one_or_none()
    )
    if admin is None:
        admin = AdminUser(
            username=settings.admin_bootstrap_username,
            email=settings.admin_bootstrap_email,
            full_name="iFilm Admin",
            hashed_password=hash_password(admin_password),
            role_id=role.id,
            is_active=True,
        )
        db.add(admin)
    else:
        admin.hashed_password = hash_password(admin_password)
        admin.role_id = role.id
        admin.is_active = True
        db.add(admin)

    # Optional subscriber mirror of the first mock Radius fixture (if configured).
    fixtures = settings.radius_mock_users or []
    if fixtures:
        fixture = fixtures[0]
        username = fixture.get("username")
        password = fixture.get("password")
        if username and password:
            subscriber = db.query(Subscriber).filter(Subscriber.username == username).one_or_none()
            if subscriber is None:
                db.add(
                    Subscriber(
                        username=username,
                        hashed_password=hash_password(password),
                        name=fixture.get("name") or username,
                        branch=fixture.get("branch") or "Kabul",
                        status="active",
                        package=fixture.get("package") or "Standard",
                        expiration=fixture.get("expiration") or "",
                        radius_synced=True,
                    )
                )

    if include_demo_catalog and db.query(CDNNode).count() == 0:
        db.add_all(
            [
                CDNNode(
                    name="Kabul CDN",
                    location="Kabul",
                    status="online",
                    ip="192.168.1.10",
                    base_url="",
                    storage_capacity=50000,
                    storage_used=1000,
                    health_score=98,
                    cache_hit_rate=94.0,
                    branch="Kabul",
                ),
                CDNNode(
                    name="Main Origin Server",
                    location="Kabul HQ",
                    status="online",
                    ip="10.0.0.1",
                    base_url="",
                    storage_capacity=100000,
                    storage_used=5000,
                    health_score=99,
                    cache_hit_rate=100.0,
                    branch="HQ",
                ),
            ]
        )

    if include_demo_catalog and db.query(Branch).count() == 0:
        db.add(
            Branch(
                name="Kabul",
                code="KBL",
                cdn="Kabul CDN",
                ip_ranges="10.1.0.0/16",
                cdn_status="healthy",
            )
        )

    if include_demo_catalog and db.query(Movie).count() == 0:
        movie_genres = _ensure_genres(db, ["Drama", "Adventure"])
        movie = Movie(
            title="The Last Caravan",
            original_title="آخرین کاروان",
            slug="the-last-caravan",
            release_year=2024,
            duration_minutes=128,
            imdb_rating=8.4,
            age_rating="PG-13",
            country="Afghanistan",
            language="Dari",
            director="Ahmad Zahir",
            cast=["Farhad Darya", "Leena Alam"],
            description="A sweeping epic about a merchant caravan crossing the Hindu Kush.",
            poster_url="https://placehold.co/300x450/4a1942/e8a838?text=Last+Caravan",
            backdrop_url="https://placehold.co/1920x800/4a1942/e8a838?text=The+Last+Caravan",
            audio=["Dari", "Pashto"],
            subtitles=["English", "Dari", "Pashto"],
            qualities=["1080p", "720p", "480p"],
            dubbed=["Persian"],
            is_featured=True,
            views=45200,
            status="draft",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        movie.genre_links = movie_genres
        # Demo catalog remains draft until an active HLS package exists and
        # the publishing workflow is used (Phase 9).
        db.add(movie)

    if include_demo_catalog and db.query(Series).count() == 0:
        series_genres = _ensure_genres(db, ["Drama", "Crime"])
        series = Series(
            title="The Bazaar",
            original_title="بازار",
            slug="the-bazaar",
            release_year=2024,
            imdb_rating=8.6,
            age_rating="PG-13",
            country="Afghanistan",
            language="Dari",
            airing_status="Ongoing",
            description="Interconnected lives of merchants in Kabul's oldest bazaar.",
            poster_url="https://placehold.co/300x450/1a1a2e/e8a838?text=The+Bazaar",
            backdrop_url="https://placehold.co/1920x800/1a1a2e/e8a838?text=The+Bazaar",
            audio=["Dari", "Pashto"],
            subtitles=["English", "Dari", "Pashto"],
            dubbed=["Persian"],
            new_episode=True,
            views=156000,
            status="draft",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        series.genre_links = series_genres
        # Demo series remains draft until episodes + packages are ready.
        db.add(series)

    db.commit()
