"""
Configuration Module.
This file is responsible for safely loading secret settings (like API keys and passwords).
It reads these secrets from a hidden file (usually named .env) so that they aren't 
hardcoded directly into the code where anyone could steal them.
"""

import os
from dotenv import load_dotenv

# This command actually searches your computer for a file named '.env' and loads its contents into memory.
load_dotenv()

class Config:
    """
    The Config class holds all our application settings in one place.
    Any part of the application can look at this class to find out what the current settings are.
    """

    # We fetch the API key needed for the Numverify service, which checks phone numbers.
    # We use os.getenv to grab it safely from memory. If it's missing, we just use a blank string "".
    NUMVERIFY_API_KEY: str = os.getenv("NUMVERIFY_API_KEY", "")
    
    # We check if the application should run in "DEBUG" mode, which might print out extra helpful logs.
    # We grab the word "True" or "False", convert it to lowercase, and check if it equals "true".
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    # AI Config
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    # Which LLM backend to use: 'openai' or 'ollama'
    LLM_BACKEND: str = os.getenv("LLM_BACKEND", "openai")
    # If using Ollama locally, the model name (e.g. qwen-3) and host
    QWEN_MODEL: str = os.getenv("QWEN_MODEL", "qwen-3")
    QWEN_FALLBACK_MODEL: str = os.getenv("QWEN_FALLBACK_MODEL", "gemma3:latest")
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    
    # Chrome Profile Configurations
    CHROME_EXECUTABLE_PATH: str = os.getenv("CHROME_EXECUTABLE_PATH", r"C:\Users\aadit\AppData\Local\Google\Chrome\Application\chrome.exe")
    CHROME_USER_DATA_DIR: str = os.getenv("CHROME_USER_DATA_DIR", r"C:\Users\aadit\AppData\Local\Google\Chrome\User Data")
    CHROME_PROFILE_DIRECTORY: str = os.getenv("CHROME_PROFILE_DIRECTORY", "Profile 12")

    # System Limits and Timeouts
    WEBHOOK_TIMEOUT: int = int(os.getenv("WEBHOOK_TIMEOUT", "15"))
    SHERLOCK_TIMEOUT: str = os.getenv("SHERLOCK_TIMEOUT", "5")
    AGENT_MAX_STEPS: int = int(os.getenv("AGENT_MAX_STEPS", "15"))
    # Maximum prompt length (characters) to send to local LLMs. Truncate longer prompts to avoid
    # context-window rejections from models with smaller context sizes.
    # Mistral has 8K context window, so we can use a moderate limit of 2000 chars.
    LLM_MAX_PROMPT_CHARS: int = int(os.getenv("LLM_MAX_PROMPT_CHARS", "2000"))