import logging
import os
import time

import colorlog


def _get_log_level(level_str):
    levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }

    level = levels.get(level_str.upper())

    if level is None:

        raise ValueError(f"Invalid log level: {level_str!r}. Expected one of: {', '.join(levels)}")

    return level


def _cleanup_old_logs(log_dir, retention_days):
    cutoff_time = time.time() - (retention_days * 24 * 60 * 60)

    for filename in os.listdir(log_dir):
        if filename.endswith(".log"):
            filepath = os.path.join(log_dir, filename)
            last_modified_time = os.path.getmtime(filepath)
            if last_modified_time < cutoff_time:
                os.remove(filepath)


def setup_logging(config, script_path=None):
    root_logger = logging.getLogger()

    # Clear existing handlers to prevent duplicates on re-initialization
    for handler in list(root_logger.handlers):

        handler.close()

        root_logger.removeHandler(handler)

    stdout_config = config["logging"]["stdout"]
    file_config = config["logging"]["file"]
    enabled_levels = []

    if stdout_config["enabled"]:
        stdout_handler = logging.StreamHandler()
        stdout_handler.setLevel(_get_log_level(stdout_config["level"]))
        stdout_handler.setFormatter(
            colorlog.ColoredFormatter(
                fmt=stdout_config["format"],
                datefmt=stdout_config["date_format"],
                log_colors={
                    "DEBUG": "cyan",
                    "INFO": "green",
                    "WARNING": "yellow",
                    "ERROR": "red",
                    "CRITICAL": "red,bg_white",
                },
            )
        )
        root_logger.addHandler(stdout_handler)
        enabled_levels.append(_get_log_level(stdout_config["level"]))

    if file_config["enabled"]:
        if script_path:
            script_dir = os.path.dirname(os.path.abspath(script_path))
            log_dir = os.path.join(script_dir, file_config["directory"])
        else:
            log_dir = file_config["directory"]

        os.makedirs(log_dir, exist_ok=True)
        _cleanup_old_logs(log_dir, file_config["retention_days"])

        log_filename = time.strftime("%Y-%m-%d_%H-%M-%S.log")
        log_path = os.path.join(log_dir, log_filename)

        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(_get_log_level(file_config["level"]))
        file_handler.setFormatter(
            root_logger.setLevel(min(enabled_levels) if enabled_levels else logging.WARNING)
        )
        root_logger.addHandler(file_handler)
        enabled_levels.append(_get_log_level(file_config["level"]))

    root_logger.setLevel(min(enabled_levels))
    return root_logger
