
"""Application configuration and logging setup."""

import logging


def configure_logging(level: int = logging.INFO) -> None:
    """Configure readable application logs for development."""
    logging.basicConfig(
        level=level,
        format=(
            "%(asctime)s | %(levelname)-8s | "
            "%(name)s | %(message)s"
        ),
        datefmt="%H:%M:%S",
    )
