"""
Small CSV helper utilities Module.

This file provides a single, organized place to manage saving data into an Excel-like CSV file.
Having this central helper means that even if multiple different parts of the program
are running at the same time, they won't mess up the formatting of the spreadsheet.
"""
import csv
import os
from typing import Optional

def append_master_row(target_url: str, bio: str, avatar_url: Optional[str] = None, avatar_path: Optional[str] = None, csv_path: str = "master_extracted_data.csv") -> None:
    """
    Append a row of data to the master CSV spreadsheet.
    If the file doesn't exist yet, it will automatically create it and write the column headers at the top.

    Columns created: target_url, bio, avatar_url, avatar_path
    """
    
    # Check if the file is missing or completely empty. If it is, we need to write the headers.
    first_write = not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0
    
    try:
        # Get the name of the folder where we want to save this file.
        parent = os.path.dirname(csv_path)
        
        # If there is a parent folder, and it doesn't actually exist on the computer yet...
        if parent and not os.path.exists(parent):
            # ...then create the folder automatically.
            os.makedirs(parent, exist_ok=True)

        # Open the CSV file in "append" mode ("a"), which adds to the bottom without erasing the top.
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            
            # Create a tool that helps us write properly formatted CSV rows.
            writer = csv.writer(f)
            
            # If this is our very first time writing to this file, create the column titles at the top.
            if first_write:
                writer.writerow(["target_url", "bio", "avatar_url", "avatar_path"])
                
            # Write the actual data row. If any optional data is missing, we just write a blank space ("").
            writer.writerow([target_url, bio, avatar_url or "", avatar_path or ""])
            
    except Exception:
        # If saving fails (e.g., the hard drive is full), we just throw the error back to whoever called us
        # so they can handle logging it. We keep this file simple.
        raise
