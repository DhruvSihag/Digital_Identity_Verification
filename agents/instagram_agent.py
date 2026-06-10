"""
Instagram Specialist AI Agent Module.

This file contains an artificial intelligence Agent specifically designed to look at
Instagram profiles. Because Instagram is very strict, we use a real Google Chrome browser 
profile to look at the pages so Instagram thinks we are a real human.
"""

import asyncio
import os
import json
import re

# We import the tools to control a real web browser.
from browser_use import Agent, Browser, BrowserProfile

# We import the OpenAI connector to give our agent a brain.
from browser_use.llm import ChatOpenAI

# We import our custom logger to print updates to the terminal.
from utils.logger import get_logger

# Import our configuration settings
from config import Config

# Initialize the logger for this file.
logger = get_logger(__name__)

# 🛠️ THE ARCHITECTURE FIX: 
# The browser-use library needs to know what AI provider we are using.
# LangChain doesn't provide this by default, so we manually inject the word "openai".
class PatchedChatOpenAI(ChatOpenAI):
    @property
    def provider(self):
        """Tell the browser tool that we are using OpenAI."""
        return "openai"

    def __getattr__(self, name):
        """
        Force the agent to use the configured model if it asks for a model name.
        """
        if name == "model":
            return getattr(self, "model_name", Config.OPENAI_MODEL)
        try:
            return super().__getattr__(name)
        except AttributeError:
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

class InstagramAgent:
    """
    A standalone tool designed to analyze Instagram profiles securely.
    """

    def __init__(self):
        """
        When the InstagramAgent starts, it reaches into the .env file to grab
        the secret OpenAI API key needed to power the AI brain.
        """
        self.api_key = os.getenv("OPENAI_API_KEY")

    async def _scrape_instagram_async(self, target_username: str) -> dict:
        """
        THE ENGINE (Asynchronous):
        This function controls the web browser to extract data specifically from Instagram.
        It runs asynchronously so it doesn't block the rest of the application.
        """
        # Safety check: ensure the API key exists before trying to run the AI.
        if not self.api_key:
            return {"error": "OPENAI_API_KEY is missing from your .env file."}

        # Log our intended target.
        logger.info(f"Targeting Instagram profile with AI Agent: {target_username}")
        
        # Step 1: Create the AI brain using our patched wrapper class.
        llm = PatchedChatOpenAI(model=Config.OPENAI_MODEL, api_key=self.api_key)
        
        # Step 2: Configure and turn on the personal Chrome browser.
        # This is critical for Instagram because it requires a logged-in session to view profiles properly.
        profile = BrowserProfile(
            # The location of the Chrome application on this computer.
            executable_path=Config.CHROME_EXECUTABLE_PATH,
            # The folder where Chrome stores all your login cookies and history.
            user_data_dir=Config.CHROME_USER_DATA_DIR,
            # The exact Chrome profile we want to use.
            profile_directory=Config.CHROME_PROFILE_DIRECTORY
        )
        # Create the browser object.
        browser = Browser(browser_profile=profile)

        # Step 3: Build the exact URL for the Instagram profile.
        target_url = f"https://www.instagram.com/{target_username}/"

        # Step 4: Write the specific mission instructions for Instagram.
        mission = f"""
        Navigate to this exact URL: {target_url}

        You are an automated OSINT data extractor. Your ONLY goal is to extract the full Instagram profile bio, the perfect profile picture URL, the profile URL itself, and the text of the top 3 recent posts.
        
        STRICT EXECUTION RULES:
        1. Wait 3 seconds for the page to fully load.
        2. Look for the user's bio/description text. You must extract the FULL bio, capturing every single word and newline. Ensure newlines are escaped properly as \\n in the JSON output.
        3. Look for the user's profile picture image URL. DO NOT TRUNCATE URLs. When extracting the avatar_url, you must output the full, exact, completely unedited URL so it can be opened directly. Never use ellipses (...) or summarize the link.
        4. If the page says "Sorry, this page isn't available" or "User not found", or there is clearly no profile, immediately stop and set "profile_status" to "no profile found".
        5. DO NOT get confused by advanced JavaScript DOM. Do not use complex javascript to bypass shadow DOMs. Rely strictly on simple native tools like `extract` or `find_elements` on standard tags (like `img`). If you have a good step budget, take your time to find the exact elements.
        6. Look at the top 3 most recent posts on their grid. Try to extract the caption/text of those posts. If the account is private, or has no posts, set top_posts to an empty list [].
        
        OUTPUT FORMAT:
        You must output ONLY a raw, valid JSON object and absolutely nothing else. No markdown blocks, no conversational text. Ensure all quotes and newlines in text are properly escaped.
        {{
            "profile_status": "found or no profile found",
            "profile_url": "{target_url}",
            "bio": "full extracted text with escaped newlines or null",
            "avatar_url": "full perfect image url or null",
            "top_posts": ["post 1 text", "post 2 text", "post 3 text"]
        }}
        """

        try:
            # Step 5: Start the Agent and let it browse the page.
            # We limit it to AGENT_MAX_STEPS actions, but explicitly forbid Javascript loops.
            agent = Agent(task=mission, llm=llm, browser=browser)
            history = await agent.run(max_steps=Config.AGENT_MAX_STEPS)
            
            # Step 6: Get the text output from the agent's history.
            text = ""
            if hasattr(history, 'final_result') and history.final_result():
                text = history.final_result()
            elif hasattr(history, 'all_results') and len(history.all_results) > 0:
                text = getattr(history.all_results[-1], 'extracted_content', str(history))
            else:
                text = str(history)

            # Step 7: Find the JSON dictionary inside the agent's output using a regular expression.
            try:
                m = re.search(r"\{.*?\}", text, re.S)
                if m:
                    # Convert the text into a real Python dictionary. Allow unescaped newlines.
                    payload = json.loads(m.group(0), strict=False)
                    
                    profile_status = payload.get("profile_status")
                    if profile_status == "no profile found":
                        return {
                            "bio": "no profile available with this username",
                            "avatar_url": None,
                            "profile_url": target_url,
                            "top_posts": []
                        }
                    
                    # Return the organized data.
                    return {
                        "bio": payload.get("bio") if payload.get("bio") != "null" else None, 
                        "avatar_url": payload.get("avatar_url") if payload.get("avatar_url") != "null" else None,
                        "profile_url": payload.get("profile_url", target_url),
                        "top_posts": payload.get("top_posts", [])
                    }
            except Exception as json_err:
                # Log a warning if the AI didn't give us valid JSON.
                logger.warning(f"Failed to parse JSON from Instagram AI output: {json_err}")
                pass

            # If we couldn't parse it, return empty fields instead of crashing.
            return {"bio": "no profile available with this username", "avatar_url": None, "profile_url": target_url, "top_posts": []}
            
        except Exception as e:
            # If the entire process crashes, log the error.
            logger.error(f"Failed to analyze Instagram profile {target_username}: {str(e)}")
            return {"bio": "no profile available with this username", "avatar_url": None, "profile_url": target_url, "top_posts": []}
            
        finally:
            # Step 8: Always close the Chrome browser to free up computer memory.
            await browser.close()

    def execute(self, target_username: str) -> dict:
        """
        THE BRIDGE (Synchronous):
        This function bridges the synchronous dispatcher code to our asynchronous browser engine.
        It runs the async scraping engine inside a mini event loop.
        """
        # Log that we are starting the background worker.
        logger.info(f"Spawning background thread worker for Instagram Username: {target_username}")

        try:
            # Start the event loop and wait for the result to come back.
            result = asyncio.run(self._scrape_instagram_async(target_username))
            return result
            
        except Exception as e:
            # Catch any major thread errors.
            logger.error(f"Instagram Agent Thread Error: {str(e)}")
            return {"bio": None, "avatar_url": None, "top_posts": []}