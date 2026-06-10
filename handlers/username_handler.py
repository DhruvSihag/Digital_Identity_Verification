"""
Username OSINT Handler Module.

This file uses the 'Sherlock' tool, which is a massive scanner that searches
over 400 different social media websites to see if a username exists on them.
It runs Sherlock in the background and reads the results.
"""

import os
import subprocess

# Import our basic blueprint for handlers.
from handlers.base_handler import BaseHandler

# Import configuration
from config import Config

# Import our tool to print messages to the screen.
from utils.logger import get_logger

# Initialize the logger for this file.
logger = get_logger(__name__)

class UsernameHandler(BaseHandler):
    """
    This class handles the searching of a specific username across the internet.
    It acts as a controller that starts the Sherlock tool behind the scenes.
    """

    def __init__(self):
        """
        When this handler starts up, call the parent blueprint's setup function.
        """
        super().__init__()

    def handle(self, input_data: str) -> dict:
        """
        This is the main function that takes a username, feeds it to Sherlock, 
        and organizes the results.
        """
        # Clean up the username by removing spaces.
        target_username = input_data.strip()
        logger.info(f"Routing target username '{target_username}' to Sherlock CLI engine...")
        
        # We will put all the websites we find the user on into this list.
        discovered_matches = []
        
        # Sherlock automatically creates a text file named after the username to store its results.
        output_filename = f"{target_username}.txt"

        try:
            # We build the command just like we would type it in the terminal.
            # Example: sherlock john_doe --timeout 5
            # We set a timeout so Sherlock doesn't get stuck forever on a slow website.
            cmd = ["sherlock", target_username, "--timeout", Config.SHERLOCK_TIMEOUT]
            
            logger.info(f"Launching subprocess execution: {' '.join(cmd)}")
            
            # We run the command. 
            # DEVNULL hides all the messy output so our terminal doesn't get spammed.
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Once Sherlock is finished running, check if it actually created the results file.
            if os.path.exists(output_filename):
                logger.info(f"Sherlock scan report file found. Commencing footprint parsing...")
                
                # Open the file and read it line by line.
                with open(output_filename, "r", encoding="utf-8") as file:
                    for line in file:
                        # Clean up any invisible newline characters at the end of the text.
                        line = line.strip()
                        
                        # Sherlock puts the actual profile link on lines that start with http.
                        if line.startswith("http://") or line.startswith("https://"):
                            
                            # We break the URL apart to figure out what website it is.
                            # e.g., https://www.instagram.com/user -> 'instagram'
                            domain_parts = line.split("/")
                            platform_name = domain_parts[2].replace("www.", "").split(".")[0].capitalize()
                            
                            # Add this profile to our list of findings.
                            discovered_matches.append({
                                "platform": platform_name,
                                "category": "social_presence",
                                "url": line,
                                "status": "Verified Profile Account Located"
                            })
                
                # Housekeeping: Delete the text file so we don't litter the hard drive.
                os.remove(output_filename)
                logger.info("Temporary target scan text report cleared from server memory cache.")
                
            else:
                # If there's no file, it means Sherlock didn't find them anywhere.
                logger.warning(f"Sherlock successfully executed but no authenticated data surfaced for: {target_username}")

            # Return a big dictionary containing all our success metrics and findings.
            return {
                "status": "success",
                "input_type": "username",
                "target": target_username,
                "metrics": {
                    "total_profiles_located": len(discovered_matches)
                },
                "matches": discovered_matches
            }

        except subprocess.CalledProcessError as cmd_err:
            # If the Sherlock tool crashed or failed to run, we catch the error here.
            logger.error(f"Sherlock sub-process system pipeline threw an execution fault: {str(cmd_err)}")
            return {"status": "error", "message": f"Sherlock core execution failure: {str(cmd_err)}"}
            
        except Exception as e:
            # If something else completely unexpected happens, log it so the app doesn't die.
            logger.critical(f"Fatal disruption inside UsernameHandler orchestrator: {str(e)}")
            return {"status": "error", "message": f"Global thread collection failure: {str(e)}"}