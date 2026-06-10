"""
Streamlit Client Dashboard Module.

This file creates a user interface (a webpage) using Streamlit.
It allows us to easily test our backend API by typing in targets and seeing the results.
It does NOT run the heavy scraping operations itself. Instead, it sends a request
to our FastAPI server (api.py) to do the work, and then waits for the answer.
"""

import streamlit as st
import requests
import os
import time
from dotenv import load_dotenv
import uuid

# Load our secret environment variables (like API keys) into memory.
load_dotenv()

# ==========================================
# 1. PAGE CONFIGURATION
# ==========================================
# Here we set up how our webpage looks. We give it a title, a magnifying glass icon,
# and tell it to use the full width of the screen.
st.set_page_config(
    page_title="OSINT API Testing Dashboard",
    page_icon="🔍",
    layout="wide"
)

# API Configuration
# This is the address of our FastAPI backend server running on our own computer.
API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000/api/v1")

# We fetch the secret internal API key to prove to the backend that we are allowed to use it.
API_KEY = os.getenv("INTERNAL_API_KEY", "default-dev-key")

# We prepare the "headers" which are like a secret envelope containing our API key 
# that gets sent with every request to the backend.
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

# ==========================================
# 2. DASHBOARD UI HEADER
# ==========================================
# We draw the main title on the screen.
st.title("🔍 OSINT API Client Dashboard")

# We add a small subtitle explaining what this page is for.
st.markdown("Visual testing rig for the Hybrid FastAPI Backend.")

# We draw a horizontal line across the screen to separate sections.
st.write("---")

# ==========================================
# 3. TEXT TARGET SCANNER
# ==========================================
# Create a sub-heading for the input section.
st.subheader("Start API Scan")

# Create a text input box where the user can type in the emails, phones, or usernames they want to search for.
user_input = st.text_input(
    "Target Input Strings (Comma separated):", 
    placeholder="e.g., testuser, target@email.com, 7742736948"
)

# Create a big button that says "Launch API Request". 
# The code inside the 'if' block only runs when the user clicks this button.
if st.button("Launch API Request", type="primary"):
    
    # First, check if the user actually typed something. If they left it blank, show a warning.
    if not user_input.strip():
        st.warning("Please enter at least one target.")
        
    else:
        # We take the user's input, which might be separated by commas, and split it into a proper list.
        # We also remove any extra spaces around each target.
        targets = [t.strip() for t in user_input.split(",") if t.strip()]
        
        # Phase 1: Fire the Web Request to FastAPI
        # We create a dictionary (payload) containing our list of targets and a job_id.
        job_id = str(uuid.uuid4())
        payload = {"job_id": job_id, "targets": targets}
        
        try:
            # We show a spinning wheel on the screen to let the user know we are connecting.
            with st.spinner("Connecting to FastAPI Server..."):
                
                # We send the POST request to our backend server, asking it to start the scan.
                response = requests.post(f"{API_URL}/scan", json=payload, headers=HEADERS)
                
                # If the server returned an error (like a 404 or 500), this will raise an exception.
                response.raise_for_status()
                
                # We read the JSON response from the server to get our unique Job ID.
                data = response.json()
                job_id = data.get("job_id")
                
            # We show a green success message to confirm the job was queued.
            st.success(f"Successfully queued job on Backend! Job ID: {job_id}")
            
            # Phase 2: The Polling Loop
            # We create an empty container on the screen where we will show status updates.
            status_container = st.empty()
            
            # We create a progress bar starting at 0%.
            progress_bar = st.progress(0)
            
            # We use these variables to track when the job is done and store the final results.
            job_completed = False
            final_data = None
            
            # We start a loop that will keep running until the job is completed.
            while not job_completed:
                
                # We pause for 3 seconds so we don't spam the server with too many requests.
                time.sleep(3) 
                
                try:
                    # We ask the server for an update on our specific Job ID.
                    poll_resp = requests.get(f"{API_URL}/status/{job_id}", headers=HEADERS)
                    poll_resp.raise_for_status()
                    poll_data = poll_resp.json()
                    
                    # We check the status field in the server's response.
                    status = poll_data.get("status")
                    
                    if status == "processing":
                        # If it's still running, we update our message on the screen.
                        status_container.info("⏳ Backend is running OSINT framework (Sherlock/Browser-Use)... Polling again in 3s")
                        
                    elif status == "completed":
                        # If it finished, we show a success message, fill the progress bar, and grab the final data.
                        status_container.success("✅ Backend completed the scraping process!")
                        progress_bar.progress(100)
                        final_data = poll_data.get("data")
                        
                        # We change this to True to break out of the while loop.
                        job_completed = True
                        
                    elif status == "error":
                        # If the backend crashed, we show an error message and stop polling.
                        status_container.error(f"❌ Backend encountered a fatal error: {poll_data.get('error_message')}")
                        job_completed = True
                        
                except Exception as poll_err:
                    # If we lost connection to the server while polling, we show an error and stop.
                    status_container.error(f"Lost connection to API during polling: {poll_err}")
                    job_completed = True
            
            # Phase 3: Display Results
            # If we successfully got the final data back from the server, we display it.
            if final_data:
                
                # Draw a separator line.
                st.write("---")
                
                # Show the raw JSON data that the API returned. This is useful for developers to see.
                st.subheader("📊 Final API JSON Payload")
                st.json(final_data)
                
                # Create a section to show the nicely formatted enriched profiles.
                st.subheader("🧠 Enriched Profiles")
                
                # Go through every profile that the backend found.
                for match in final_data.get("all_matches", []):
                    
                    # We check if the backend managed to grab extra "enriched" data (like bio or avatar).
                    enriched = match.get("enriched_data", {})
                    
                    if enriched:
                        # Create a nice boxed container for each profile.
                        with st.container(border=True):
                            
                            # Print the platform name and the URL of the profile.
                            st.markdown(f"**Platform:** {match.get('platform', 'Unknown')}")
                            st.markdown(f"**URL:** {match.get('url')}")
                            
                            # We split the box into two columns. 1 part for the image, 3 parts for text.
                            col1, col2 = st.columns([1, 3])
                            
                            # In the first column, we try to display the profile picture.
                            with col1:
                                avatar = enriched.get("local_avatar_path")
                                
                                # We make sure the file actually exists on our computer before trying to show it.
                                if avatar and os.path.exists(avatar):
                                    st.image(avatar, width=140)
                                else:
                                    st.caption("No Profile Image")
                                    
                            # In the second column, we display the user's bio.
                            with col2:
                                st.write("**Extracted Bio:**")
                                st.write(enriched.get("bio", "None"))
                                
        except Exception as e:
            # If the initial connection to the FastAPI server failed entirely, we show this error.
            st.error(f"Failed to connect to FastAPI Backend. Is it running? Error: {e}")
