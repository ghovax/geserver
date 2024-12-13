"""
API module that provides HTTP endpoints for interacting with the entity system.

This module defines the Flask application and various endpoints for creating,
updating, retrieving, and removing entities, as well as managing the application state.
"""

import logging
from flask import Flask, request, jsonify, abort
import vispy.app
from server.entity_components import CoreProperties, Transform, Script, Renderer
from server.configuration import world_lock
import datetime
import os
import threading
from flask_socketio import SocketIO, emit
import esper
import importlib.util
from threading import Lock
import re

# Initialize logger for this module
logger = logging.getLogger(__name__)
flask_app = Flask(__name__)

# Initialize SocketIO
socketio = SocketIO(flask_app, async_mode="eventlet")

# Global variable to hold the script modules
scripts = []
scripts_lock = Lock()  # Create a lock for thread-safe access

# Global variable to hold the meshes
meshes = []
meshes_lock = Lock()  # Create a lock for thread-safe access


# Create a success response
def success_response(data=None):
    response = {
        "status": "success",
        "data": data or {},
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    return jsonify(response), 200


# Create an error response
def error_response(reason, status_code=400):
    response = {
        "status": "error",
        "reason": reason,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    return jsonify(response), status_code


def get_entity_components(entity_id):
    """Retrieve components for a specific entity."""
    logger.debug(f"Retrieving components for entity {entity_id}")
    entity_info = {"components": {}}

    import importlib

    # Import the entity_components module and get all the component types
    entity_components = importlib.import_module("server.entity_components")
    component_types = [
        getattr(entity_components, class_name)
        for class_name in dir(entity_components)
        if not class_name.startswith("__")
        and isinstance(getattr(entity_components, class_name), type)
    ]
    # Create a mapping of component types to their names and fields
    component_mapping = {
        class_object: (
            class_object.__name__,
            [field.name for field in class_object.__dataclass_fields__.values()],
        )
        for class_object in component_types
    }

    # Iterate over the component mapping and retrieve the component values
    for component_type, (key, fields) in component_mapping.items():
        try:
            if esper.has_component(entity_id, component_type):
                component_value = esper.component_for_entity(entity_id, component_type)
                entity_info["components"][key] = {
                    "".join(
                        x.capitalize() if i > 0 else x.lower()
                        for i, x in enumerate(field.split("_"))
                    ): getattr(component_value, field)
                    for field in fields
                }
        except KeyError:
            logger.warning(f"Entity {entity_id} does not have component {key}")

    return entity_info


@flask_app.route("/get_entity_components", methods=["GET"])
def get_entity_components_endpoint():
    """Retrieve information about a specific entity."""
    logger.info("Endpoint '/get_entity_components' called")
    try:
        parameters = request.json
        logger.debug(f"Request data: {parameters}")
        if parameters is None:
            return error_response(reason="Invalid JSON request", status_code=400)

        entity_id = parameters.get("entityId")
        logger.debug(f"Processing request to retrieve entity {entity_id}")

        with world_lock:
            if not esper.entity_exists(entity_id):
                logger.warning(f"Attempted to retrieve non-existent entity {entity_id}")
                return error_response(
                    reason=f"Entity {entity_id} does not exist",
                    status_code=404,
                )

            entity_info = get_entity_components(entity_id)
            return success_response(data=entity_info)

    except Exception as exception:
        error_message = f"Failed to retrieve entity {entity_id}"
        logger.error(f"{error_message}: {str(exception)}", exc_info=True)
        return error_response(
            reason=error_message,
            status_code=500,
        )


def validate_transform_data(component_data):
    logger.debug("Validating transform data")
    if not isinstance(component_data, dict):
        return False, "Transform data must be an object"

    # Check for unexpected fields
    allowed_fields = {
        "position",
        "scale",
    }  # TODO: Add rotation component, which is still not implemented because I don't know what the rotation axis is
    unexpected_fields = set(component_data.keys()) - allowed_fields
    if unexpected_fields:
        logger.warning(
            f"Unexpected fields in transform data: {', '.join(unexpected_fields)}"
        )
        return (
            False,
            f"Unexpected fields in transform data: {', '.join(unexpected_fields)}",
        )

    required_fields = [
        "position",
        "scale",
    ]  # TODO: Add the rotation component also here
    for field in required_fields:
        if field not in component_data:
            return False, f"Transform data is missing a required field: {field}"

        value = component_data[field]
        if not isinstance(value, list):
            return False, f"{field} must be an array"
        if len(value) != 3:
            return False, f"{field} must contain exactly 3 values"

        # Validate that all values are numbers and within reasonable ranges
        if not all(isinstance(x, (int, float)) for x in value):
            return False, f"All {field} values must be numbers"

        # Add reasonable range checks
        if field == "scale" and any(x <= 0 for x in value):
            return False, "Scale values must be positive numbers"
        if any(abs(x) > 1e6 for x in value):
            return (
                False,
                f"{field} values must be within reasonable range, with a maximum of 1,000,000",
            )

    return True, None


def validate_script_data(component_data):
    logger.debug("Validating script data")
    script_path = component_data.get("scriptPath")
    if not script_path:
        return False, "Script path is required"
    if not isinstance(script_path, str):
        return False, "Script path must be a string"
    if not os.path.isfile(script_path):
        return False, "Script path must point to a valid file"
    if not script_path.endswith(".py"):
        return False, "Script path must have a .py extension"

    return True, None


def validate_renderer_data(component_data):
    logger.debug("Validating renderer data")
    if not isinstance(component_data, dict):
        return False, "Renderer data must be an object"

    file_path = component_data.get("filePath")
    if not file_path:
        return False, "File path is required"
    if not isinstance(file_path, str):
        return False, "File path must be a string"
    if not os.path.isfile(file_path):
        return False, "File path must point to a valid file"
    supported_extensions = [".obj", ".fbx", ".dae", ".gltf", ".glb"]
    if not any(file_path.endswith(extension) for extension in supported_extensions):
        return (
            False,
            f"File path must have a supported extension ({', '.join(supported_extensions)})",
        )

    return True, None


# Validate the request body for adding a component to an entity
def validate_add_component_to_entity_request(parameters):
    logger.debug("Validating add component to entity request")
    if not isinstance(parameters, dict):
        return False, "Request body must be a JSON object"

    entity_id = parameters.get("entityId")
    if not entity_id:
        return False, "Entity ID is required"
    if not isinstance(entity_id, int):
        return False, "Entity ID must be an integer"

    component_type = parameters.get("type")
    # FIXME: Get allowed component types from the entity_components module
    allowed_component_types = ["transform", "script", "renderer"]
    if not component_type:
        return False, "Component type is required"
    if not isinstance(component_type, str):
        return False, "Component type must be a string"
    if component_type not in allowed_component_types:
        return (
            False,
            f"Invalid component type: {component_type}, allowed types are: {', '.join(allowed_component_types)}",
        )

    component_data = parameters.get("data")
    if not component_data:
        return False, "Component data is required"

    validation_functions = {
        component_type: globals()[f"validate_{component_type}_data"]
        for component_type in allowed_component_types
    }

    is_valid, error_message = validation_functions[component_type](component_data)
    if not is_valid:
        logger.warning(f"Validation failed for {component_type}: {error_message}")
        return False, error_message

    return True, None


# Handle adding a transform component to an entity
def handle_transform_component(entity_id, transform: Transform):
    logger.debug(f"Handling transform component for entity {entity_id}")
    try:
        with world_lock:
            logger.debug(f"Acquired lock for entity {entity_id}")
            esper.add_component(entity_id, transform)
            logger.info(f"Successfully added transform component to entity {entity_id}")
            mesh = next(
                (mesh for mesh in meshes if mesh["entityId"] == entity_id), None
            )
            if mesh:
                mesh["toBeTransformed"] = True
            return success_response(
                data=esper.component_for_entity(entity_id, Transform)
            )
    except Exception as exception:
        logger.error(
            f"Error handling transform component for entity {entity_id}: {exception}"
        )


# Handle adding a script component to an entity
def handle_script_component(entity_id, script: Script):
    logger.debug(f"Handling script component for entity {entity_id}")
    global scripts  # Declare the global variable

    script_path = script.script_path
    logger.info(f"Loading script at {script_path} for entity {entity_id}")

    # Extract the script name without the extension to create a meaningful module name
    script_name = os.path.splitext(os.path.basename(script_path))[0]

    # Load the script as a module with a meaningful name
    spec = importlib.util.spec_from_file_location(script_name, script_path)
    script_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script_module)

    try:
        with world_lock:
            if not esper.has_component(entity_id, Script):
                esper.add_component(entity_id, Script(script_path))
                logger.info(
                    f"Script component added for entity {entity_id} with path {script_path}"
                )
            else:
                logger.warning(
                    f"Script component already exists for entity {entity_id}"
                )
                return error_response(
                    reason=f"Script component already exists for entity {entity_id}",
                    status_code=400,
                )

        # FIXME: What if it has both on_load and on_update? What if it has neither?
        script_info = {}

        # Check if the on_load function exists
        if hasattr(script_module, "on_load"):
            logger.debug(
                f"Script on_load function is found at: {script_module.on_load}"
            )

            script_module.on_load(entity_id)

            # Create a dictionary to hold the script path and module
            # FIXME: Replace or append to the dictionary?
            script_info = {"scriptPath": script_path, "scriptModule": script_module}

        if hasattr(script_module, "on_update"):
            logger.debug(
                f"Script on_update function is found at: {script_module.on_update}"
            )

            # TODO: Make this a global timer that can be stopped and started
            def on_update(event):
                global meshes
                # Fetch the mesh and shift it by the transform component
                mesh = next(
                    (mesh for mesh in meshes if mesh["entityId"] == entity_id), None
                )
                if mesh and mesh["toBeTransformed"] == True:
                    transform = esper.component_for_entity(entity_id, Transform)
                    with meshes_lock:
                        mesh["meshObject"].transform.translate(
                            tuple(transform.position)
                        )
                        # TODO: Rotate the mesh by the rotation component, which aren't present yet
                        mesh["meshObject"].transform.scale(tuple(transform.scale))
                        mesh["toBeTransformed"] = False

                script_module.on_update(event)

            timer = vispy.app.Timer(
                interval=1 / 60, connect=on_update, start=True
            )  # 60 FPS callback
            script_info["timer"] = timer
            if "entityIds" not in script_info:
                script_info["entityIds"] = []
            script_info["entityIds"].append(entity_id)

        with scripts_lock:  # Acquire the lock
            scripts.append(script_info)  # Modify the list safely

        return success_response()
    except KeyError:
        return error_response(
            reason=f"Entity {entity_id} does not exist", status_code=404
        )


def handle_renderer_component(entity_id, renderer: Renderer):
    logger.debug(f"Handling renderer component for entity {entity_id}")
    file_path = renderer.file_path

    # Validate that scene_path is provided
    if file_path is None:
        return error_response(reason="File path is required", status_code=400)

    logger.info(f"Loading scene from {file_path} for entity {entity_id}")

    try:
        from vispy import io
        from vispy import scene
        from server.configuration import view

        # Check if the path is a valid file
        if not os.path.isfile(file_path):
            return error_response(
                reason="File path must point to a valid file", status_code=400
            )

        # Read mesh data
        vertices, faces, normals, _ = io.read_mesh(file_path)
        mesh = scene.visuals.Mesh(
            vertices,
            faces,
            normals,
            shading="flat",
            color=(1, 1, 1, 1),
            parent=view.scene,
        )

        from vispy.visuals.transforms import MatrixTransform

        mesh.transform = MatrixTransform()
        with meshes_lock:
            meshes.append(
                {
                    "entityId": entity_id,
                    "filePath": file_path,
                    "meshObject": mesh,
                    "toBeTransformed": True,
                }
            )

        # Check if vertices and faces are valid
        if len(vertices) == 0 or len(faces) == 0:  # Check if arrays are empty
            logger.error("Mesh data is empty or invalid")
            return error_response(reason="Invalid mesh data", status_code=400)

        logger.info(
            f"Mesh contains {len(faces)} faces, {len(vertices)} vertices and {len(normals)} normals"
        )

        with world_lock:
            if not esper.entity_exists(entity_id):
                return error_response(
                    reason=f"Entity {entity_id} not found", status_code=404
                )

            esper.add_component(entity_id, renderer)
            logger.info(f"Successfully added renderer component to entity {entity_id}")
            return success_response(
                data=esper.component_for_entity(entity_id, Renderer)
            )

    except Exception as exception:
        logger.error(
            f"Failed to load scene from {file_path}: {exception}", exc_info=True
        )
        return error_response(reason="Failed to load scene data", status_code=500)


def add_component_to_entity(entity_id, component):
    """Add a component to an existing entity."""
    logger.debug(f"Attempting to add component to entity {entity_id}")

    try:
        if not esper.entity_exists(entity_id):
            raise ValueError(f"Entity {entity_id} not found")

        import server.entity_components as components  # Import the module

        component_classes = [
            getattr(components, class_name)
            for class_name in dir(components)
            if isinstance(getattr(components, class_name), type)
            and class_name != "CoreProperties"
        ]  # Acquire list of all class types from server.entity_components
        component_handlers = {
            component_class: globals()[
                f"handle_{component_class.__name__.lower()}_component"
            ]
            for component_class in component_classes
        }

        handler = component_handlers.get(type(component))
        if handler:
            handler(entity_id, component)
        else:
            raise ValueError(
                f"Component is not of the supported types: {', '.join(component_handlers.keys())}"
            )
    except Exception as exception:
        logger.error(
            f"Error adding component to entity {entity_id}: {exception}",
            exc_info=True,
        )
        raise exception


def camel_to_snake(name):
    """Convert camelCase to snake_case."""
    logger.debug(f"Converting '{name}' from camelCase to snake_case")
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", name).lower()


def convert_keys_to_snake_case(data):
    """Convert all keys in a dictionary from camelCase to snake_case."""
    logger.debug("Converting keys to snake_case")
    if isinstance(data, dict):
        return {
            camel_to_snake(k): convert_keys_to_snake_case(v) for k, v in data.items()
        }
    elif isinstance(data, list):
        return [convert_keys_to_snake_case(item) for item in data]
    else:
        return data


@flask_app.route("/add_component_to_entity", methods=["POST"])
def add_component_to_entity_endpoint():
    """Add a component to an existing entity."""
    logger.info("Endpoint '/add_component_to_entity' called")
    try:
        parameters = request.json
        logger.debug(f"Request data: {parameters}")
        if parameters is None:
            return error_response(reason="Invalid JSON request", status_code=400)

        is_valid, error_message = validate_add_component_to_entity_request(parameters)
        if not is_valid:
            return error_response(reason=error_message, status_code=400)

        entity_id = parameters.get("entityId")
        component_type = parameters.get("type")
        component_data = parameters.get("data")

        # Component types association
        component_types_association = {
            "transform": Transform,
            "script": Script,
            "renderer": Renderer,
        }

        component_type = component_types_association.get(component_type)
        if component_type is None:
            return error_response(
                reason=f"Unsupported component type: {component_type}", status_code=400
            )

        component_data = convert_keys_to_snake_case(component_data)
        component = component_type(**component_data)
        add_component_to_entity(entity_id, component)

        return success_response()

    except ValueError as value_error:
        return error_response(reason=str(value_error), status_code=404)
    except Exception as exception:
        entity_id = request.json.get("entityId")
        logger.error(
            f"Error adding component to entity {entity_id}: {str(exception)}",
            exc_info=True,
        )
        return error_response(reason=str(exception), status_code=500)


def create_entity(name, target_scene, tags):
    """Create a new base entity locally."""
    logger.info(f"Creating entity with name: {name}")
    base_entity_component = CoreProperties(
        name=name,
        tags=tags,
        target_scene=target_scene,
    )
    return esper.create_entity(base_entity_component)


@flask_app.route("/create_entity", methods=["POST"])
def create_entity_endpoint():
    """Create a new base entity.

    JSON payload is expected to contain the following fields for example:
    ```json
    {
        "name": "entity_name",
        "targetScene": "target_scene",
        "tags": ["tag1", "tag2"]
    }
    ```

    Returns:
        JSON response indicating the result of the operation.
    """
    logger.info("Endpoint '/create_entity' called")
    parameters = request.json
    logger.debug(f"Request data: {parameters}")
    if parameters is None:
        return error_response(
            reason="Invalid JSON request, expected application/json", status_code=415
        )

    name_data = parameters.get("name")
    target_scene_data = parameters.get("targetScene")
    tags_data = parameters.get("tags", [])

    if not name_data or not target_scene_data:
        return error_response(
            reason="name and targetScene are required", status_code=400
        )

    with world_lock:
        entity_id = create_entity(name_data, target_scene_data, tags_data)
        return success_response(data={"entityId": entity_id})


def remove_entity(entity_id):
    """Remove an existing entity locally."""
    logger.info(f"Attempting to remove entity {entity_id}")
    global meshes  # Declare the global variable
    global scripts

    with world_lock:
        if not esper.entity_exists(entity_id):
            raise ValueError(f"Entity {entity_id} not found")

        esper.delete_entity(entity_id)
        with meshes_lock:
            meshes_to_remove = [
                mesh for mesh in meshes if mesh["entityId"] == entity_id
            ]
            for mesh in meshes_to_remove:
                from vispy.visuals.transforms import MatrixTransform

                mesh["meshObject"].parent = None
                mesh["meshObject"].transform = MatrixTransform()
            meshes = [
                mesh for mesh in meshes if mesh["entityId"] != entity_id
            ]  # Update the global meshes list

        with scripts_lock:
            scripts_to_remove = [
                script for script in scripts if entity_id in script["entityIds"]
            ]
            for script in scripts_to_remove:
                script["timer"].stop()
                script["timer"].disconnect()
                script["entityIds"].remove(entity_id)
            scripts = [
                script for script in scripts if entity_id not in script["entityIds"]
            ]  # Update the global scripts list


@flask_app.route("/remove_entity", methods=["DELETE"])
def remove_entity_endpoint():
    """Remove an existing entity.

    This endpoint removes the specified entity from the system.

    Request JSON payload is for example:
    ```json
    {
        "entityId": 1
    }
    ```

    Returns:
        JSON response indicating the result of the operation.
    """
    logger.info("Endpoint '/remove_entity' called")
    parameters = request.json
    entity_id = parameters.get("entityId")

    if entity_id is None:
        return error_response(reason="entityId is required", status_code=400)

    try:
        remove_entity(entity_id)
        logger.info(f"Successfully removed entity {entity_id}")
        return success_response()
    except ValueError as value_error:
        return error_response(reason=str(value_error), status_code=404)
    except Exception as exception:
        logger.error(
            f"Error removing entity {entity_id}: {str(exception)}",
            exc_info=True,
        )
        return error_response(reason=str(exception), status_code=500)


@flask_app.route("/status", methods=["GET"])
def status():
    """Check the server status.

    Request JSON payload is empty.

    Returns:
        JSON response indicating the result of the operation.
    """
    logger.info("Endpoint '/status' called")
    return success_response()


@socketio.on("request_status")
def handle_status_request():
    """Handle WebSocket status request.

    Request JSON payload is empty.

    Returns:
        JSON response indicating the result of the operation.
    """
    try:
        response = {
            "status": "success",
            "data": {},
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        emit("status_response", response)
    except Exception as exception:
        emit(
            "status_response",
            {
                "status": "error",
                "reason": str(exception),
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            },
        )


@flask_app.route("/reset", methods=["POST"])
def reset():
    """Reset the server state.

    This endpoint resets the server to its initial state.

    Request JSON payload is empty.

    Returns:
        JSON response indicating the result of the operation.
    """
    logger.info("Endpoint '/reset' called")
    try:
        with world_lock:
            logger.info("Clearing the database")
            esper.clear_database()  # Assuming this function exists to clear all entities

        return success_response()
    except Exception as exception:
        logger.error(f"Error resetting server: {str(exception)}", exc_info=True)
        return error_response(reason="Failed to reset server", status_code=500)
