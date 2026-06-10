"""
Input validation helpers Module.

This file contains small functions that check if the information the user typed in
(like an email, phone number, or username) is formatted correctly before we try to search for it.
"""
import re

def is_email(value: str) -> bool:
    """
    Check if the input looks like a real email address.
    It makes sure there is text, followed by an '@' symbol, followed by more text, a period, and text.
    """
    return bool(re.match(r"[^@]+@[^@]+\.[^@]+", value))

def is_phone(value: str) -> bool:
    """
    Check if the input looks like a valid phone number.
    It allows an optional '+' at the beginning, followed by 7 to 15 numbers.
    """
    return bool(re.match(r"^\+?\d{7,15}$", value))

def is_username(value: str) -> bool:
    """
    Check if the input looks like a valid name or username.
    It allows letters, numbers, spaces, underscores, hyphens, periods, and @ symbols.
    The name must be between 2 and 50 characters long.
    """
    # If the user typed nothing, return False immediately.
    if not value:
        return False
        
    # Check the text against our allowed rules.
    return bool(re.match(r"^[a-zA-Z0-9_\-\s\.@]{2,50}$", value))