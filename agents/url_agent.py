"""
URL Specialist AI Agent Module.

This file contains an artificial intelligence "Agent" that acts like a human.
Given a specific URL, it can physically open a Chrome web browser, look at the page,
and read the text on the screen to find what we are looking for (like a bio or a picture).
"""

import asyncio
import os
import json
import re

# We import tools from 'browser_use' which allow our AI to control a real web browser.
from browser_use import Agent, Browser, BrowserProfile

# We import the Langchain connector to give our agent an OpenAI GPT brain!
from browser_use.llm import ChatOpenAI

# We import our custom logger to print updates to the terminal screen.
from utils.logger import get_logger

# Import our configuration settings
from config import Config

# Initialize the logging tool so we can print status messages for this file.
logger = get_logger(__name__)


def _truncate_prompt(mission: str) -> str:
    """Truncate long mission prompts to avoid model context-window rejections.

    Keeps a head and tail of the original prompt and inserts a clear marker where the
    middle was removed. The limit is controlled by `Config.LLM_MAX_PROMPT_CHARS`.
    """
    max_chars = getattr(Config, "LLM_MAX_PROMPT_CHARS", 2000)
    if not mission:
        return mission

    # Collapse long whitespace to reduce token overhead.
    mission = re.sub(r"\s+", " ", mission).strip()
    if len(mission) <= max_chars:
        return mission

    # Keep a head and tail to preserve instruction intent, insert explicit truncation marker.
    head_len = int(max_chars * 0.25)
    tail_len = int(max_chars * 0.65)
    head = mission[:head_len]
    tail = mission[-tail_len:]
    return head + "\n\n...PROMPT_TRUNCATED...\n\n" + tail

# 🛠️ THE ARCHITECTURE FIX: 
# The browser-use library expects a "provider" property (like saying "I am using OpenAI").
# LangChain doesn't have it by default.
# We create a custom subclass that strictly injects this missing property to stop the program from crashing!
class PatchedChatOpenAI(ChatOpenAI):
    @property
    def provider(self):
        """Tells the browser tool that our AI provider is OpenAI."""
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

class UrlAgent:
    """
    A standalone tool designed to analyze individual profile webpages.
    It operates completely in its own isolated environment (sandbox) so if it breaks, 
    it won't crash the main application.
    """

    def __init__(self):
        """
        When we turn on the UrlAgent, we reach into our secure vault (.env file) 
        and grab the OpenAI API Key, which acts as the 'battery' for our AI brain.
        """
        self.api_key = os.getenv("OPENAI_API_KEY")

    async def _scrape_url_async(self, target_url: str) -> dict:
        """
        THE ENGINE (Asynchronous):
        This is the actual internal mechanism that controls the mouse and keyboard.
        It runs "asynchronously" meaning it can do multiple things without freezing our server.
        """
        # Safety Check: If using OpenAI backend ensure API key exists.
        if Config.LLM_BACKEND == "openai" and not self.api_key:
            return {"bio": None, "avatar_url": None, "error": "OPENAI_API_KEY is missing from your .env file."}

        # Log that we are about to start looking at a specific webpage.
        logger.info(f"Targeting profile link with AI Agent: {target_url}")
        
        # Step 1: Initialize the AI brain. Support either OpenAI or local Ollama (Qwen).
        if Config.LLM_BACKEND == "ollama":
            from browser_use import ChatOllama
            llm = ChatOllama(model=Config.QWEN_MODEL, host=Config.OLLAMA_HOST)
        else:
            # Default to OpenAI-compatible wrapper
            llm = PatchedChatOpenAI(model=Config.OPENAI_MODEL, api_key=self.api_key)
        
        # Step 2: Configure and turn on your personal Chrome browser.
        # We tell it exactly where Chrome is installed on the computer.
        profile = BrowserProfile(
            # Standard path for Chrome on Windows
            executable_path=Config.CHROME_EXECUTABLE_PATH,
            
            # Point to the main User Data folder where Chrome keeps all its cookies and settings.
            user_data_dir=Config.CHROME_USER_DATA_DIR,
            
            # Tell it WHICH specific profile inside that folder to use.
            profile_directory=Config.CHROME_PROFILE_DIRECTORY
        )
        # Create the actual browser object using the settings above.
        browser = Browser(browser_profile=profile)

        # Step 3: Write out a clear list of instructions (a mission) for the AI in plain English.
        mission = f"""
        Navigate to this exact URL: {target_url}

        You are an automated OSINT data extractor. Your ONLY goal is to extract the full profile bio, the perfect profile picture URL, and the profile URL itself.
        
        STRICT EXECUTION RULES:
        1. Wait 3 seconds for the page to fully load.
        2. Look for the user's bio/description text. You must extract the FULL bio, capturing every single word and newline. Ensure newlines are escaped properly as \\n in the JSON output.
        3. Look for the user's profile picture image URL. DO NOT TRUNCATE URLs. When extracting the avatar_url, you must output the full, exact, completely unedited URL so it can be opened directly. Never use ellipses (...) or summarize the link.
        4. If the page is a login wall, broken, "User not found", or there is clearly no profile, immediately stop and set "profile_status" to "no profile found".
        5. DO NOT get confused by advanced JavaScript DOM. Do not use complex javascript to bypass shadow DOMs. Rely strictly on simple native tools like `extract` or `find_elements` on standard tags (like `img`). If you have a good step budget, take your time to find the exact elements.
        
        OUTPUT FORMAT:
        You must output ONLY a raw, valid JSON object and absolutely nothing else. No markdown blocks, no conversational text. Ensure all quotes and newlines in text are properly escaped.
        {{
            "profile_status": "found or no profile found",
            "profile_url": "{target_url}",
            "bio": "full extracted text with escaped newlines or null",
            "avatar_url": "full perfect image url or null"
        }}
        """

        try:
            # Step 4: Create the Agent. Truncate mission if it's too long for the configured LLM.
            mission = _truncate_prompt(mission)

            # Configure a lightweight fallback LLM (Gemma 3) to use if the primary model rejects.
            fallback_llm = None
            if Config.LLM_BACKEND == "ollama":
                try:
                    from browser_use import ChatOllama
                    # Use Gemma 3 as fallback for lightweight error recovery
                    fallback_llm = ChatOllama(model=Config.QWEN_FALLBACK_MODEL, host=Config.OLLAMA_HOST)
                except Exception:
                    fallback_llm = None
            else:
                # Use OpenAI wrapper as a fallback when Ollama is not the primary backend.
                fallback_llm = PatchedChatOpenAI(model=Config.OPENAI_MODEL, api_key=self.api_key)

            # Enable vision/multimodal so the LLM can process screenshots and page content.
            # Fallback LLM provides recovery if primary model rejects requests.
            # NOTE: Gemma 3 has only 4KB context window, so vision is disabled to fit prompts.
            agent = Agent(task=mission, llm=llm, browser=browser, fallback_llm=fallback_llm, use_vision=False)

            # Step 5: Tell the agent to hit 'Go' and wait for it to finish browsing.
            # We set max_steps to AGENT_MAX_STEPS as configured, but guard against overthinking via the prompt.
            history = await agent.run(max_steps=Config.AGENT_MAX_STEPS)
            
            # Now we extract the final text output that the AI produced.
            text = ""
            
            # Different versions of the library return results in different formats, so we check a few places.
            if hasattr(history, 'final_result') and history.final_result():
                text = history.final_result()
            elif hasattr(history, 'all_results') and len(history.all_results) > 0:
                text = getattr(history.all_results[-1], 'extracted_content', str(history))
            else:
                text = str(history)

            # Step 6: Try to find a JSON dictionary { ... } hidden inside the text output using a regular expression.
            try:
                # The regex looks for anything that starts with { and ends with }
                m = re.search(r"\{.*?\}", text, re.S)
                if m:
                    # If we found it, convert the text into a real Python dictionary. Allow unescaped newlines.
                    payload = json.loads(m.group(0), strict=False)
                    
                    profile_status = payload.get("profile_status")
                    if profile_status == "no profile found":
                        return {
                            "bio": "no profile available at this URL",
                            "avatar_url": None,
                            "profile_url": target_url
                        }
                    
                    # Return the clean dictionary. We convert the word "null" into an actual Python None.
                    return {
                        "bio": payload.get("bio") if payload.get("bio") != "null" else None, 
                        "avatar_url": payload.get("avatar_url") if payload.get("avatar_url") != "null" else None,
                        "profile_url": payload.get("profile_url", target_url)
                    }
            except Exception as json_err:
                # If we couldn't parse the JSON, we log a warning.
                logger.warning(f"Failed to parse JSON from AI output: {json_err}")
                pass

            # Best-effort fallback: if it didn't return JSON, we return empty data so we don't crash.
            return {"bio": "no profile available at this URL", "avatar_url": None, "profile_url": target_url}
            
        except Exception as e:
            # Error Handling: If the AI crashes completely, we catch the error safely here.
            logger.error(f"Failed to analyze URL {target_url}: {str(e)}")
            return {"bio": "no profile available at this URL", "avatar_url": None, "profile_url": target_url}
            
        finally:
            # Crucial Cleanup: ALWAYS close the Chrome window when we are done, 
            # otherwise we will have 100 invisible Chrome windows open and the computer will freeze.
            await browser.close()

    def execute(self, target_url: str) -> dict:
        """
        THE BRIDGE (Synchronous):
        Because our server is synchronous (handles one thing at a time), but our browser tool
        is asynchronous (handles many things), we need a bridge. 
        This function creates a mini timeline just for the browser, runs it, and waits for it to finish.
        """
        # Log that we are launching a background worker just for this URL.
        logger.info(f"Spawning background thread worker for URL: {target_url}")

        try:
            # Use asyncio.run to create the mini-timeline (event loop) and run our scraping engine.
            result = asyncio.run(self._scrape_url_async(target_url))
            return result
            
        except Exception as e:
            # Catch any extreme errors that happen on the bridge itself.
            logger.error(f"URL Agent Thread Error: {str(e)}")
            return {"bio": None, "avatar_url": None}