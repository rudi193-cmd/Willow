import os
import shutil
import time
import sqlite3
import hashlib
import re
from datetime import datetime

# --- PIP INSTALL REQUIREMENTS ---
# pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib google-api-core

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# --- CONFIGURATION ---
ATMOSPHERE_PATH = r"G:\My Drive\Willow\Auth Users\Sweet-Pea-Rudi19\Drop"
EARTH_PATH = r"C:\Users\Sean\Documents\GitHub\willow"
ROOTS_PATH = os.path.join(EARTH_PATH, "artifacts", "pending")
DB_PATH = os.path.join(EARTH_PATH, "willow_index.db")

# SCOPES: Read Drive files
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# GHOSTS: Files that need transmutation
GHOST_EXTENSIONS = {'.gdoc', '.gsheet', '.gslides'}

def init_nervous_system():
    """Initializes SQLite to track files."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS file_registry 
                      (file_hash TEXT PRIMARY KEY, filename TEXT, ingest_date TEXT, category TEXT, status TEXT)''')
    conn.commit()
    conn.close()
    print("Nervous System (SQLite) active.")

def get_drive_service():
    """Authenticates using credentials.json."""
    creds = None
    token_path = os.path.join(EARTH_PATH, 'token.json')
    creds_path = os.path.join(EARTH_PATH, 'credentials.json')

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(creds_path):
                print("CRITICAL: credentials.json not found.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
            
    return build('drive', 'v3', credentials=creds)

def sanitize_filename(name):
    """Removes illegal characters from filenames (e.g. : ? < > |)."""
    return re.sub(r'[<>:"/\\|?*]', '', name)

def transmute_ghost(file_path, service):
    """
    Finds the file ID via API (Remote Targeting) and exports as PDF.
    Bypasses local read errors.
    """
    filename_with_ext = os.path.basename(file_path)
    filename_no_ext = os.path.splitext(filename_with_ext)[0]
    
    try:
        # 1. Remote Target: Ask API for the ID based on the name
        # We search for the name and ensure it's not in the trash.
        query = f"name = '{filename_no_ext}' and trashed = false"
        results = service.files().list(q=query, pageSize=1, fields="files(id, name)").execute()
        items = results.get('files', [])

        if not items:
            print(f"Skipping {filename_with_ext}: Cloud Original not found via API.")
            return False
        
        file_id = items[0]['id']

        # 2. Export (PDF)
        request = service.files().export_media(fileId=file_id, mimeType='application/pdf')
        
        # 3. Sanitize and Save
        safe_name = sanitize_filename(filename_no_ext) + ".pdf"
        
        # Ensure destination exists
        os.makedirs(ROOTS_PATH, exist_ok=True)
        destination = os.path.join(ROOTS_PATH, safe_name)
        
        with open(destination, 'wb') as fh:
            fh.write(request.execute())
            
        print(f"Transmuted: {filename_with_ext} -> {safe_name}")
        return True

    except Exception as e:
        # Catch errors but keep running
        print(f"Transmutation Error ({filename_with_ext}): {e}")
        return False

def calculate_iron_content(filepath):
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            buf = f.read()
            hasher.update(buf)
        return hasher.hexdigest()
    except: return None

def process_drop():
    if not os.path.exists(ATMOSPHERE_PATH):
        print("Waiting for G: Drive...")
        return
    
    drive_service = None 

    for root_dir, _, files in os.walk(ATMOSPHERE_PATH):
        for file in files:
            file_path = os.path.join(root_dir, file)
            _, ext = os.path.splitext(file)
            
            # CASE 1: GHOSTS
            if ext.lower() in GHOST_EXTENSIONS:
                if drive_service is None:
                    print("Ghost detected. Spinning up Transmuter Engine...")
                    drive_service = get_drive_service()
                
                # Try to transmute
                if drive_service and transmute_ghost(file_path, drive_service):
                    try:
                        os.remove(file_path) # Delete ghost after success
                    except: pass
                continue

            # CASE 2: IRON (Regular Files)
            file_hash = calculate_iron_content(file_path)
            if not file_hash: continue

            destination = os.path.join(ROOTS_PATH, file)
            try:
                os.makedirs(ROOTS_PATH, exist_ok=True)
                shutil.copy2(file_path, destination)
                os.remove(file_path)
                print(f"Harvested Iron: {file} -> Roots")
            except Exception as e:
                print(f"Error moving {file}: {e}")

if __name__ == "__main__":
    print("Initializing Willow [Sovereign Build]...")
    init_nervous_system()
    
    while True:
        try:
            process_drop()
        except Exception as e:
            print(f"Global Error: {e}")
        time.sleep(10)