"""
API module that provides HTTP endpoints for interacting with the entity system.

This module defines the Flask application and various endpoints for creating,
updating, retrieving, and removing entities, as well as managing the application state.
"""

import logging
from flask import Flask, request, jsonify, abort
from server.entity_components import CoreProperties, Transform, Script
from server.configuration import world_lock
import pyglet
import datetime
import os
import threading
from flask_socketio import SocketIO, emit
import esper
import importlib.util
from threading import Lock

# Initialize logger for this module
logger = logging.getLogger(__name__)
app = Flask(__name__)

# Initialize SocketIO
socketio = SocketIO(app, async_mode="eventlet")

# Global variable to hold the script modules
script_modules = []
script_modules_lock = Lock()  # Create a lock for thread-safe access


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


@app.route("/get_entity/<int:entity_id>", methods=["GET"])
def get_entity(entity_id):
    """Retrieve information about a specific entity.

    This endpoint returns the components and their values for the specified entity.

    Request JSON payload is empty.

    Args:
        entity_id (int): The ID of the entity to retrieve.

    Returns:
        JSON response containing the entity's components and their values.
    """
    try:
        logger.debug(f"Processing request to retrieve entity {entity_id}")

        with world_lock:
            if not esper.entity_exists(entity_id):
                logger.warning(f"Attempted to retrieve non-existent entity {entity_id}")
                return error_response(
                    reason=f"Entity {entity_id} does not exist",
                    status_code=404,
                )

            entity_info = {
                "entityId": entity_id,
                "components": {},
            }

            import importlib

            entity_components = importlib.import_module("server.entity_components")
            component_types = [
                getattr(entity_components, class_name)
                for class_name in dir(entity_components)
                if not class_name.startswith("__")
                and isinstance(getattr(entity_components, class_name), type)
            ]
            component_mapping = {
                class_object: (
                    class_object.__name__,
                    [
                        field.name
                        for field in class_object.__dataclass_fields__.values()
                    ],
                )
                for class_object in component_types
            }

            for component_type, (key, fields) in component_mapping.items():
                if esper.has_component(entity_id, component_type):
                    component_value = esper.component_for_entity(
                        entity_id, component_type
                    )
                    entity_info["components"][key] = {
                        "".join(
                            x.capitalize() if i > 0 else x.lower()
                            for i, x in enumerate(field.split("_"))
                        ): getattr(component_value, field)
                        for field in fields
                    }

            return success_response(data=entity_info)

    except Exception as exception:
        error_message = f"Failed to retrieve entity {entity_id}"
        logger.error(f"{error_message}: {str(exception)}", exc_info=True)
        return error_response(
            reason=error_message,
            status_code=500,
        )


def validate_transform_data(component_data):
    if not isinstance(component_data, dict):
        return False, "Transform data must be an object"

    # Check for unexpected fields
    allowed_fields = {"position", "rotation", "scale"}
    unexpected_fields = set(component_data.keys()) - allowed_fields
    if unexpected_fields:
        return (
            False,
            f"Unexpected fields in transform data: {', '.join(unexpected_fields)}",
        )

    required_fields = ["position", "rotation", "scale"]
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


# Validate the request body for adding a component to an entity
def validate_add_component_to_entity_request(parameters):
    if not isinstance(parameters, dict):
        return False, "Request body must be a JSON object"

    component_type = parameters.get("type")
    # TODO: When a new component is added, add it to the allowed_component_types list
    allowed_component_types = ["transform", "script"]
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

    # TODO: When a new component is added, add its validation function to the validation_functions dictionary
    validation_functions = {
        "transform": validate_transform_data,
        "script": validate_script_data,
    }

    is_valid, error_message = validation_functions[component_type](component_data)
    if not is_valid:
        return False, error_message

    return True, None


# Handle adding a transform component to an entity
def handle_transform_component(entity_id, component_data):
    position = component_data.get("position")
    rotation = component_data.get("rotation")
    scale = component_data.get("scale")

    with world_lock:
        if not esper.entity_exists(entity_id):
            return error_response(
                reason=f"Entity {entity_id} not found", status_code=404
            )

        esper.add_component(entity_id, Transform(position, rotation, scale))
        return success_response(data=esper.component_for_entity(entity_id, Transform))


# Handle adding a script component to an entity
def handle_script_component(entity_id, component_data):
    global script_modules  # Declare the global variable

    script_path = component_data.get("scriptPath")
    logger.info(f"Loading script at {script_path} for entity {entity_id}")

    # Extract the script name without the extension to create a meaningful module name
    script_name = os.path.splitext(os.path.basename(script_path))[0]

    # Load the script as a module with a meaningful name
    spec = importlib.util.spec_from_file_location(script_name, script_path)
    script_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script_module)

    if not esper.has_component(entity_id, Script):
        esper.add_component(entity_id, Script(script_path))
    else:
        logger.warning(f"Script component already exists for entity {entity_id}")

    logger.info(f"Script loaded: {script_name}")

    # Check if the on_load function exists
    if hasattr(script_module, "on_load"):
        logger.debug(f"Script on_load function is found at: {script_module.on_load}")

        script_module.on_load()

        # Create a dictionary to hold the script path and module
        script_info = {"path": script_path, "module": script_module}

        # Append the dictionary to the global list in a thread-safe manner
        with script_modules_lock:  # Acquire the lock
            script_modules.append(script_info)  # Modify the list safely

        return success_response()
    else:
        logger.error(f"No on_load function found in {script_path}")
        return error_response(
            reason=f"No on_load function found in {script_path}", status_code=400
        )


@app.route("/add_component_to_entity/<int:entity_id>", methods=["POST"])
def add_component_to_entity(entity_id):
    """Add a component to an existing entity.

    This endpoint accepts a JSON payload with the component type and its parameters,
    and adds the specified component to the entity.

    Request JSON payload is expected to contain the following fields:
    - type (str): The type of the component to add.
    - data (dict): The data for the component to add, specific to the component type.

    For example, to add a transform component to an entity, the request body should look like this:
    ```json
    {
        "type": "transform",
        "data": {
            "position": [1, 2, 3],
            "rotation": [0, 0, 0],
            "scale": [1, 1, 1]
        }
    }
    ```

    To add a script component to an entity, the request body should look like this:
    ```json
    {
        "type": "script",
        "data": {
            "scriptPath": "/absolute/path/to/script.py"
        }
    }
    ```

    Args:
        entity_id (int): The ID of the entity to which the component will be added.

    Returns:
        JSON response indicating the result of the operation.
    """
    try:
        parameters = request.json
        if parameters is None:
            return error_response(reason="Invalid JSON request", status_code=400)

        is_valid, error_message = validate_add_component_to_entity_request(parameters)
        if not is_valid:
            return error_response(reason=error_message, status_code=400)

        component_type = parameters.get("type")
        component_data = parameters.get("data")

        # TODO: When a new component is added, add it to the component_types_association dictionary
        component_types_association = {
            "transform": Transform,
            "script": Script,
        }

        for component_type in component_types_association:
            if esper.has_component(
                entity_id, component_types_association[component_type]
            ):
                return error_response(
                    reason=f"Component {component_type} already exists for entity {entity_id}",
                    status_code=400,
                )

        if not esper.entity_exists(entity_id):
            return error_response(
                reason=f"Entity {entity_id} not found, can't add component {component_type} to it",
                status_code=404,
            )

        # TODO: When a new component is added, add it to the component_handlers dictionary
        component_handlers = {
            "transform": handle_transform_component,
            "script": handle_script_component,
        }

        if component_type in component_handlers:
            return component_handlers[component_type](entity_id, component_data)

        return error_response(
            reason=f"Unsupported component type: {component_type}", status_code=400
        )

    except Exception as exception:
        logger.error(
            f"Error adding component to entity {entity_id}: {str(exception)}",
            exc_info=True,
        )
        return error_response(reason=str(exception), status_code=500)


@app.route("/create_entity", methods=["POST"])
def create_entity():
    """Create a new base entity.

    JSON payload is expected to contain the following fields:
    - name (str): The name of the entity.
    - targetScene (str): The target scene for the entity.
    - tags (list): A list of tags for the entity.

    Returns:
        JSON response indicating the result of the operation.
    """
    parameters = request.json
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
        base_entity_component = CoreProperties(
            name=name_data,
            tags=tags_data,
            target_scene=target_scene_data,
        )
        entity_id = esper.create_entity(base_entity_component)
        return success_response(data={"entityId": entity_id})


@app.route("/remove_entity/<int:entity_id>", methods=["DELETE"])
def remove_entity(entity_id):
    """Remove an existing entity.

    This endpoint removes the specified entity from the system.

    Request JSON payload is empty.

    Args:
        entity_id (int): The ID of the entity to remove.

    Returns:
        JSON response indicating the result of the operation.
    """
    with world_lock:
        if not esper.entity_exists(entity_id):
            return error_response(
                reason=f"Entity {entity_id} not found", status_code=404
            )

        esper.delete_entity(entity_id)
        return success_response()


@app.route("/shutdown", methods=["POST"])
def shutdown():
    """Shutdown the Flask server.

    This endpoint shuts down the server.

    Request JSON payload is empty.

    Returns:
        JSON response indicating the result of the operation.
    """
    threading.Thread(target=pyglet.app.exit).start()
    return success_response()


@app.route("/status", methods=["GET"])
def status():
    """Check the server status.

    Request JSON payload is empty.

    Returns:
        JSON response indicating the result of the operation.
    """
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


@app.route("/reset", methods=["POST"])
def reset():
    """Reset the server state.

    This endpoint resets the server to its initial state.

    Request JSON payload is empty.

    Returns:
        JSON response indicating the result of the operation.
    """
    try:
        with world_lock:
            # Clear all entities from the esper world
            esper.clear_database()  # Assuming this function exists to clear all entities

        return success_response()
    except Exception as exception:
        logger.error(f"Error resetting server: {str(exception)}", exc_info=True)
        return error_response(reason="Failed to reset server", status_code=500)
