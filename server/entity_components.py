"""
Module defining the components used in the entity system.

Each component represents a specific attribute or behavior of an entity,
allowing for modular and flexible entity definitions.
"""

from dataclasses import dataclass
from typing import List

@dataclass
class Name:
    """Represents a name identifier for an entity."""
    value: str

@dataclass
class Tags:
    """Represents a collection of tags for an entity."""
    values: List[str]

@dataclass
class TargetScene:
    """Represents the target scene for an entity."""
    value: str

@dataclass
class Transform:
    """Represents the transformation properties of an entity."""
    position: List[float]
    rotation: List[float]
    scale: List[float]
