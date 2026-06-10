"""
Abstract Base Handler Module.

This file provides a foundational blueprint (a template) that all other specific handlers
(like the Email Handler, Phone Handler, etc.) must follow. It ensures that every handler
has the exact same basic structure, which keeps the code organized and predictable.
"""

# We import special tools from Python that let us create "Abstract" classes.
# An Abstract class is like a blueprint—you can't use it directly, you can only build upon it.
from abc import ABC, abstractmethod

class BaseHandler(ABC):
    """
    Abstract base class for all data handlers.
    Think of this as a contract that all child handlers must sign.
    """

    @abstractmethod
    def handle(self, input_data: str) -> dict:
        """
        Process the raw input data (like an email string) and return the results as a dictionary.
        Because this has the '@abstractmethod' tag, Python will force every specific handler
        to write their own custom version of this function.
        """
        pass