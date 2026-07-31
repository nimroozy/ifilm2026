"""CLI entry: python -m app.workers.media_processing"""

from __future__ import annotations

import logging
import sys

from app.core.config import get_settings
from app.services.media_processing.worker import run_forever


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [media-processing] %(message)s",
        stream=sys.stdout,
    )
    settings = get_settings()
    run_forever(settings=settings)


if __name__ == "__main__":
    main()
