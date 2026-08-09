"""Public Vite env keys allowed in the customer/admin SPA bundle.

Secrets (JWT, playback HMAC, DB, Redis, bootstrap passwords) must never appear
as VITE_* variables. See docs/security/SECRET_HYGIENE.md.
"""

from __future__ import annotations

# Keep in sync with app/frontend/src/vite-env.d.ts
FRONTEND_PUBLIC_ENV_KEYS: frozenset[str] = frozenset(
    {
        "VITE_API_BASE_URL",
        "VITE_DATA_MODE",
        "VITE_APP_TITLE",
        "VITE_APP_DESCRIPTION",
        "VITE_APP_LOGO_URL",
        "VITE_SITE_URL",
        "VITE_TWITTER_SITE",
        "VITE_TWITTER_CREATOR",
        "VITE_APP_VERSION",
        "VITE_PORT",
    }
)
