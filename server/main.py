"""
Main application module that handles the initialization and running of the entity system.

This module sets up logging, starts the Flask API server, and runs the Pyglet event loop.
"""

import logging
import threading
import pyglet
from configuration import setup_logging, setup_opentelemetry
from opentelemetry.instrumentation.flask import FlaskInstrumentor
import api

# Configure logging at startup
setup_logging()
setup_opentelemetry()  # Set up OpenTelemetry
logger = logging.getLogger(__name__)

# Instrument the Flask app
FlaskInstrumentor().instrument_app(api.app)


def run_flask_app():
    """Start the Flask API server in a separate thread.

    This function initializes the Flask application and runs it on the specified host and port.
    """
    werkzeug_logger = logging.getLogger("werkzeug")
    werkzeug_logger.handlers = []
    werkzeug_logger.propagate = True

    logger.info("Starting Flask server...")
    try:
        api.app.run(host="0.0.0.0", port=5003, debug=False, use_reloader=False)
        logger.info("Flask server started")
    except Exception as exception:
        logger.error(f"Failed to start Flask server: {str(exception)}", exc_info=True)


if __name__ == "__main__":
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask_app, daemon=True)
    flask_thread.start()

    # Start Pyglet event loop in the main thread
    # This will block until the application is closed
    pyglet.app.run()

    logger.info("Shutting down...")
