"""
FastAPI Server Backend Module.

This file runs the actual server that listens for requests (either from our Streamlit
dashboard or from a real production frontend). It is the central nervous system 
of the backend API.

It handles two main workflows:
1. POLLING: A client asks it to start a job, and then keeps asking "are you done yet?".
2. WEBHOOKS: A client asks it to start a job, gives it a URL, and says "send the data here when you finish".
"""

import os
import uuid
import requests
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, BackgroundTasks, Security, HTTPException, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from dotenv import load_dotenv

from main import OSINTFramework
from utils.logger import get_logger
from config import Config

# Initialize our central logger so we can record server activities to the console.
logger = get_logger(__name__)

# Load secret environment variables (like our API keys) from the hidden .env file.
load_dotenv()

# We create the main FastAPI application object. 
# We give it a title and description which will show up in the auto-generated documentation.
app = FastAPI(
    title="OSINT Recon API",
    description="Headless backend API for automated OSINT profile extraction.",
    version="1.0.0"
)

# -------------------------------------------------------------------
# SECURITY: API KEY VALIDATION
# -------------------------------------------------------------------
# This section ensures that random people on the internet cannot use our API for free.
# They must provide a secret key in the 'X-API-Key' header of their request.

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def get_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    This function checks if the provided API Key matches the secret INTERNAL_API_KEY.
    If it does not match, or is missing, it immediately blocks the request and throws an error.
    """
    # Fetch the expected secret key from our environment variables.
    expected_key = os.getenv("INTERNAL_API_KEY", "default-dev-key")
    
    # If they didn't provide a key, or it's the wrong one, we reject them.
    if not api_key or api_key != expected_key:
        logger.warning("Failed API authentication attempt. An invalid key was provided.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate API key. Ensure X-API-Key header is present and valid."
        )
        
    return api_key

# -------------------------------------------------------------------
# MEMORY & DATA MODELS
# -------------------------------------------------------------------
# We use this simple dictionary as a temporary database to track the status of jobs.
# In a real massive production system, this would be a database like Redis or PostgreSQL.
job_store: Dict[str, Dict[str, Any]] = {}

class ScanRequest(BaseModel):
    """
    This class defines the exact shape of the JSON data we expect the client to send us.
    If they send data that doesn't match this shape, FastAPI will automatically reject it.
    """
    job_id: str
    targets: List[str]
    callback_url: Optional[str] = None

# -------------------------------------------------------------------
# BACKGROUND WORKER PROCESS
# -------------------------------------------------------------------

def cleanup_job_files(result_data: dict):
    """
    This function is responsible for deleting the downloaded profile pictures (avatars)
    after we have successfully sent them to the client. This ensures we don't 
    clutter our server's hard drive and maintains a "zero footprint" policy for images.
    """
    paths_to_delete = []
    
    # First, we look through all the URL Agent results to find any saved avatar paths.
    for match in result_data.get("all_matches", []):
        enriched = match.get("enriched_data", {})
        if "local_avatar_path" in enriched and enriched["local_avatar_path"]:
            paths_to_delete.append(enriched["local_avatar_path"])
            
    # Second, we look through all the Instagram Agent results to find any saved avatar paths.
    for insta in result_data.get("instagram_results", []):
        extracted = insta.get("extracted_data", {})
        if "local_avatar_path" in extracted and extracted["local_avatar_path"]:
            paths_to_delete.append(extracted["local_avatar_path"])
            
    # Finally, we go through the list of paths we found and delete the actual files from the computer.
    # We use 'set' to remove any duplicates so we don't try to delete the same file twice.
    for file_path in set(paths_to_delete):
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Zero-Footprint Cleanup: Erased {file_path}")
        except Exception as e:
            logger.error(f"Cleanup failed for {file_path}: {e}")

def run_background_scan(job_id: str, targets: List[str], callback_url: Optional[str] = None):
    """
    This function handles the actual heavy lifting of scraping.
    It runs in the background so that our API server doesn't freeze up while waiting 
    for the slow OSINT agents to finish.
    """
    try:
        logger.info(f"[JOB {job_id}] Starting background OSINT scan for targets: {targets}")
        
        # We start up the main OSINT Framework engine.
        engine = OSINTFramework()
        
        # We tell the engine to run the scan and we wait for the massive dictionary of results.
        result_data = engine.run_scan(targets)
        
        # Once the scan is done, we save the results into our temporary memory dictionary.
        # This allows the Streamlit dashboard to pull the data using the /status endpoint.
        job_store[job_id]["status"] = "completed"
        job_store[job_id]["data"] = result_data
        logger.info(f"[JOB {job_id}] Successfully completed local scraping.")
        
        # For debugging purposes, we also save the final JSON data to a text file.
        # This lets us inspect exactly what the payload looks like.
        import json
        debug_filename = f"final_api_payload_{job_id}.json"
        try:
            with open(debug_filename, "w", encoding="utf-8") as f:
                json.dump(result_data, f, indent=4)
            logger.info(f"💾 Saved final API payload to {debug_filename} for review.")
        except Exception as e:
            logger.error(f"Failed to save debug JSON: {e}")

        # Webhook Architecture
        # If the client provided a callback URL, it means they want us to actively push the data to them.
        if callback_url:
            logger.info(f"[JOB {job_id}] Webhook URL detected! Attempting to push data to {callback_url}")
            try:
                # We wrap the results into a clean JSON package.
                payload = {
                    "job_id": job_id,
                    "status": "completed",
                    "results": result_data
                }
                
                # We send the package to the client's server via a POST request.
                webhook_response = requests.post(callback_url, json=payload, timeout=Config.WEBHOOK_TIMEOUT)
                
                # If their server replies with a success code (like 200 OK), we know they received it.
                if webhook_response.status_code in (200, 201, 202):
                    logger.info(f"[JOB {job_id}] Webhook successfully delivered to {callback_url}.")
                    
                    # Since they received the data, we no longer need the local image files, so we delete them.
                    cleanup_job_files(result_data)
                else:
                    logger.warning(f"[JOB {job_id}] Webhook failed! Remote server returned status code: {webhook_response.status_code}")
                    
            except Exception as webhook_err:
                # If we couldn't connect to their server at all, we log the error but don't crash our own system.
                logger.error(f"[JOB {job_id}] Critical failure while sending Webhook: {str(webhook_err)}")

    except Exception as e:
        # If the actual OSINT scraping process crashes internally, we catch the error gracefully.
        logger.error(f"[JOB {job_id}] Fatal background crash during execution: {str(e)}")
        
        # We update the job status in memory so the polling client knows it failed.
        job_store[job_id]["status"] = "error"
        job_store[job_id]["error_message"] = str(e)


# -------------------------------------------------------------------
# API ENDPOINTS
# -------------------------------------------------------------------

@app.post("/api/v1/scan", summary="Start a new OSINT Scan")
async def start_scan(request: ScanRequest, background_tasks: BackgroundTasks, api_key: str = Security(get_api_key)):
    """
    This endpoint is used to trigger a new OSINT scan operation.
    
    Because scans can take several minutes, this endpoint DOES NOT wait for the scan to finish.
    Instead, it throws the work into a background queue and immediately responds with "processing".
    """
    # We grab the job ID provided by the client's request.
    job_id = request.job_id
    
    # We save an initial placeholder record in our memory database saying the job has started.
    job_store[job_id] = {
        "status": "processing",
        "targets": request.targets,
        "data": None
    }
    
    # We hand the heavy lifting off to FastAPI's background task manager.
    background_tasks.add_task(run_background_scan, job_id, request.targets, request.callback_url)
    
    # We instantly reply to the client so their HTTP request doesn't time out.
    return {"job_id": job_id, "status": "processing", "message": "Task queued successfully."}


@app.get("/api/v1/status/{job_id}", summary="Check Scan Status")
async def check_status(job_id: str, api_key: str = Security(get_api_key)):
    """
    This endpoint is used by clients who are polling. They will call this URL 
    every few seconds to check if their specific job_id is finished yet.
    """
    # First, we check if we even know about this job ID.
    if job_id not in job_store:
        # If we don't, we throw a 404 Not Found error.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Job ID {job_id} could not be found in the system memory."
        )
        
    # If we do know about it, we return the current status (and the data, if it's finished).
    return job_store[job_id]
