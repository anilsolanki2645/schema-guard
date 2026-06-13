import logging
import sys


def setup_logger(verbose: bool = False) -> logging.Logger:
    """
    Configure and return the schema-guard logger.

    When verbose is True, log level is set to DEBUG for detailed step-by-step output.
    When verbose is False, log level is set to WARNING (minimal output).
    """
    logger = logging.getLogger("schema_guard")

    # Avoid adding duplicate handlers if called multiple times
    if logger.handlers:
        logger.handlers.clear()

    level = logging.DEBUG if verbose else logging.WARNING
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)

    formatter = logging.Formatter("[schema-guard] %(levelname)s: %(message)s")
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    return logger


def get_logger() -> logging.Logger:
    """Get the existing schema-guard logger instance."""
    return logging.getLogger("schema_guard")
