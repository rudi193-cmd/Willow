#!/usr/bin/env python3
"""
Release validation utilities.

Prepares artifacts for distribution by cleaning internal references.
"""

import os
import re
import sys
import shutil
import hashlib
from pathlib import Path
from datetime import datetime

# Patterns to strip from files
STRIP_PATTERNS = [
    r'C:\\Users\\[^\\]+\\',          # Windows user paths
    r'/Users/[^/]+/',                 # Mac user paths
    r'/home/[^/]+/',                  # Linux user paths
    r'die-namic-system',              # Internal repo name
    r'rudi193-cmd',                   # GitHub username in comments
    r'# TODO:.*internal.*',           # Internal TODOs
    r'# HACK:.*',                     # Hack comments
    r'# DEBUG:.*',                    # Debug comments
]

# Files to exclude from release
EXCLUDE_FILES = [
    '.env',
    '.env.local',
    'credentials.json',
    '*.log',
    '*.pyc',
    '__pycache__',
    '.DS_Store',
    'desktop.ini',
    'Thumbs.db',
]

# Directories to exclude
EXCLUDE_DIRS = [
    '__pycache__',
    '.git',
    'node_modules',
    '.venv',
    'venv',
]


def clean_content(content: str) -> str:
    """Remove internal references from content."""
    cleaned = content
    for pattern in STRIP_PATTERNS:
        cleaned = re.sub(pattern, '[REDACTED]', cleaned, flags=re.IGNORECASE)
    return cleaned


def should_exclude(path: Path) -> bool:
    """Check if path should be excluded from release."""
    name = path.name

    # Check directory exclusions
    for part in path.parts:
        if part in EXCLUDE_DIRS:
            return True

    # Check file exclusions
    for pattern in EXCLUDE_FILES:
        if pattern.startswith('*'):
            if name.endswith(pattern[1:]):
                return True
        elif name == pattern:
            return True

    return False


def hash_file(path: Path) -> str:
    """Generate SHA256 hash of file."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()[:12]


def validate_artifact(source_dir: Path, output_dir: Path, dry_run: bool = True) -> dict:
    """
    Validate and prepare artifact for release.

    Args:
        source_dir: Directory containing artifact to validate
        output_dir: Directory to write cleaned artifact
        dry_run: If True, only report what would be done

    Returns:
        Manifest dictionary
    """
    manifest = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'source': str(source_dir),
        'files': [],
        'excluded': [],
        'cleaned': [],
        'errors': [],
    }

    if not source_dir.exists():
        manifest['errors'].append(f'Source not found: {source_dir}')
        return manifest

    for root, dirs, files in os.walk(source_dir):
        # Filter excluded directories
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        for filename in files:
            source_path = Path(root) / filename
            rel_path = source_path.relative_to(source_dir)

            if should_exclude(source_path):
                manifest['excluded'].append(str(rel_path))
                continue

            # Read and clean content
            try:
                with open(source_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                cleaned = clean_content(content)
                was_cleaned = cleaned != content

                if was_cleaned:
                    manifest['cleaned'].append(str(rel_path))

                # Output
                if not dry_run:
                    output_path = output_dir / rel_path
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(cleaned)

                manifest['files'].append({
                    'path': str(rel_path),
                    'hash': hash_file(source_path),
                    'cleaned': was_cleaned,
                })

            except UnicodeDecodeError:
                # Binary file - copy as-is
                if not dry_run:
                    output_path = output_dir / rel_path
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_path, output_path)

                manifest['files'].append({
                    'path': str(rel_path),
                    'hash': hash_file(source_path),
                    'binary': True,
                })

            except Exception as e:
                manifest['errors'].append(f'{rel_path}: {e}')

    return manifest


def print_manifest(manifest: dict):
    """Print manifest summary."""
    print(f"Validation Report")
    print(f"=" * 40)
    print(f"Timestamp: {manifest['timestamp']}")
    print(f"Source: {manifest['source']}")
    print()
    print(f"Files processed: {len(manifest['files'])}")
    print(f"Files excluded: {len(manifest['excluded'])}")
    print(f"Files cleaned: {len(manifest['cleaned'])}")
    print(f"Errors: {len(manifest['errors'])}")

    if manifest['cleaned']:
        print()
        print("Cleaned files:")
        for f in manifest['cleaned']:
            print(f"  - {f}")

    if manifest['excluded']:
        print()
        print("Excluded files:")
        for f in manifest['excluded'][:10]:
            print(f"  - {f}")
        if len(manifest['excluded']) > 10:
            print(f"  ... and {len(manifest['excluded']) - 10} more")

    if manifest['errors']:
        print()
        print("Errors:")
        for e in manifest['errors']:
            print(f"  ! {e}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python validate_release.py <source_dir> [output_dir]")
        print()
        print("Options:")
        print("  source_dir  Directory to validate")
        print("  output_dir  Output directory (default: dry run)")
        sys.exit(1)

    source = Path(sys.argv[1])
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    dry_run = output is None

    if dry_run:
        print("DRY RUN - no files will be modified")
        print()

    manifest = validate_artifact(source, output or Path('.'), dry_run)
    print_manifest(manifest)

    if manifest['errors']:
        sys.exit(1)
