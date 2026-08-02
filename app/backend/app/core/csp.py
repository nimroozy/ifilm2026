"""Content-Security-Policy builders (authoritative source for response headers).

Production is intentionally restrictive. Development loosens only what Vite HMR
requires (ws/wss + unsafe-eval for the toolchain). Do not broaden production to
silence browser noise.
"""

from __future__ import annotations

from typing import Literal

CspMode = Literal["production", "development"]


def build_csp(mode: CspMode = "production") -> str:
    """Return a single CSP policy string for the document / API responses."""
    connect = ["'self'", "blob:"]
    script = ["'self'"]
    # Radix / Tailwind use inline style attributes in both modes.
    # Google Fonts CSS is loaded by the existing SPA stylesheet imports.
    style = ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"]
    font = ["'self'", "data:", "https://fonts.gstatic.com"]

    if mode == "development":
        # Vite HMR websockets + esbuild/SWC eval in the transform pipeline.
        connect.extend(
            [
                "ws:",
                "wss:",
                "http://127.0.0.1:8000",
                "http://localhost:8000",
                "http://127.0.0.1:3000",
                "http://localhost:3000",
                "http://127.0.0.1:4173",
                "http://localhost:4173",
            ]
        )
        script.append("'unsafe-eval'")

    directives = [
        "default-src 'self'",
        f"script-src {' '.join(script)}",
        f"style-src {' '.join(style)}",
        # Favicon / optional remote artwork thumbnails use https.
        "img-src 'self' data: blob: https:",
        f"font-src {' '.join(font)}",
        f"connect-src {' '.join(connect)}",
        # Protected stream origin is same-origin (/api/stream/…). blob: for MSE.
        "media-src 'self' blob:",
        "frame-src 'self' https://www.youtube-nocookie.com https://www.youtube.com",
        "child-src 'self' https://www.youtube-nocookie.com https://www.youtube.com",
        "worker-src 'self' blob:",
        "object-src 'none'",
        "base-uri 'self'",
        "frame-ancestors 'none'",
        "form-action 'self'",
    ]
    return "; ".join(directives) + ";"


def security_header_map(*, mode: CspMode = "production") -> dict[str, str]:
    return {
        "Content-Security-Policy": build_csp(mode),
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "DENY",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    }
