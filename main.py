"""
Main Module.
This is the central entry point for the entire OSINT tool framework.
It takes whatever the user types in, hands it over to the dispatcher to do the heavy lifting,
and then packages the final results nicely to send back to the frontend.
"""

import json
from dispatcher import CommandDispatcher
from utils.logger import get_logger

# We set up our logger here so we can record exactly what the framework is doing at any time.
logger = get_logger(__name__)

class OSINTFramework:
    """
    The OSINTFramework acts as the main engine.
    It connects the inputs from the user directly to our backend search tools.
    """

    def __init__(self):
        """
        When the OSINTFramework is created, it gets everything ready to start a search.
        Specifically, it creates a CommandDispatcher, which is the "traffic cop" that 
        will eventually route our searches to the right places.
        """
        # Create the dispatcher that will handle sorting our inputs
        self.dispatcher = CommandDispatcher()

    def run_scan(self, input_targets: list[str]) -> dict:
        """
        This function is the main trigger to start the entire scanning process.
        It takes a list of targets (like emails or usernames), feeds them into the system,
        and waits for the final data to come back.
        """
        # Record what we are about to search so we have a log of it.
        logger.info(f"OSINT Framework processing target payload: {input_targets}")
        
        # We use a try-except block here to make sure that if the search completely crashes, 
        # the entire program doesn't break. Instead, we can catch the error safely.
        try:
            # Tell the dispatcher to take these targets and start the full OSINT search.
            return self.dispatcher.dispatch(input_targets)
            
        except Exception as e:
            # If something terrible happens during the scan, we record a critical error.
            logger.critical(f"Global framework handling error: {str(e)}")
            
            # We return a simple, clean dictionary with the error message so the user knows what went wrong.
            return {"status": "error", "message": f"Framework scan failure: {str(e)}"}
