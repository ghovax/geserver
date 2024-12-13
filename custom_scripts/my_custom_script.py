# Load the logger
import logging
logger = logging.getLogger(__name__)

import server.api as api
from server.entity_components import *
from server.api import meshes
from vispy.visuals.transforms import MatrixTransform

local_entity_id = None

def on_load(entity_id):
    logger.critical("My custom script has loaded!")
    global local_entity_id
    local_entity_id = entity_id

    # Create a transform component
    transform = Transform(position=[1, 2, 0], scale=[0.5, 1, 1.5])
    api.add_component_to_entity(entity_id, transform)

    # Create a renderer component
    renderer = Renderer(file_path="/Users/giovannigravili/geserver/assets/cube.obj")
    api.add_component_to_entity(local_entity_id, renderer)

def on_update(event):
    mesh = next((mesh for mesh in meshes if mesh["entityId"] == local_entity_id), None)
    if mesh:
        mesh["meshObject"].transform.rotate(0.1, [0, 1, 0]) # Rotate the mesh by 0.1 radians around the y-axis
    else:
        raise Exception(f"Mesh {local_entity_id} not found")