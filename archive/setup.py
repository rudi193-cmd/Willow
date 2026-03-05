"""
Willow Setup — Zero-cost onboarding.
Run: python setup.py
"""
import os
import subprocess
import sqlite3

EARTH_PATH = os.path.dirname(os.path.abspath(__file__))
ARTIFACTS_PATH = os.path.join(EARTH_PATH, "artifacts")
FOLDERS = ["pending", "documents", "photos", "screenshots", "reddit", "Unsorted"]
DB_PATH = os.path.join(EARTH_PATH, "willow_index.db")

def create_folders():
    for folder in FOLDERS:
        os.makedirs(os.path.join(ARTIFACTS_PATH, folder), exist_ok=True)
    print(f"[OK] Artifact folders ready: {', '.join(FOLDERS)}")

def init_master_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS file_registry
        (file_hash TEXT PRIMARY KEY, filename TEXT, ingest_date TEXT, category TEXT, status TEXT)""")
    conn.commit()
    conn.close()
    print(f"[OK] Master DB: {DB_PATH}")

def install_deps():
    deps = ["google-api-python-client", "google-auth-httplib2", "google-auth-oauthlib", "requests"]
    subprocess.run(["pip", "install", "--quiet"] + deps, check=True)
    print("[OK] Python dependencies installed.")

def pull_ollama_model():
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            if "moondream" not in result.stdout:
                print("[*] Pulling moondream vision model (1.7GB)...")
                subprocess.run(["ollama", "pull", "moondream"], check=True)
            else:
                print("[OK] moondream already installed.")
            if "llama3.2" not in result.stdout:
                print("[*] Pulling llama3.2 text model...")
                subprocess.run(["ollama", "pull", "llama3.2"], check=True)
            else:
                print("[OK] llama3.2 already installed.")
        else:
            print("[!] Ollama not running. Start it and re-run setup.")
    except FileNotFoundError:
        print("[!] Ollama not installed. Visit https://ollama.ai to install (free, local).")
    except Exception as e:
        print(f"[!] Ollama check failed: {e}")

if __name__ == "__main__":
    print("--- Willow Setup ---")
    create_folders()
    init_master_db()
    install_deps()
    pull_ollama_model()
    print("\n[DONE] Willow ready. Run: python aios_loop.py")
