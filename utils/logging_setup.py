"""
Logging setup module for Mirrobot.

This module configures the logging system used throughout the bot, providing
consistent and well-formatted log output to files and the console.
"""

import logging
import sys
import colorlog
from datetime import datetime

class DiscordReconnectFilter(logging.Filter):
    """
    Filter to remove excessive reconnection messages from discord.py.
    
    This filter helps keep logs cleaner by filtering out common, repetitive
    reconnection messages that aren't critical for troubleshooting.
    """
    def __init__(self):
        """Initialize the reconnect filter."""
        super().__init__()
        self.is_in_traceback = False
        
    def filter(self, record):
        """
        Filter out common discord.py reconnection messages.
        
        Args:
            record (logging.LogRecord): The log record to check
            
        Returns:
            bool: False if the message should be filtered out, True otherwise
        """
        # Skip reconnection messages from discord.client
        if record.name == 'discord.client' and 'Attempting a reconnect in' in record.getMessage():
            return False
        
        # Get the log message
        message = record.getMessage()
        
        # Skip empty error messages or direct cause messages
        if message.strip() == '' or 'The above exception was the direct cause of the following exception:' in message:
            return False
            
        # Detect if we're entering a traceback
        if 'Traceback (most recent call last):' in message:
            self.is_in_traceback = True
            return False
        
        # Continue filtering if we're in a traceback
        if self.is_in_traceback:
            # Check if this is a continuation of the traceback
            if message.strip() == '' or not any([
                '  File "' in message,  # Line showing file location
                '    ' in message,      # Indented code line
                'Error:' in message,    # Error type declaration
                'Exception:' in message,# Exception type declaration
                'The above exception was' in message, # Chained exception message
                message.strip() == ''   # Empty line in traceback
            ]):
                # We've exited the traceback
                self.is_in_traceback = False
            else:
                # Still in traceback, filter it out
                return False
        
        # Skip specific error patterns
        if any(msg in message for msg in [
            'getaddrinfo failed',
            'ClientConnectorError', 
            'Cannot connect to host gateway', 
            'WebSocket closed with 1000',
            'ConnectionClosed',
            'socket.gaierror',
            'aiohttp.client_exceptions',
        ]):
            return False
            
        return True

class StreamToLogger:
    """
    File-like object that redirects writes to a logger.
    
    This class allows redirecting stdout/stderr to the logging system,
    ensuring that all output is properly captured in log files.
    
    Attributes:
        logger (logging.Logger): The logger to write to
        log_level (int): The logging level to use
        buffer (str): Buffer for accumulating text before logging
    """
    def __init__(self, logger, log_level=logging.INFO):
        """
        Initialize the stream to logger redirector.
        
        Args:
            logger (logging.Logger): The logger instance to write to
            log_level (int, optional): The logging level to use. Defaults to INFO.
        """
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ''
        
    def write(self, buf):
        """
        Write text to the logger.
        
        Args:
            buf (str): Text to write
        """
        for line in buf.rstrip().splitlines():
            # Skip lines that appear to be already formatted discord log messages
            if 'discord.' in line and ('[INFO' in line or '[ERROR' in line or '[DEBUG' in line or '[WARNING' in line):
                continue
            # Check if the line already contains log level indicators
            if '[INFO' in line or '[ERROR' in line:
                # Write directly to handlers to avoid double formatting
                for handler in self.logger.handlers:
                    handler.stream.write(line + '\n')
            else:
                # Use logger's formatting
                self.logger.log(self.log_level, line.rstrip())

    def flush(self):
        """Flush the stream (no-op for logging)."""
        pass

def setup_logging():
    """
    Set up the logging system for the bot.
    
    This function configures log formatting, file handlers, and console output.
    It should be called once during bot initialization.
    
    Returns:
        logging.Logger: The configured logger instance
    """
    # Create a custom logger
    logger = logging.getLogger('mirrobot')
    logger.setLevel(logging.DEBUG)  # Set the logging level
    
    # Create handlers for both file and console
    log_filename = f"logs/{datetime.now().strftime('bot_%Y-%m-%d.log')}"
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG) 
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO) 
    
    # Create a formatter and set it for file handler
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(formatter)
    
    # Create a colored formatter for the console handler using colorlog
    console_formatter = colorlog.ColoredFormatter(
        '%(log_color)s%(message)s',
        datefmt=None,
        reset=False,
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        },
        secondary_log_colors={},
        style='%'
    )
    console_handler.setFormatter(console_formatter)
    
    # Add handlers to the logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # Add the reconnect filter to the handlers
    reconnect_filter = DiscordReconnectFilter()
    file_handler.addFilter(reconnect_filter)
    console_handler.addFilter(reconnect_filter)
    
    # Configure the root discord logger to capture all discord.py modules
    discord_logger = logging.getLogger('discord')
    discord_logger.handlers = []  # Remove any existing handlers
    discord_logger.setLevel(logging.DEBUG)
    discord_logger.addHandler(file_handler)
    discord_logger.addHandler(console_handler)
    discord_logger.propagate = False  # Prevent double logging
    
    # Redirect stdout and stderr to the logging system
    sys.stdout = StreamToLogger(logger, logging.INFO)
    sys.stderr = StreamToLogger(logger, logging.ERROR)
    
    return logger

def get_logger():
    """
    Get the logger instance for the bot.
    
    If the logging system hasn't been set up yet, this will set it up.
    
    Returns:
        logging.Logger: The configured logger instance
    """
    return logging.getLogger('mirrobot')
