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

logger = logging.getLogger(__name__)

# Initialize global objects and their locks
world_lock = threading.Lock()

window_lock = threading.Lock()
window = None

import vispy
from vispy import scene
import numpy as np

vispy.use(app="Glfw", gl="gl2")
# Create a canvas and a 3D viewport
canvas = scene.SceneCanvas(
    keys="interactive", size=(800, 600), show=True, always_on_top=True
)
view = canvas.central_widget.add_view()

# Ensure camera is positioned correctly
view.camera = scene.TurntableCamera(
    up="z", azimuth=90, distance=5  # Adjust these values if necessary
)
