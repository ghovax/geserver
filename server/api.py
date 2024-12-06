"""
API module that provides HTTP endpoints for interacting with the entity system.

This module defines the Flask application and various endpoints for creating,
updating, retrieving, and removing entities, as well as managing the application state.
"""

import logging
from flask import Flask, request, jsonify, abort
from entity_components import Name, Tags, TargetScene, Transform
from configuration import world, world_lock, window, window_lock
import pyglet
import datetime
from opentelemetry import trace
import sys
import os
import threading
import subprocess
from flask_socketio import SocketIO, emit

# Initialize logger for this module
logger = logging.getLogger(__name__)
app = Flask(__name__)

# Initialize tracer
tracer = trace.get_tracer(__name__)

# Initialize SocketIO
socketio = SocketIO(app)


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
            if not world.entity_exists(entity_id):
                logger.warning(f"Attempted to retrieve non-existent entity {entity_id}")
                return error_response(
                    reason=f"Entity {entity_id} does not exist",
                    status_code=404,
                )

            entity_info = {
                "entityId": entity_id,
                "components": {},
            }

            component_mapping = {
                class_object: (
                    class_object.__name__.lower(),
                    [
                        field.name
                        for field in class_object.__dataclass_fields__.values()
                    ],
                )
                for class_object in (TargetScene, Name, Tags, Transform)
            }

            for component_type, (key, fields) in component_mapping.items():
                if world.has_component(entity_id, component_type):
                    component_value = world.component_for_entity(
                        entity_id, component_type
                    )
                    entity_info["components"][key] = {
                        field: getattr(component_value, field) for field in fields
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
    component_type = parameters.get("type")
    component_data = parameters.get("data")

    if component_type == "transform":
        if not isinstance(component_data, dict):
            return False, "Transform data must be an object"
        position = component_data.get("position")
        rotation = component_data.get("rotation")
        scale = component_data.get("scale")

        if not (
            isinstance(position, list)
            and len(position) == 3
            and isinstance(rotation, list)
            and len(rotation) == 3
            and isinstance(scale, list)
            and len(scale) == 3
        ):
            return (
                False,
                "position, rotation, and scale must be arrays of three numbers",
            )

    return True, None


def handle_transform(entity_id, component_data):
    position = component_data.get("position")
    rotation = component_data.get("rotation")
    scale = component_data.get("scale")

    with world_lock:
        if not world.entity_exists(entity_id):
            return error_response(
                reason=f"Entity {entity_id} not found", status_code=404
            )

        world.add_component_to_entity(entity_id, Transform(position, rotation, scale))
        return success_response(data=world.component_for_entity(entity_id, Transform))


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
    with tracer.start_as_current_span("add_component_to_entity"):
        try:
            parameters = request.json
            if parameters is None:
                return error_response(reason="Invalid JSON request", status_code=400)

            is_valid, error_message = validate_add_component_to_entity_request(
                parameters
            )
            if not is_valid:
                return error_response(reason=error_message, status_code=400)

            component_type = parameters.get("type")
            component_data = parameters.get("data")

            component_actions = {
                "transform": lambda: handle_transform(entity_id, component_data)
            }

            action = component_actions.get(component_type)
            if action:
                return action()  # Call the corresponding function
            else:
                return error_response(
                    reason="Unsupported component type", status_code=400
                )

        except Exception as exception:
            logger.error(
                f"Error adding component to entity {entity_id}: {str(exception)}",
                exc_info=True,
            )
            return error_response(reason=str(exception), status_code=500)


@app.route("/create_entity", methods=["POST"])
def create_entity():
    """Create a new entity.

    This endpoint accepts a JSON payload with the entity's components and creates a new entity.

    Returns:
        JSON response indicating the result of the operation.
    """
    parameters = request.json
    if parameters is None:
        return error_response(reason="Invalid JSON request", status_code=400)

    name_data = parameters.get("name")
    target_scene_data = parameters.get("targetScene")
    tags_data = parameters.get("tags")

    if not target_scene_data or not name_data or tags_data is None:
        return error_response(
            reason="name, targetScene, and tags are required", status_code=400
        )

    with world_lock:
        entity_id = world.create_entity(
            Name(name_data),
            TargetScene(target_scene_data),
            Tags(tags_data),
        )
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
        if not world.entity_exists(entity_id):
            return error_response(
                reason=f"Entity {entity_id} not found", status_code=404
            )

        world.delete_entity(entity_id)
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
