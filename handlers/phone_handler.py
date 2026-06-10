"""
Phone OSINT Handler Module.

This file handles everything related to investigating phone numbers.
It uses two main tools:
1. Numverify: A website that checks if a phone number is currently active and who the carrier is.
2. Phonenumbers: A Google tool built into Python that figures out the format, country, and original network of a number.

Example usage:
    handler = PhoneHandler()
    result = handler.handle("9413909502")
"""

import os
import requests
import json
from dotenv import load_dotenv

# We import the basic blueprint that all handlers must follow.
from handlers.base_handler import BaseHandler

# We import our tool to print messages to the screen.
from utils.logger import get_logger

# We try to import the phonenumbers library safely.
try:
    import phonenumbers
    from phonenumbers import geocoder, carrier as phone_carrier
except ImportError:
    # If the user forgot to install it, we just set it to None.
    phonenumbers = None

# Initialize the logger for this specific file.
logger = get_logger(__name__)

# Find the hidden .env file which contains our secret API keys.
root_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", ".env")

# Load the environment variables into memory.
if os.path.exists(root_env_path):
    load_dotenv(dotenv_path=root_env_path)
else:
    load_dotenv()


class PhoneHandler(BaseHandler):
    """
    This class handles the step-by-step investigation of a single phone number.
    It cleans up the number, checks the cloud, and checks offline databases.
    """

    def __init__(self):
        """
        When this handler starts up, it gets the Numverify secret key from the .env file.
        """
        # Call the setup function of our parent blueprint class.
        super().__init__()
        
        # Grab the secret key for Numverify.
        self.numverify_key = os.getenv("NUMVERIFY_API_KEY", "")

    def _sanitize_and_normalize(self, raw_input: str) -> str:
        """
        Cleans up the phone number string.
        It removes any dashes, spaces, or letters, leaving only pure numbers.
        It also tries to automatically add the country code if it's missing.
        """
        # If the user didn't type anything, just return blank.
        if not raw_input:
            return ""
            
        # Keep only the characters that are numbers (e.g. "123-456" becomes "123456").
        clean_num = "".join(filter(str.isdigit, raw_input))
        
        # If the number starts with a 0 and is 11 digits long, remove the 0.
        # (This is common for local calls in some countries).
        if raw_input.strip().startswith("0") and len(clean_num) == 11:
            clean_num = clean_num[1:]

        # If the number is exactly 10 digits, we guess it's an Indian number and add '91' to the front.
        if len(clean_num) == 10:
            clean_num = f"91{clean_num}"
            
        return clean_num

    def _query_numverify_api(self, clean_numeric: str) -> dict:
        """
        Asks the Numverify website if this phone number is currently active and 
        who the carrier (like AT&T or Verizon) is right now.
        """
        logger.info(f"Querying Numverify live data registry for: {clean_numeric}")
        
        # If we don't have a real API key, we skip this step so the program doesn't crash.
        if not self.numverify_key or "placeholder" in self.numverify_key.lower():
            logger.warning("Skipping Numverify network layer: Valid API access key is missing.")
            return {}

        # Build the exact URL we need to ask Numverify.
        url = f"http://apilayer.net/api/validate?access_key={self.numverify_key}&number={clean_numeric}&country_code=IN&format=1"
        
        try:
            # Send the request over the internet.
            res = requests.get(url, timeout=7)
            
            # If the website responded successfully (code 200)...
            if res.status_code == 200:
                data = res.json()
                logger.debug(f"Numverify Raw API Response Payload: {data}")
                
                # If they gave us an error message back, log it and stop.
                if "error" in data:
                    logger.error(f"Numverify API Gate Refused Request: {data['error'].get('info')}")
                    return {}

                # If the number is valid, we organize the data into a clean dictionary and return it.
                if data.get("valid") is True:
                    return {
                        "valid": True,
                        "carrier": data.get("carrier") or "Unknown Operator Switch",
                        "line_type": str(data.get("line_type")).title() or "Mobile SIM Card",
                        "country": data.get("country_name", "India")
                    }
                    
        except Exception as e:
            # If our internet connection failed entirely, just log it.
            logger.error(f"Numverify cloud gateway communication failure thread execution dropped: {str(e)}")
            
        return {}

    def _execute_native_library(self, clean_numeric: str) -> list:
        """
        Uses the Google phonenumbers library (which works offline) to figure out 
        where the number comes from and what kind of number it is.
        """
        library_results = []
        
        # Format the number with a '+' sign, which is standard for international numbers.
        formatted_e164 = f"+{clean_numeric}"
        logger.info(f"Initiating native Python phonenumbers database lookup for: {formatted_e164}")
        
        # If the user forgot to install the library, print an error and stop.
        if not phonenumbers:
            logger.error("Native parsing library is missing. Ensure 'pip install phonenumbers' executed cleanly.")
            return library_results

        try:
            # Tell the library to analyze our formatted number. We guess 'IN' (India) as the default.
            parsed_number = phonenumbers.parse(formatted_e164, "IN")
            
            # Check if it actually looks like a real phone number structurally.
            if phonenumbers.is_valid_number(parsed_number):
                
                # 1. Try to find the original network carrier name.
                original_carrier = phone_carrier.name_for_number(parsed_number, "en")
                if not original_carrier:
                    original_carrier = "Indian Mobile Operator Network Grid"
                    
                # 2. Try to find the geographic region (like the state or city) the number belongs to.
                circle_location = geocoder.description_for_number(parsed_number, "en") or "National Routing Zone"
                
                # 3. Figure out if it's a mobile phone, landline, or VoIP.
                num_type = phonenumbers.number_type(parsed_number)
                line_profile = "Mobile SIM Card" if num_type == 1 else "Fixed Landline / VoIP Connection"
                
                # Put all this information together into a readable text block.
                summary_details = (
                    f"• Structural Format: {line_profile}\n"
                    f"• Region/Circle Assignment: {circle_location}\n"
                    f"• Original Registered Carrier: {original_carrier}\n"
                    f"• Country Validity Index: Valid E.164 Route"
                )
                
                # Add this finding to our list.
                library_results.append({
                    "platform": "Native Phonenumbers Core",
                    "category": "telecom_metadata_registry",
                    "status": "Scan Complete",
                    "details": summary_details
                })
                
        except Exception as e:
            # If the parser crashed, catch the error so the whole app doesn't die.
            logger.error(f"Native telecommunication library parser execution fault: {str(e)}")
            
        return library_results

    def handle(self, input_data: str) -> dict:
        """
        This is the main function that coordinates all the checks for a phone number.
        """
        # Remove extra spaces around the input.
        raw_phone = input_data.strip()
        logger.info(f"Initiating clean telephone identifier audit for payload: '{raw_phone}'")
        
        # Layer 0: Clean up the messy input so we just have pure numbers.
        clean_numeric_str = self._sanitize_and_normalize(raw_phone)
        
        # If there were no numbers at all, fail immediately.
        if not clean_numeric_str:
            return {
                "status": "failed",
                "message": "The system failed to extract any meaningful numeric digits from the input string handle."
            }
            
        # Add the '+' sign back on for standardized formatting.
        normalized_target = f"+{clean_numeric_str}"
        
        live_matches = []
        infrastructure_count = 0
        
        # Layer 1: Ask the Numverify website for live data.
        meta = self._query_numverify_api(clean_numeric_str)
        
        # If they gave us good data back...
        if meta and meta.get("valid"):
            infrastructure_count = 1
            # Add it to our results list.
            live_matches.append({
                "platform": f"Live Network State: {meta.get('carrier')}",
                "category": "infrastructure_telemetry",
                "status": meta.get("line_type"),
                "details": f"• Current Active Carrier: {meta.get('carrier')}\n• Registration Country Base: {meta.get('country')}\n• Routing Status: Live Switch Active"
            })
        else:
            logger.warning("Omitting cloud infrastructure report metrics cards from final telemetry matrix array.")

        # Layer 2: Use the offline Google database to find out where the number is from.
        native_hits = self._execute_native_library(clean_numeric_str)
        if native_hits:
            # Combine these findings with our live findings.
            live_matches.extend(native_hits)

        # If we couldn't find ANYTHING using either method, we report a failure.
        if not live_matches:
            return {
                "status": "failed",
                "message": "All analytical tracking pipelines returned empty configuration matrices for this target."
            }

        # Return a big dictionary containing all our success metrics and findings.
        return {
            "status": "success",
            "input_type": "phone",
            "target": normalized_target,
            "metrics": {
                "total_indicators_mapped": len(live_matches),
                "infrastructure_records": infrastructure_count,
                "social_profiles_found": len(live_matches) - infrastructure_count
            },
            "matches": live_matches
        }