from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.admin import AdminRole, AdminUser
from app.models.cdn import Branch, CDNNode
from app.models.content import Movie, Series
from app.models.user import Subscriber


SUPER_PERMISSIONS = [
    "dashboard",
    "movies",
    "series",
    "upload",
    "encoding",
    "cdn",
    "users",
    "branches",
    "reports",
    "settings",
]


def bootstrap_data(db: Session) -> None:
    settings = get_settings()

    role = db.query(AdminRole).filter(AdminRole.name == "Super Admin").one_or_none()
    if role is None:
        role = AdminRole(name="Super Admin", permissions=SUPER_PERMISSIONS)
        db.add(role)
        db.flush()

    admin = db.query(AdminUser).filter(AdminUser.username == settings.admin_bootstrap_username).one_or_none()
    if admin is None:
        admin = AdminUser(
            username=settings.admin_bootstrap_username,
            email=settings.admin_bootstrap_email,
            full_name="iFilm Admin",
            hashed_password=hash_password(settings.admin_bootstrap_password),
            role_id=role.id,
            is_active=True,
        )
        db.add(admin)

    if db.query(Subscriber).filter(Subscriber.username == "mobin_user_001").one_or_none() is None:
        db.add(
            Subscriber(
                username="mobin_user_001",
                hashed_password=hash_password("password"),
                name="Ahmad Karimi",
                branch="Kabul",
                status="active",
                package="Premium 50Mbps",
                expiration="2026-12-31",
                radius_synced=True,
            )
        )

    if db.query(CDNNode).count() == 0:
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

    if db.query(Branch).count() == 0:
        db.add(
            Branch(
                name="Kabul",
                code="KBL",
                cdn="Kabul CDN",
                ip_ranges="10.1.0.0/16",
                cdn_status="healthy",
            )
        )

    if db.query(Movie).count() == 0:
        db.add(
            Movie(
                title="The Last Caravan",
                original_title="آخرین کاروان",
                year=2024,
                duration=128,
                rating=8.4,
                age_rating="PG-13",
                genres=["Drama", "Adventure"],
                country="Afghanistan",
                language="Dari",
                director="Ahmad Zahir",
                cast=["Farhad Darya", "Leena Alam"],
                description="A sweeping epic about a merchant caravan crossing the Hindu Kush.",
                poster="https://placehold.co/300x450/4a1942/e8a838?text=Last+Caravan",
                backdrop="https://placehold.co/1920x800/4a1942/e8a838?text=The+Last+Caravan",
                audio=["Dari", "Pashto"],
                subtitles=["English", "Dari", "Pashto"],
                qualities=["1080p", "720p", "480p"],
                dubbed=["Persian"],
                featured=True,
                views=45200,
            )
        )

    if db.query(Series).count() == 0:
        db.add(
            Series(
                title="The Bazaar",
                original_title="بازار",
                year=2024,
                rating=8.6,
                age_rating="PG-13",
                genres=["Drama", "Crime"],
                country="Afghanistan",
                language="Dari",
                seasons=3,
                episode_count=30,
                status="Ongoing",
                description="Interconnected lives of merchants in Kabul's oldest bazaar.",
                poster="https://placehold.co/300x450/1a1a2e/e8a838?text=The+Bazaar",
                backdrop="https://placehold.co/1920x800/1a1a2e/e8a838?text=The+Bazaar",
                audio=["Dari", "Pashto"],
                subtitles=["English", "Dari", "Pashto"],
                dubbed=["Persian"],
                new_episode=True,
                views=156000,
            )
        )

    db.commit()
