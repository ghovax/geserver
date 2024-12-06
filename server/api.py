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
from error_codes import *

# Initialize logger for this module
logger = logging.getLogger(__name__)
app = Flask(__name__)

# Initialize tracer
tracer = trace.get_tracer(__name__)


def success_response(message=None, data=None):
    """Create a standardized success response.

    Args:
        message (str, optional): A message to include in the response. Defaults to None.
        data (dict, optional): The data to include in the response. Defaults to None.

    Returns:
        tuple: A tuple containing the JSON response and HTTP status code.
    """
    response = {
        "status": "success",
        "message": message,
        "data": data or {},
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }
    return jsonify(response), 200


def error_response(message, status_code=400, error_code=None):
    """Create a standardized error response.

    Args:
        message (str): A human-readable error message.
        status_code (int): The HTTP status code to return.
        error_code (str, optional): A machine-readable error code. Defaults to None.

    Returns:
        tuple: A tuple containing the JSON response and HTTP status code.
    """
    response = {
        "status": "error",
        "message": message,
        "error": {
            "code": error_code or f"ERROR_{status_code}",
        },
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
        logger.debug(f"Processing request to retrieve entity #{entity_id}")

        with world_lock:
            if not world.entity_exists(entity_id):
                logger.warning(
                    f"Attempted to retrieve non-existent entity #{entity_id}"
                )
                return error_response(
                    message=f"Entity #{entity_id} does not exist",
                    status_code=404,
                    error_code=ENTITY_NOT_FOUND,
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

            logger.info(
                f"Retrieved entity #{entity_id} with "
                f"{len(entity_info['components'])} components"
            )
            return success_response(
                message=f"Retrieved entity #{entity_id}", data=entity_info
            )

    except Exception as exception:
        error_message = f"Failed to retrieve entity #{entity_id}"
        logger.error(f"{error_message}: {str(exception)}", exc_info=True)
        return error_response(
            message=error_message, status_code=500, error_code=INTERNAL
        )


def validate_add_component_request(parameters):
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
                "Position, rotation, and scale must be arrays of three numbers",
            )

    return True, None


def handle_transform(entity_id, component_data):
    position = component_data.get("position")
    rotation = component_data.get("rotation")
    scale = component_data.get("scale")

    with world_lock:
        if not world.entity_exists(entity_id):
            return error_response(
                f"Entity #{entity_id} not found", 404, ENTITY_NOT_FOUND
            )

        world.add_component(entity_id, Transform(position, rotation, scale))
        logger.info(
            f"Added Transform component to entity #{entity_id} with data {component_data}"
        )
        return success_response(
            message=f"Transform component added to entity #{entity_id}",
            data=component_data,
        )


@app.route("/add_component/<int:entity_id>", methods=["POST"])
def add_component(entity_id):
    """Add a component to an existing entity.

    This endpoint accepts a JSON payload with the component type and its parameters,
    and adds the specified component to the entity.

    Args:
        entity_id (int): The ID of the entity to which the component will be added.

    Returns:
        JSON response indicating the result of the operation.
    """
    with tracer.start_as_current_span("add_component"):
        try:
            parameters = request.json
            if parameters is None:
                return error_response("Invalid JSON request", 400, INVALID_JSON_REQUEST)

            # Validate the request parameters
            is_valid, error_message = validate_add_component_request(parameters)
            if not is_valid:
                return error_response(error_message, 400, UNSUPPORTED_COMPONENT_TYPE)

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
                    "Unsupported component type", 400, UNSUPPORTED_COMPONENT_TYPE
                )

        except Exception as exception:
            logger.error(
                f"Error adding component to entity #{entity_id}: {str(exception)}",
                exc_info=True,
            )
            return error_response(str(exception), 400, INTERNAL)


@app.route("/create_entity", methods=["POST"])
def create_entity():
    """Create a new entity.

    This endpoint accepts a JSON payload with the entity's components and creates a new entity.

    Returns:
        JSON response indicating the result of the operation.
    """
    parameters = request.json
    if parameters is None:
        return error_response("Invalid JSON request", 400, INVALID_JSON_REQUEST)

    # Extract parameters with defaults
    name_data = parameters.get("name")
    target_scene_data = parameters.get("targetScene")
    tags_data = parameters.get("tags")

    if not target_scene_data or not name_data or tags_data is None:
        return error_response(
            "name, targetScene, and tags are required", 400, INVALID_JSON_REQUEST
        )

    with world_lock:
        # Create the entity with the provided or default components
        entity_id = world.create_entity(
            Name(name_data),
            TargetScene(target_scene_data),
            Tags(tags_data),
        )
        logger.info(f"Created entity #{entity_id}")
        return success_response(f"Entity #{entity_id} created", {"entityId": entity_id})


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
                f"Entity #{entity_id} not found", 404, ENTITY_NOT_FOUND
            )

        world.delete_entity(entity_id)
        logger.info(f"Removed entity #{entity_id}")
        return success_response(f"Entity #{entity_id} removed")


@app.route("/shutdown", methods=["POST"])
def shutdown():
    """Shutdown the Flask server.

    This endpoint shuts down the server.

    Returns:
        JSON response indicating the result of the operation.
    """
    threading.Thread(target=pyglet.app.exit).start()
    logger.info("Server shutting down...")
    return success_response("Server shutting down...")
