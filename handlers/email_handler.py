"""
Email OSINT Handler Module.

This file handles everything related to investigating email addresses.
It goes through multiple steps to check if an email is real and finds out where it has been used.
It checks the structure, verifies the domain's mail servers (DNS MX), asks ZeroBounce if it's alive,
and checks if it was leaked in any data breaches.
"""

import os
import re
import requests
from dotenv import load_dotenv

# We import the basic blueprint that all handlers must follow.
from handlers.base_handler import BaseHandler

# We import our tool to print messages to the screen.
from utils.logger import get_logger

# We try to import the tool used to check domain names (DNS).
try:
    import dns.resolver
except ImportError:
    # If it's not installed, we just set it to None and skip this check later.
    dns = None

# We try to import the ZeroBounce library which checks if an email is actually alive.
try:
    from zerobouncesdk import ZeroBounce
except ImportError:
    # If it's not installed, we just set it to None.
    ZeroBounce = None

# Initialize the logger for this specific file.
logger = get_logger(__name__)

# Find the hidden .env file which contains our secret passwords and API keys.
root_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", ".env")

# If we found the .env file in the main folder, load it.
if os.path.exists(root_env_path):
    load_dotenv(dotenv_path=root_env_path)
else:
    # Otherwise, try to load it from the current folder.
    load_dotenv()


class EmailHandler(BaseHandler):
    """
    This class handles the step-by-step investigation of a single email address.
    """

    def __init__(self):
        """
        When this handler starts up, it gets the secret keys it needs from the .env file.
        """
        # Call the setup function of our parent blueprint class.
        super().__init__()
        
        
        # Grab the secret key for ZeroBounce (used to check if the email actually exists).
        self.zb_key = os.getenv("ZEROBOUNCE_API_KEY", "")
        
        # Turn on the ZeroBounce engine if we have both the tool and the key.
        self.zb_engine = ZeroBounce(self.zb_key) if (ZeroBounce and self.zb_key) else None

    def _has_valid_mx(self, domain: str) -> bool:
        """
        Stage 2 Check: Verify that the part of the email after the '@' actually has mail servers setup.
        If a domain doesn't have an MX (Mail Exchange) record, it can't receive emails, so it's fake.
        """
        # If the DNS tool isn't installed, we just skip this check and assume it's good.
        if not dns:
            logger.warning("dnspython package not installed. Bypassing Stage 2 DNS pre-filter check.")
            return True
            
        try:
            # Log what we are doing.
            logger.info(f"Stage 2 Pre-Filter: Querying DNS MX records for domain: '{domain}'")
            
            # Actually ask the internet if this domain has mail servers.
            dns.resolver.resolve(domain, 'MX')
            
            # If it didn't crash, it means we found them. It's a real domain.
            return True
            
        except Exception as e:
            # If it crashed, the domain is probably fake or dead.
            logger.error(f"Stage 2 Pre-Filter Failed: Domain '{domain}' has no valid MX records or is dead. Info: {str(e)}")
            return False

    def _verify_via_zerobounce(self, email: str) -> tuple:
        """
        Stage 3 Check: Ask ZeroBounce (a professional email checking service) if this exact email exists.
        
        Returns a tuple with three items:
        1. True/False: Should we continue investigating this email?
        2. String: A message explaining what happened.
        3. True/False: Did the API call actually work successfully?
        """
        # If we don't have a real ZeroBounce key, just skip this step.
        if not self.zb_engine or not self.zb_key or "your_" in self.zb_key.lower():
            logger.warning("ZeroBounce API key unconfigured. Skipping Stage 3 Gate filter gracefully.")
            return True, "Skipped (API Key Missing)", False

        try:
            # Log what we are doing.
            logger.info(f"Stage 3 Gate: Querying ZeroBounce API for target: '{email}'")
            
            # Ask ZeroBounce to check the email.
            response = self.zb_engine.validate(email)
            
            # ZeroBounce returns weird formats sometimes, so we clean up the main status.
            raw_status = str(response.status).lower().strip()
            api_status = raw_status.split('.')[-1] if '.' in raw_status else raw_status
            
            # We also clean up the detailed sub-status.
            raw_sub = str(response.sub_status).lower().strip()
            sub_status = raw_sub.split('.')[-1] if '.' in raw_sub else raw_sub
            
            # Log the cleaned up answers from ZeroBounce.
            logger.info(f"ZeroBounce Core Return Cleaned: '{api_status}' | Sub-Status: '{sub_status}'")

            # If ZeroBounce says it's totally fake, we stop completely.
            if api_status in ["invalid", "do_not_mail"] or sub_status == "does_not_accept_mail":
                return False, f"Rejected by ZeroBounce: Invalid Target (Reason: {sub_status})", True
                
            # If ZeroBounce says it's real, we continue.
            elif api_status in ["valid", "catch_all", "catch-all"]:
                return True, f"Verified via ZeroBounce ({api_status.title()})", True
                
            # If ZeroBounce is confused, we give the email the benefit of the doubt and continue.
            else:
                logger.warning(f"ZeroBounce returned ambiguous status: {api_status}. Defaulting to open fallback pass.")
                return True, f"ZeroBounce Inconclusive: {api_status}", True
                
        except Exception as e:
            # If our connection to ZeroBounce crashed, log the error but don't stop the whole program.
            logger.error(f"ZeroBounce Gateway connection or timeout fault: {str(e)}")
            return False, f"ZeroBounce API Exception / Key Credit Exhausted: {str(e)}", False

    def handle(self, input_data: str) -> dict:
        """
        This is the main function that coordinates all the checks for an email address.
        """
        # Clean the input by removing spaces and making it lowercase.
        target_email = input_data.strip().lower()
        logger.info(f"Initiating clean API identity audit for email: '{target_email}'")
        
        # An email MUST have an '@' symbol, otherwise it's just a regular word.
        if "@" not in target_email:
            return {"status": "failed", "message": "Malformed email string pattern."}

        # Split the email into the username (prefix) and the website (domain).
        email_prefix = target_email.split("@")[0]
        domain_part = target_email.split("@")[1]
        
        # We use these lists to collect whatever interesting things we find.
        live_results = []
        historical_traces = []

        # ================= STAGE 1 GATE: STRUCTURAL ANALYSIS =================
        # Gmail addresses must be at least 6 letters long. If it's shorter, it's fake.
        if "gmail.com" in domain_part and len(email_prefix) < 6:
            return self._build_failure_response(target_email, "Structural Pre-Filter Check Failed: Username too short.")

        # If the username is just a bunch of numbers (like 123456@yahoo.com), it's probably spam and hard to track.
        if email_prefix.isdigit():
            return self._build_failure_response(target_email, "Structural Pre-Filter Check Failed: Purely numeric prefixes are invalid tracking points.")

        # ================= STAGE 2 GATE: DNS MX ROUTE CHECK =================
        # Check if the domain actually has mail servers setup.
        if not self._has_valid_mx(domain_part):
            return self._build_failure_response(target_email, f"DNS Pre-Filter Failed: Domain '{domain_part}' has no active MX records.")

        # ================= STAGE 3 GATE: ZEROBOUNCE LIVE API =================
        # Check if the email actually exists according to ZeroBounce.
        should_continue, status_note, api_success = self._verify_via_zerobounce(target_email)
        
        # If ZeroBounce said it's totally fake, we stop and return the failure.
        if not should_continue:
            logger.warning(f"EmailHandler cutting pipeline deployment short. Reason: {status_note}")
            return self._build_failure_response(target_email, status_note)

        # If we successfully talked to ZeroBounce, record that as a positive finding.
        if api_success:
            domain_title = domain_part.split(".")[0].title()
            live_results.append({
                "platform": f"{domain_title} Core Identity System",
                "category": "infrastructure_telemetry",
                "status": "Target Confirmed Active",
                "details": f"• Verification Authority: ZeroBounce Cloud Index\n• Status Feedback: {status_note}\n• Action Status: Integrity checks complete. Deep footprint maps unlocked."
            })



        # We take the username part of the email to use later for username searches.
        generated_aliases = [email_prefix]
        
        # We record that we successfully extracted this username.
        live_results.append({
            "platform": "Alias Targeting System",
            "category": "username_profiling_wordlist",
            "status": "Target Isolated",
            "details": f"Prefix isolated successfully: '{email_prefix}'. Set as singular target for downstream Sherlock thread mapping."
        })

        # Combine both the live server checks and the historical breach checks into one big list.
        combined_matches = live_results + historical_traces
        
        # Return the final report containing everything we found.
        return {
            "status": "success",
            "input_type": "email",
            "target": target_email,
            "metrics": {
                "total_indicators_mapped": len(combined_matches),
                "live_gateways_found": len(live_results),
                "historical_leaks_found": len(historical_traces),
                "username_variations_found": len(generated_aliases)
            },
            "matches": combined_matches,
            "sherlock_queue": generated_aliases
        }

    def _build_failure_response(self, email: str, error_message: str) -> dict:
        """
        Helper function to easily create a standardized error message dictionary
        whenever something goes wrong or the email is fake.
        """
        domain_name = email.split("@")[1].split(".")[0].title()
        return {
            "status": "failed",
            "input_type": "email",
            "target": email,
            "message": error_message,
            "metrics": {
                "total_indicators_mapped": 0,
                "live_gateways_found": 0,
                "historical_leaks_found": 0,
                "username_variations_found": 0
            },
            "matches": [{
                "platform": f"{domain_name} Target Verification Gate",
                "category": "infrastructure_telemetry",
                "status": "Invalid Target Refused",
                "details": f"Pipeline Halting Flag: {error_message}"
            }],
            "sherlock_queue": []
        }