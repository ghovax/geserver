"""
Main application module that handles the initialization and running of the entity system.

This module sets up logging, starts the Flask API server, and runs the Pyglet event loop.
"""

import logging
import threading
import server.api as api
import server.configuration as configuration
from vispy import app

# Configure logging at startup
logger = logging.getLogger(__name__)


def run_flask_app():
    # Start the Flask API server in a separate thread
    werkzeug_logger = logging.getLogger("werkzeug")
    werkzeug_logger.handlers = []
    werkzeug_logger.propagate = True

    logger.info("Starting Flask server...")
    try:
        api.socketio.run(
            api.flask_app, host="0.0.0.0", port=5001, debug=False, use_reloader=False
        )
        logger.info("Flask server started")
    except Exception as exception:
        logger.error(f"Failed to start Flask server: {str(exception)}", exc_info=True)


def main():
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask_app, daemon=True)
    flask_thread.start()

    # TODO: Start event loop in the main thread
    app.run()


if __name__ == "__main__":
    main()
