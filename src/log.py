import os
import logging
from dotenv import load_dotenv # type: ignore
load_dotenv()

def setup_logging() -> None:
    """Setup logging from $LOG_FILE and $LOG_LEVEL environment variables."""
    try:
        log_file = os.environ["LOG_FILE"]
        log_level_env = os.environ["LOG_LEVEL"]
    except KeyError as e:
        raise RuntimeError(f"A logging environment variable is not properly set, cannot setup logging.", e)

    try:
        log_level_num = int(log_level_env)
    except ValueError:
        log_level_num = 0

    if log_level_num == 0:
        log_level = logging.CRITICAL + 1  # disables logging
    elif log_level_num == 1:
        log_level = logging.INFO
    elif log_level_num == 2:
        log_level = logging.DEBUG
    else:
        log_level = logging.CRITICAL + 1

    logging.basicConfig(
        filename=log_file,
        filemode="a",
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

# ------------------
# Wrappers
# ------------------
def debug(msg: str) -> None:
    logging.debug(msg)

def info(msg: str) -> None:
    logging.info(msg)

def warn(msg: str) -> None:
    logging.warning(msg)

def error(msg: str) -> None:
    logging.error(msg)

def critical(msg: str) -> None:
    logging.critical(msg)
