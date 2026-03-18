import os
import sys
import glob
import time

# --- ANCHOR: Force Project Root ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

from core import loam

def is_text_file(filename):
    """Filter for persona/content files."""
    valid_exts = {'.md', '.txt', '.json', '.yaml', '.yml'}
    return os.path.splitext(filename)[1].lower() in valid_exts

def omni_restore():
    print(f"--- OMNI-RESTORE: Scanning {project_root} ---")
    
    # 1. Initialize DB (Schema-Aware Check)
    print("Verifying Database Schema...")
    loam.init_db("Sean")
    
    restored_count = 0
    
    # 2. Recursive Walk from Project Root
    for root, dirs, files in os.walk(project_root):
        # Skip technical folders
        if ".git" in root or "__pycache__" in root or "artifacts" in root:
            continue
            
        for filename in files:
            if not is_text_file(filename):
                continue
                
            filepath = os.path.join(root, filename)
            
            # OPTIONAL: Prioritize files modified recently (The "All Day" Work)
            # mtime = os.path.getmtime(filepath)
            
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # Heuristic: Is this a persona?
                # If it's small (<10KB) or contains "Persona", "System", "Character"
                is_likely_persona = len(content) < 20000 
                
                if is_likely_persona:
                    print(f"  -> Ingesting: {filename} (from {os.path.basename(root)})")
                    loam.ingest_file_knowledge(
                        username="Sean",
                        filename=filename,
                        file_hash=f"auto_{filename}",
                        category="persona",  # Tagging as persona for Pocket Host
                        content_text=content,
                        provider="local"
                    )
                    restored_count += 1
            except Exception as e:
                # Ignore read errors on locked files
                pass

    print(f"\n--- DONE: {restored_count} Files Ingested. ---")
    print("Refresh your Pocket Host. If the file existed, it is now in the DB.")

if __name__ == "__main__":
    omni_restore()
    