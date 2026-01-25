"""
Logging configuration for ClientCreate.

Logs are stored in Google Drive appDataFolder, but we also maintain
a local fallback log for debugging before Drive connection is established.
"""

import logging
import os
from datetime import datetime
from typing import Optional, Callable


class DriveLogHandler(logging.Handler):
    """
    Custom log handler that writes to Google Drive.
    Buffers log entries until Drive connection is established.
    """

    def __init__(self):
        super().__init__()
        self.buffer = []
        self.drive_write_callback: Optional[Callable[[str], bool]] = None
        self.is_connected = False

    def set_drive_callback(self, callback: Callable[[str], bool]):
        """
        Set the callback function for writing to Drive.

        Args:
            callback: Function that takes log text and writes to Drive.
                     Returns True on success.
        """
        self.drive_write_callback = callback
        self.is_connected = True

        # Flush buffer
        if self.buffer:
            for record in self.buffer:
                self._write_to_drive(record)
            self.buffer.clear()

    def _write_to_drive(self, formatted_record: str):
        """Write a formatted record to Drive."""
        if self.drive_write_callback:
            try:
                self.drive_write_callback(formatted_record)
            except Exception as e:
                # Fallback to stderr if Drive write fails
                print(f"Failed to write log to Drive: {e}")

    def emit(self, record):
        """Emit a log record."""
        try:
            formatted = self.format(record)

            if self.is_connected and self.drive_write_callback:
                self._write_to_drive(formatted)
            else:
                # Buffer until connected
                self.buffer.append(formatted)
        except Exception:
            self.handleError(record)


class StatusLogHandler(logging.Handler):
    """
    Custom log handler that sends logs to GUI status widget.
    """

    def __init__(self):
        super().__init__()
        self.status_callback: Optional[Callable[[str], None]] = None

    def set_status_callback(self, callback: Callable[[str], None]):
        """
        Set the callback function for updating GUI status.

        Args:
            callback: Function that takes log message and updates GUI
        """
        self.status_callback = callback

    def emit(self, record):
        """Emit a log record to GUI."""
        try:
            if self.status_callback:
                # Use just the message for GUI, not full format
                self.status_callback(record.getMessage())
        except Exception:
            self.handleError(record)


# Global handlers
_drive_handler: Optional[DriveLogHandler] = None
_status_handler: Optional[StatusLogHandler] = None
_logger: Optional[logging.Logger] = None


def setup_logger(name: str = "ClientCreate") -> logging.Logger:
    """
    Set up and return the application logger.

    Args:
        name: Logger name

    Returns:
        Configured logger instance
    """
    global _drive_handler, _status_handler, _logger

    if _logger is not None:
        return _logger

    _logger = logging.getLogger(name)
    _logger.setLevel(logging.DEBUG)

    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    simple_formatter = logging.Formatter('%(message)s')

    # Console handler for debugging
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(detailed_formatter)
    _logger.addHandler(console_handler)

    # Drive handler (buffered until connected)
    _drive_handler = DriveLogHandler()
    _drive_handler.setLevel(logging.INFO)
    _drive_handler.setFormatter(detailed_formatter)
    _logger.addHandler(_drive_handler)

    # Status handler for GUI
    _status_handler = StatusLogHandler()
    _status_handler.setLevel(logging.INFO)
    _status_handler.setFormatter(simple_formatter)
    _logger.addHandler(_status_handler)

    # Local fallback log file
    local_log_dir = os.path.join(os.path.expanduser('~'), 'Documents', 'ClientCreate', 'logs')
    os.makedirs(local_log_dir, exist_ok=True)

    local_log_file = os.path.join(
        local_log_dir,
        f'client_create_{datetime.now().strftime("%Y-%m-%d")}.log'
    )

    file_handler = logging.FileHandler(local_log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    _logger.addHandler(file_handler)

    return _logger


def get_logger() -> logging.Logger:
    """Get the application logger, creating it if necessary."""
    global _logger
    if _logger is None:
        return setup_logger()
    return _logger


def set_drive_log_callback(callback: Callable[[str], bool]):
    """
    Set the callback for writing logs to Google Drive.

    Args:
        callback: Function that writes log text to Drive
    """
    global _drive_handler
    if _drive_handler:
        _drive_handler.set_drive_callback(callback)


def set_status_callback(callback: Callable[[str], None]):
    """
    Set the callback for updating GUI status.

    Args:
        callback: Function that updates GUI with log message
    """
    global _status_handler
    if _status_handler:
        _status_handler.set_status_callback(callback)


def log_info(message: str):
    """Log an info message."""
    get_logger().info(message)


def log_warning(message: str):
    """Log a warning message."""
    get_logger().warning(message)


def log_error(message: str):
    """Log an error message."""
    get_logger().error(message)


def log_debug(message: str):
    """Log a debug message."""
    get_logger().debug(message)
