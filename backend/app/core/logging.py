import logging
import sys

logger = logging.getLogger("contentpulse")


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    logger.handlers[:] = [handler]
    logger.setLevel(level.upper())
    logger.propagate = False
    # httpx logs every request URL at INFO, and several news providers take
    # their API key as a query parameter: keep those lines out of the logs.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
