import os
import sys
import logging
from dotenv import load_dotenv
load_dotenv()

def setup_logging() -> None:
    """Setup logging from $LOG_FILE and $LOG_LEVEL environment variables."""
    try:
        log_file = os.environ["LOG_FILE"]
        log_level_env = os.environ["LOG_LEVEL"]
        # Resolve to absolute path so we can check existence and permissions.
        full_path = os.path.abspath(log_file)
        parent_dir = os.path.dirname(full_path) or os.getcwd()

        if not os.path.isdir(parent_dir):
            raise KeyError(f"LOG_FILE parent directory does not exist: {parent_dir}")

        # Require that the log file already exists and is a regular file.
        # Do NOT allow automatic creation of the file; exit if missing.
        if not os.path.exists(full_path) or not os.path.isfile(full_path):
            raise KeyError(f"LOG_FILE does not exist: {full_path}")

        if not os.access(full_path, os.W_OK):
            raise KeyError(f"LOG_FILE is not writable: {full_path}")
    except KeyError as e:
        print(f"A logging environment variable is not properly set; cannot set up logging.", e)
        sys.exit(1)

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
        filename=full_path,
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
