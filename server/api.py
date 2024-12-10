"""
API module that provides HTTP endpoints for interacting with the entity system.

This module defines the Flask application and various endpoints for creating,
updating, retrieving, and removing entities, as well as managing the application state.
"""

import logging
from flask import Flask, request, jsonify, abort
from server.entity_components import CoreProperties, Transform, Script
from server.configuration import world_lock, window, window_lock
import pyglet
import datetime
import sys
import os
import threading
import subprocess
from flask_socketio import SocketIO, emit
import esper
import importlib.util
import time
from threading import Lock

# Initialize logger for this module
logger = logging.getLogger(__name__)
app = Flask(__name__)

# Initialize SocketIO
socketio = SocketIO(app, async_mode="eventlet")

# Global variable to hold the script modules
script_modules = []
script_modules_lock = Lock()  # Create a lock for thread-safe access


def success_response(data=None):
    """Create a standardized success response.

    Args:
        data (dict, optional): The data to include in the response. Defaults to None.

    Returns:
        tuple: A tuple containing the JSON response and HTTP status code.
    """
    response = {
        "status": "success",
        "data": data or {},
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    return jsonify(response), 200


def error_response(reason, status_code=400):
    """Create a standardized error response.

    Args:
        reason (str): A human-readable error message.
        status_code (int, optional): The HTTP status code to return. Defaults to 400.

    Returns:
        tuple: A tuple containing the JSON response and HTTP status code.
    """
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
                if not class_name.startswith("__") and isinstance(getattr(entity_components, class_name), type)
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


def validate_add_component_to_entity_request(parameters):
    """Validate the parameters for adding a component to an entity.

    Args:
        parameters (dict): The parameters to validate.

    Returns:
        tuple: A tuple containing a boolean indicating validity and an error message if invalid.
    """
    if not isinstance(parameters, dict):
        return False, "Request body must be a JSON object"

    component_type = parameters.get("type")
    if not component_type:
        return False, "Component type is required"
    if not isinstance(component_type, str):
        return False, "Component type must be a string"
    if component_type not in ["transform", "script"]:
        return False, "Invalid component type"

    component_data = parameters.get("data")
    if not component_data:
        return False, "Component data is required"

    if component_type == "transform":
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
                return False, f"Transform data missing required field: {field}"

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
                    f"{field} values must be within reasonable range (±1,000,000)",
                )
                
    elif component_type == "script":
        script_path = parameters.get("data", {}).get("scriptPath")
        if not script_path:
            return False, "Script path is required"
        if not isinstance(script_path, str):
            return False, "Script path must be a string"
        if not os.path.isfile(script_path):
            return False, "Script path must point to a valid file"
        if not script_path.endswith(".py"):
            return False, "Script path must have a .py extension"

    return True, None


def handle_transform(entity_id, component_data):
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


def handle_script(entity_id, component_data):
    global script_modules  # Declare the global variable

    script_path = component_data.get("scriptPath")
    logger.info(f"Loading script at {script_path} for entity {entity_id}")

    # Extract the script name without the extension to create a meaningful module name
    script_name = os.path.splitext(os.path.basename(script_path))[0]

    # Load the script as a module with a meaningful name
    spec = importlib.util.spec_from_file_location(script_name, script_path)
    script_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script_module)
    esper.add_component(entity_id, Script(script_path))

    # Check if the on_load function exists
    if hasattr(script_module, "on_load"):
        logger.info(f"Script loaded: {script_name}")

        # Create a dictionary to hold the script path and module
        script_info = {"path": script_path, "module": script_module}

        # Append the dictionary to the global list in a thread-safe manner
        with script_modules_lock:  # Acquire the lock
            script_modules.append(script_info)  # Modify the list safely

        logger.info(f"Script on_load function: {script_module.on_load}")

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

        component_actions = {
            "transform": lambda: handle_transform(entity_id, component_data),
            "script": lambda: handle_script(entity_id, component_data),
        }

        action = component_actions.get(component_type)
        if action:
            return action()  # Call the corresponding function
        else:
            return error_response(reason="Unsupported component type", status_code=400)

    except Exception as exception:
        logger.error(
            f"Error adding component to entity {entity_id}: {str(exception)}",
            exc_info=True,
        )
        return error_response(reason=str(exception), status_code=500)


@app.route("/create_entity", methods=["POST"])
def create_entity():
    """Create a new base entity."""
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

    Returns:
        JSON response indicating the result of the operation.
    """
    threading.Thread(target=pyglet.app.exit).start()
    return success_response()


@app.route("/status", methods=["GET"])
def status():
    """Check the server status."""
    return success_response()


@socketio.on("request_status")
def handle_status_request():
    """Handle WebSocket status request."""
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
