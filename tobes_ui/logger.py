"""Logger for tobes-ui"""

from enum import Enum
import logging

LOGGER_NAME = 'tobes-ui'
LOGGER = logging.getLogger(LOGGER_NAME)
SUB_LOGGER = lambda name: logging.getLogger(f"{LOGGER_NAME}.{name}")

class LogLevel(Enum):
    """Defines log level"""
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARN = logging.WARN
    ERROR = logging.ERROR
    FATAL = logging.FATAL

    def __str__(self):
        """Convert to readable string"""
        return str(self.name).lower()

def configure_logging(loglevel: LogLevel, file: str = None):
    """Configure logging for tobes_ui to given loglevel"""
    fmt = ('%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s %(module)s' +
           ' %(funcName)s: %(message)s')
    if file:
        logging.basicConfig(filename=file,
                            level=logging.ERROR, format=fmt, datefmt='%Y-%m-%d %H:%M:%S')
    else:
        logging.basicConfig(level=logging.ERROR, format=fmt, datefmt='%Y-%m-%d %H:%M:%S')
    LOGGER.setLevel(loglevel.value)

def set_level(loglevel: LogLevel, sub_logger: str = None):
    """Configure level on the fly, for the main logger or sub-logger"""
    if sub_logger:
        SUB_LOGGER(sub_logger).setLevel(loglevel.value)
    else:
        LOGGER.setLevel(loglevel.value)
