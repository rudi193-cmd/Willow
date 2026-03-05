"""
Artifact Folder Consolidation

Merges the 229-folder chaos into ~14 canonical folders.
DRY RUN by default — pass --execute to actually move files.

Usage:
    python scripts/consolidate_artifacts.py          # dry run
    python scripts/consolidate_artifacts.py --execute
"""
import os
import sys
import shutil
import argparse
from pathlib import Path

BASE = Path(__file__).parent.parent / "artifacts" / "Sweet-Pea-Rudi19"

# Canonical folders — these are preserved as-is
KEEP = {
    "pending", "screenshots", "photos", "social", "documents",
    "code", "data", "audio", "video", "narrative", "specs",
    "governance", "binary", "archive", "_junk"
}

# Merge map: folder_name -> canonical destination
MERGE = {
    # Screenshots
    "screencapture": "screenshots",
    "screen_recorder": "screenshots",

    # Photos (only if clearly photos, not screenshots)
    # photos stays as photos

    # Social
    "reddit": "social",
    "redditscreenshots": "social",
    "social-media-tracker": "social",
    "processed_reddit": "social",

    # Documents (all text/pdf/doc formats)
    "text": "documents",
    "txt": "documents",
    "plaintext": "documents",
    "plain": "documents",
    "texts": "documents",
    "textextract": "documents",
    "textextraction": "documents",
    "textract": "documents",
    "textraction": "documents",
    "texetextract": "documents",
    "texextract": "documents",
    "plainext": "documents",
    "txtextract": "documents",
    "document": "documents",
    "docs": "documents",
    "pdf": "documents",
    "pdfs": "documents",
    "markdown": "documents",
    "thefoldernameistext": "documents",
    "thefoldernameistexts": "documents",

    # Code
    "python": "code",
    "javascript": "code",
    "jsx": "code",
    "js": "code",
    "typescript": "code",
    "batch": "code",
    "batchfiles": "code",
    "bash": "code",
    "bashscripts": "code",
    "script": "code",
    "scripts": "code",
    "thecorrectfoldernameiscode": "code",
    "thefoldernameshouldbepython": "code",
    "codes": "code",

    # Data
    "json": "data",
    "jsonfiles": "data",
    "jsontxt": "data",
    "csv": "data",
    "training": "data",
    "jupyter": "data",
    "xlsx": "data",
    "excel": "data",

    # Audio
    "audio": "audio",
    "m4a": "audio",
    "midi": "audio",
    "mid": "audio",

    # Video
    "video": "video",
    "videos": "video",
    "vid": "video",

    # Archive (unclassifiable)
    "unknown": "archive",
    "unsorted": "archive",
    "unidentified": "archive",
    "unread": "archive",
    "undecided": "archive",
    "undecidable": "archive",
    "unnamed": "archive",
    "untitled": "archive",
    "new": "archive",
}


def is_junk_name(name: str) -> bool:
    """Detect LLM hallucinated folder names."""
    # Random hex-like strings
    if len(name) > 15 and all(c in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in name.lower()):
        # Check if it looks like a real word compound
        real_words = {"screenshot", "document", "python", "javascript", "binary",
                      "training", "narrative", "governance", "audio", "video"}
        if not any(w in name.lower() for w in real_words):
            return True
    # LLM narration patterns
    junk_patterns = [
        "thecorrectfoldername", "thefoldernameis", "thefoldernameshould",
        "thisimagecontains", "thisisavideo", "avideoofan",
        "filetypeis", "filetypebinary", "filetypepdf", "filetypepython", "filetypeunread",
        "filesinthefolder", "filesize0kb", "filestype", "filenew",
        "0bytes0pages", "size95kb", "2004307200", "ireserved_special_token",
        "contentmachinelearning", "exporttrainingdata",
    ]
    name_lower = name.lower()
    return any(p in name_lower for p in junk_patterns)


def consolidate(dry_run: bool = True):
    if not BASE.exists():
        print(f"ERROR: {BASE} not found")
        return

    # Ensure canonical folders exist
    for folder in KEEP:
        dest = BASE / folder
        if not dry_run:
            dest.mkdir(exist_ok=True)
        else:
            print(f"[MKDIR] {folder}/")

    moved = 0
    junked = 0
    skipped = 0

    all_folders = sorted([d for d in BASE.iterdir() if d.is_dir()])

    for folder in all_folders:
        name = folder.name

        if name in KEEP:
            continue

        files = list(folder.rglob("*"))
        file_count = sum(1 for f in files if f.is_file())

        # Determine destination
        if name in MERGE:
            dest_name = MERGE[name]
        elif is_junk_name(name):
            dest_name = "_junk"
        else:
            dest_name = "archive"
            print(f"[UNKNOWN] {name}/ ({file_count} files) -> archive")

        dest_dir = BASE / dest_name

        if file_count == 0:
            # Empty folder — just remove it
            action = f"[RMDIR ] {name}/"
            if not dry_run:
                try:
                    folder.rmdir()
                except:
                    pass
            junked += 1
        else:
            action = f"[MOVE  ] {name}/ ({file_count} files) -> {dest_name}/"
            if not dry_run:
                if not dest_dir.exists():
                    dest_dir.mkdir(exist_ok=True)
                for f in folder.rglob("*"):
                    if f.is_file():
                        target = dest_dir / f.name
                        # Don't overwrite
                        if target.exists():
                            target = dest_dir / f"{f.stem}_{name}{f.suffix}"
                        try:
                            shutil.move(str(f), str(target))
                        except Exception as e:
                            print(f"  ERROR moving {f.name}: {e}")
                try:
                    shutil.rmtree(str(folder))
                except:
                    pass
            moved += file_count

        print(action)

    print(f"\n{'DRY RUN' if dry_run else 'DONE'}: {moved} files moved, {junked} empty folders removed")
    if dry_run:
        print("Run with --execute to apply changes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Actually move files (default: dry run)")
    args = parser.parse_args()
    consolidate(dry_run=not args.execute)
