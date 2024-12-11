# Load the logger
import logging
logger = logging.getLogger(__name__)

def on_load():
    logger.critical("My custom script has loaded!")
