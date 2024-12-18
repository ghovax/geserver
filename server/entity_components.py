"""
Module defining the components used in the entity system.

Each component represents a specific attribute or behavior of an entity,
allowing for modular and flexible entity definitions.
"""

from dataclasses import dataclass
from typing import List, Any
import numpy as np
import vispy.scene.visuals


@dataclass
class Transform:
    """Represents the transformation properties of an entity."""

    position: List[float]
    # TODO: Add the rotation component, whatever it is, what about the rotation axis?
    scale: List[float]


@dataclass
class CoreProperties:
    """Represents the core properties of an entity."""

    name: str  # Name of the entity
    tags: List[str]  # List of tags associated with the entity
    target_scene: str  # Target scene for the entity


@dataclass
class Script:
    """Represents a script component that references a Python script to be executed."""

    script_path: str  # Path to the script to be executed


@dataclass
class Renderer:
    """Represents the renderer component containing scene data loaded from Assimp."""

    file_path: str  # Path to the scene file
