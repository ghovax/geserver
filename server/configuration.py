"""
Configuration module for setting up global objects and their locks.

This module initializes the world and window objects, as well as their associated locks,
to ensure thread-safe operations within the application.
"""

import os
import ctypes.util
import threading
import esper

# Global objects and their locks
world_lock = threading.Lock()
esper.switch_world("default")  # Set the active world context

window_lock = threading.Lock()
window = None

# Try multiple library paths for the Assimp library
LIBRARY_PATHS = [
    "/opt/homebrew/Cellar/assimp/5.4.3/lib/libassimp.5.4.3.dylib",
    "/opt/homebrew/lib/libassimp.dylib",
    "/usr/local/lib/libassimp.dylib",
    "/usr/lib/libassimp.dylib",
]


def configure_assimp():
    """Configure the Assimp library path for loading 3D models.

    This function sets environment variables to help locate the Assimp library
    and attempts to find it using ctypes. It checks multiple predefined library paths.

    Returns:
        None
    """
    for lib_path in LIBRARY_PATHS:
        if os.path.exists(lib_path):
            os.environ["ASSIMP_LIBRARY_PATH"] = lib_path
            os.environ["DYLD_LIBRARY_PATH"] = os.path.dirname(lib_path)
            break

    # Also try to use ctypes to find the library
    assimp_path = ctypes.util.find_library("assimp")
    if assimp_path:
        os.environ["ASSIMP_PATH"] = assimp_path


import logging


class ColorCodes:
    """Class to define color codes for logging output."""

    GREY = "\x1b[38;21m"
    BLUE = "\x1b[38;5;39m"
    YELLOW = "\x1b[38;5;226m"
    RED = "\x1b[38;5;196m"
    BOLD_RED = "\x1b[31;1m"
    RESET = "\x1b[0m"


class ColoredFormatter(logging.Formatter):
    """Custom logging formatter that adds color to log messages based on severity."""

    def __init__(self, format_string):
        super().__init__(format_string)
        self.FORMATS = {
            logging.DEBUG: ColorCodes.GREY + format_string + ColorCodes.RESET,
            logging.INFO: ColorCodes.BLUE + format_string + ColorCodes.RESET,
            logging.WARNING: ColorCodes.YELLOW + format_string + ColorCodes.RESET,
            logging.ERROR: ColorCodes.RED + format_string + ColorCodes.RESET,
            logging.CRITICAL: ColorCodes.BOLD_RED + format_string + ColorCodes.RESET,
        }

    def format(self, record):
        log_format = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_format)
        return formatter.format(record)


def setup_logging():
    """Set up logging configuration for the application.

    This function configures the logging format and level, and sets up
    a colored formatter for console output.
    """
    format_str = "%(levelname)s:%(name)s:%(message)s"
    colored_formatter = ColoredFormatter(format_str)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(colored_formatter)

    logging.basicConfig(level=logging.WARNING, handlers=[stream_handler])

    # Configure Flask's logger
    flask_logger = logging.getLogger("werkzeug")
    flask_logger.setLevel(logging.INFO)

    # Configure PyAssimp logger
    pyassimp_logger = logging.getLogger("pyassimp")
    pyassimp_logger.setLevel(logging.INFO)
