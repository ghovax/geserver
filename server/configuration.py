"""
Configuration module for setting up global objects and their locks.

This module initializes the world and window objects, as well as their associated locks,
to ensure thread-safe operations within the application.
"""

import os
import ctypes.util
import threading
import logging

# Basic logging configuration
logging.basicConfig(level=logging.INFO)

# Initialize global objects and their locks
world_lock = threading.Lock()

window_lock = threading.Lock()
window = None

# Try multiple library paths for the Assimp library
ASSIMP_LIBRARY_PATHS = [
    "/opt/homebrew/Cellar/assimp/5.4.3/lib/libassimp.5.4.3.dylib",
    "/opt/homebrew/lib/libassimp.dylib",
    "/usr/local/lib/libassimp.dylib",
    "/usr/lib/libassimp.dylib",
]


def configure_assimp_library_path():
    # Configure the Assimp library path for loading 3D models
    for library_path in ASSIMP_LIBRARY_PATHS:
        if os.path.exists(library_path):
            os.environ["ASSIMP_LIBRARY_PATH"] = library_path
            os.environ["DYLD_LIBRARY_PATH"] = os.path.dirname(library_path)
            break

    # Also try to use ctypes to find the library
    assimp_path = ctypes.util.find_library("assimp")
    if assimp_path:
        os.environ["ASSIMP_PATH"] = assimp_path
