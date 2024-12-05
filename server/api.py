"""
API module that provides HTTP endpoints for interacting with the entity system.

This module defines the Flask application and various endpoints for creating,
updating, retrieving, and removing entities, as well as managing the application state.
"""

import logging
from flask import Flask, request, jsonify
from entity_components import Name, Tags, TargetScene, Transform
from configuration import world, world_lock, window, window_lock
import pyglet
import datetime
from opentelemetry import trace

# Initialize logger for this module
logger = logging.getLogger(__name__)
app = Flask(__name__)

# Initialize tracer
tracer = trace.get_tracer(__name__)


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
        "error": {
            "message": message,
            "code": error_code or f"ERROR_{status_code}",
        },
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
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
                    error_code="ENTITY_NOT_FOUND",
                )

            entity_info = {
                "entityId": entity_id,
                "components": {},
            }

            component_mapping = {
                TargetScene: ("targetScene", "value"),
                Name: ("name", "value"),
                Tags: ("tags", "values"),
            }

            for component_class, (key, attr) in component_mapping.items():
                if world.has_component(entity_id, component_class):
                    entity_info["components"][key] = getattr(
                        world.component_for_entity(entity_id, component_class), attr
                    )

            logger.info(
                f"Retrieved entity #{entity_id} with "
                f"{len(entity_info['components'])} components"
            )
            return success_response(
                {"entity": entity_info, "message": "Entity retrieved"}
            )

    except Exception as exception:
        error_message = f"Failed to retrieve entity #{entity_id}"
        logger.error(f"{error_message}: {str(exception)}", exc_info=True)
        return error_response(
            message=error_message, status_code=500, error_code="INTERNAL_SERVER_ERROR"
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
            return error_response({"error": f"Entity #{entity_id} not found"}, 404)

        world.add_component(entity_id, Transform(position, rotation, scale))
        logger.info(
            f"Added Transform component to entity #{entity_id} with data {component_data}"
        )
        return success_response(
            {"message": f"Transform component added to entity #{entity_id}"}
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
                return error_response({"error": "Invalid JSON request"}, 400)

            # Validate the request parameters
            is_valid, error_message = validate_add_component_request(parameters)
            if not is_valid:
                return error_response({"error": error_message}, 400)

            component_type = parameters.get("type")
            component_data = parameters.get("data")

            component_actions = {
                "transform": lambda: handle_transform(entity_id, component_data)
            }

            action = component_actions.get(component_type)
            if action:
                return action()  # Call the corresponding function
            else:
                return error_response({"error": "Unsupported component type"}, 400)

        except Exception as exception:
            logger.error(
                f"Error adding component to entity #{entity_id}: {str(exception)}",
                exc_info=True,
            )
            return error_response({"error": str(exception)}, 400)
