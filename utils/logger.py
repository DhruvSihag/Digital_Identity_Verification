"""
Centralized logging setup Module.

This file provides a standard way for our entire application to print messages
to the screen. Instead of using normal 'print()' statements, we use this logger
so that every message looks consistent and includes the time and the file it came from.
"""

import logging

def get_logger(name: str) -> logging.Logger:
    """
    Return a configured logger instance.
    
    You pass in the name of the file asking for the logger (usually '__name__').
    If the logger isn't set up yet, this function configures it to print out
    nice, readable text in the terminal.
    """
    # Create the logger object with the given name.
    logger = logging.getLogger(name)
    
    # If the logger doesn't have any handlers (meaning it hasn't been set up yet)...
    if not logger.handlers:
        
        # Create a tool that sends the messages to the terminal screen (console).
        handler = logging.StreamHandler()
        
        # Define exactly how the message should look.
        # Format: [Time] - [File Name] - [Severity Level] - [The Actual Message]
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        
        # Attach the format to the handler.
        handler.setFormatter(formatter)
        
        # Attach the handler to the logger.
        logger.addHandler(handler)
        
        # Tell the logger to only print messages that are 'INFO' level or higher
        # (It will ignore 'DEBUG' messages so the screen doesn't get too cluttered).
        logger.setLevel(logging.INFO)
        
    return logger
