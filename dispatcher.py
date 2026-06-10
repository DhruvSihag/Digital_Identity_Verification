"""
Dispatcher Module.
This file is the "traffic cop" of the application. 
When a user provides an input (like an email, phone number, or username), 
this module looks at the input, figures out what type it is, and sends it 
to the correct specialist tool (handler) to get the data.

It is designed to work in the background and return data as a simple dictionary 
so that it can be easily sent over the internet as JSON.
"""

import os
import requests
import concurrent.futures
from utils.validators import is_email, is_phone, is_username
from utils.logger import get_logger
from utils.csv_helper import append_master_row
from handlers.email_handler import EmailHandler
from handlers.phone_handler import PhoneHandler
from handlers.username_handler import UsernameHandler
from agents.url_agent import UrlAgent
from agents.instagram_agent import InstagramAgent

logger = get_logger(__name__)

class CommandDispatcher:
    """
    The CommandDispatcher acts as the main manager. 
    It knows about all the different handlers and AI agents that can search for data.
    """

    def __init__(self):
        """
        When the CommandDispatcher is created, it prepares its "tools".
        We set up handlers for emails, phones, and usernames so they are ready to use.
        We also set up the special AI agents (URL and Instagram) that will be used 
        later to dig deeper into specific profiles.
        """
        self.handlers = {
            "email": EmailHandler(),
            "phone": PhoneHandler(),
            "username": UsernameHandler()
        }
        self.url_agent = UrlAgent()
        self.instagram_agent = InstagramAgent()

    def _enrich_special_profiles(self, matches: list):
        """
        This function takes a list of profiles we found and tries to get more details (like a bio or profile picture).
        We don't want to scan every single website on the internet because it takes too long.
        So, we check if the link belongs to a "whitelisted" website (like Pinterest or Hackerearth).
        If it does, we use the URL Agent (an AI tool) to read the page and pull out the extra details.
        Finally, it adds this new data straight into the original profile dictionary so everything is kept together.
        """
        # We only want our AI to spend time scanning these specific websites to save time and money.
        whitelist = ["pinterest.com", "hackerearth.com", "hackerrank.com", "gravatar.com"]

        for profile in matches:
            url = profile.get("url") if isinstance(profile, dict) else str(profile)
            
            if not url:
                continue
                
            # We check if the URL contains any of our whitelisted domains.
            if any(domain in url for domain in whitelist):
                logger.info(f"Dispatcher found whitelisted target: {url}. Initiating URL Agent...")
                
                # We ask the URL Agent to visit the link and find the bio and avatar.
                try:
                    agent_output = self.url_agent.execute(url)
                    
                    if isinstance(agent_output, dict):
                        bio_text = agent_output.get("bio") or ""
                        image_url = agent_output.get("avatar_url")
                    else:
                        bio_text = str(agent_output)
                        words = bio_text.split()
                        image_url = next((word for word in words if word.startswith("http") and any(ext in word.lower() for ext in ["jpg", "png", "jpeg"])), None)
                    
                    local_image_path = None
                    # If the AI found a profile picture link, we want to download it and save it to our computer.
                    # This way, we have a local copy of the image to show on our dashboard.
                    if image_url:
                        # Make sure the 'avatars' folder exists before we try to save a file inside it.
                        os.makedirs("avatars", exist_ok=True)
                        safe_name = url.replace("/", "_").replace(":", "_")
                        local_image_path = f"avatars/{safe_name}.jpg"
                        try:
                            img_data = requests.get(image_url, timeout=10).content
                            with open(local_image_path, 'wb') as img_file:
                                img_file.write(img_data)
                            logger.info(f"Successfully downloaded avatar to {local_image_path}")
                        except Exception as img_err:
                            logger.error(f"Failed downloading avatar image: {str(img_err)}")
                            local_image_path = None

                    # Now that we have the extra info, we attach it directly into the profile's dictionary.
                    # We do this so that when we send the final report to the frontend, all the data is in one place.
                    if isinstance(profile, dict):
                        profile["enriched_data"] = {
                            "bio": bio_text,
                            "avatar_url": image_url,
                            "local_avatar_path": local_image_path
                        }

                    # Log tasks to CSV and Markdown
                    try:
                        append_master_row(url, bio_text, image_url, local_image_path, csv_path="extracted_profiles.csv")
                    except Exception as csv_err:
                        logger.error(f"Failed writing to extracted_profiles.csv: {str(csv_err)}")

                    try:
                        with open("extracted_profiles_report.md", "a", encoding="utf-8") as log_file:
                            log_file.write(f"\n## Target Search: `{url}`\n\n")
                            log_file.write(f"### Extracted Bio / Results\n")
                            log_file.write(f"> {bio_text}\n\n---\n")
                    except Exception as log_err:
                        logger.error(f"Failed writing extracted_profiles_report.md: {str(log_err)}")

                    try:
                        with open("api_transaction_logs.md", "a", encoding="utf-8") as cost_file:
                            cost_file.write(f"- **Target:** `{url}` | **Status:** Transaction complete\n")
                    except Exception as cost_err:
                        logger.error(f"Failed writing api_transaction_logs.md: {str(cost_err)}")

                except Exception as e:
                    logger.error(f"Synchronous worker crashed for {url}: {str(e)}")
                    if isinstance(profile, dict):
                        profile["enriched_data"] = {
                            "error": str(e)
                        }

    def dispatch(self, input_data: list[str]) -> dict:
        """
        This is the main function that gets called when a new search starts.
        It takes a list of targets (like emails or phones), decides what type each target is,
        and sends it to the right handler. It gathers all the results and returns one big final report.
        """
        # If the user accidentally sent a single text string instead of a list, 
        # we wrap it in a list so the rest of our code doesn't break.
        if isinstance(input_data, str):
            input_data = [input_data]
            
        logger.info(f"Analyzing and routing batch input payload: {input_data}")

        final_report = {
            "status": "success",
            "inputs_processed": input_data,
            "email_results": [],
            "phone_results": [],
            "username_results": [],
            "instagram_results": [],
            "all_matches": []
        }

        usernames_to_scan = set()

        try:
            # We go through every single target the user gave us one by one.
            for target in input_data:
                target = target.strip()
                # If the target is just empty spaces, we skip it and move to the next one.
                if not target:
                    continue

                # We use a validator to guess if this target looks like an email address.
                if is_email(target):
                    logger.info(f"Target '{target}' identified as EMAIL.")
                    email_result = self.handlers["email"].handle(target)
                    final_report["email_results"].append(email_result)
                    
                    if isinstance(email_result, dict) and email_result.get("status") == "success":
                        # Sometimes an email address can give us a username (e.g. john from john@gmail.com).
                        # We save these usernames into a list so we can scan them later.
                        aliases = email_result.get("sherlock_queue", [])
                        usernames_to_scan.update(aliases)
                        
                        # Add email matches
                        for match in email_result.get("matches", []):
                            if match not in final_report["all_matches"]:
                                final_report["all_matches"].append(match)
                                
                elif is_phone(target):
                    logger.info(f"Target '{target}' identified as PHONE.")
                    phone_result = self.handlers["phone"].handle(target)
                    final_report["phone_results"].append(phone_result)
                    
                    if isinstance(phone_result, dict) and phone_result.get("status") == "success":
                        for match in phone_result.get("matches", []):
                            if match not in final_report["all_matches"]:
                                final_report["all_matches"].append(match)

                elif is_username(target):
                    logger.info(f"Target '{target}' identified as USERNAME.")
                    usernames_to_scan.add(target)
                    
                else:
                    logger.warning(f"Unrecognized input pattern: '{target}'")

            # Now we look at all the usernames we found (both directly from the user and from the emails).
            # We use a 'set' earlier so we don't scan the same username twice. This saves time.
            for alias in usernames_to_scan:
                logger.info(f"Dispatcher executing deduplicated username scan for: '{alias}'")
                try:
                    logger.info(f"Initiating parallel execution: Sherlock and Instagram Agent for alias: '{alias}'")
                    
                    # We use a ThreadPoolExecutor to run Sherlock and the Instagram AI simultaneously
                    # This cuts the scanning time in half since both tasks wait for the internet.
                    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                        # Submit both tasks to the background threads
                        future_sherlock = executor.submit(self.handlers["username"].handle, alias)
                        future_insta = executor.submit(self.instagram_agent.execute, alias)
                        
                        # Wait for both tasks to finish and grab their results
                        username_result = future_sherlock.result()
                        insta_output = future_insta.result()

                    final_report["username_results"].append(username_result)
                    
                    if isinstance(username_result, dict) and username_result.get("status") == "success":
                        discovered_profiles = username_result.get("matches", [])
                        for profile in discovered_profiles:
                            if profile not in final_report["all_matches"]:
                                final_report["all_matches"].append(profile)
                    
                    # Store Instagram data
                    insta_data_block = {
                        "target_username": alias,
                        "platform": "Instagram",
                        "status": "Target Profile Analysis",
                        "extracted_data": insta_output
                    }
                    
                    # Download avatar
                    image_url = insta_output.get("avatar_url")
                    if image_url:
                        os.makedirs("avatars", exist_ok=True)
                        safe_name = f"instagram_{alias}"
                        local_image_path = f"avatars/{safe_name}.jpg"
                        try:
                            img_data = requests.get(image_url, timeout=10).content
                            with open(local_image_path, 'wb') as img_file:
                                img_file.write(img_data)
                            # Store the local path for cleanup
                            insta_output["local_avatar_path"] = local_image_path
                        except Exception as e:
                            logger.error(f"Failed downloading IG avatar: {e}")
                            
                    final_report["instagram_results"].append(insta_data_block)

                except Exception as sub_err:
                    logger.error(f"Automated execution failed for alias '{alias}': {str(sub_err)}")

            # Finally, we have gathered a giant list of all the profile links we found across the internet.
            # We send this entire list to our URL Agent enrichment function.
            # It will check if any of these links belong to websites it knows how to read, and if so, it grabs more details.
            if final_report["all_matches"]:
                logger.info(f"Enriching {len(final_report['all_matches'])} total combined profiles...")
                self._enrich_special_profiles(final_report["all_matches"])

            return final_report

        except Exception as e:
            logger.error(f"Critical execution error during batch dispatch routing: {str(e)}")
            return {
                "status": "error",
                "message": f"An error occurred inside the dispatcher subsystem: {str(e)}"
            }