"""
Module defining the components used in the entity system.

Each component represents a specific attribute or behavior of an entity,
allowing for modular and flexible entity definitions.
"""


class Name:
    """
    Represents a name identifier for an entity.

    Attributes:
        value (str): The name of the entity.
    """

    def __init__(self, value):
        self.value = value


class Tags:
    """
    Represents a collection of tags for an entity.

    Attributes:
        values (list[str]): List of tags associated with the entity.
    """

    def __init__(self, values):
        self.values = values


class TargetScene:
    """
    Represents the target scene for an entity.

    Attributes:
        value (str): The scene identifier.
    """

    def __init__(self, value):
        self.value = value


class Transform:
    """
    Represents the transformation properties of an entity.

    Attributes:
        position (list[float]): The position of the entity in 3D space.
        rotation (list[float]): The rotation of the entity in 3D space.
        scale (list[float]): The scale of the entity in 3D space.
    """

    def __init__(self, position, rotation, scale):
        self.position = position
        self.rotation = rotation
        self.scale = scale
