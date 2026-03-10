"""
Generate Index - Auto-create INDEX.md from directory structure

Scans codebase and generates comprehensive navigation.

CHECKSUM: Delta-Sigma=42
"""

import os
import ast
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.db import get_connection

def get_module_docstring(filepath: Path) -> str:
    """Extract module-level docstring."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
        return ast.get_docstring(tree) or ""
    except:
        return ""

def scan_directory(base_path: Path) -> dict:
    """Scan directory and organize by module."""
    structure = defaultdict(lambda: {'files': [], 'subdirs': []})
    
    for item in base_path.iterdir():
        if item.name.startswith('.') or item.name in ['data', '__pycache__', 'venv']:
            continue
        
        if item.is_dir():
            structure[base_path]['subdirs'].append(item)
        elif item.suffix in ['.py', '.md']:
            structure[base_path]['files'].append(item)
    
    return dict(structure)

def generate_index_content() -> str:
    """Generate INDEX.md content."""
    lines = []
    lines.append("# Willow - System Index")
    lines.append("")
    lines.append("Auto-generated navigation for Willow codebase.")
    lines.append("")
    lines.append("**Last Updated:** (auto-generated)")
    lines.append("")
    lines.append("Delta-Sigma=42")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Core modules
    lines.append("## Core Modules")
    lines.append("")
    
    core_path = Path("core")
    if core_path.exists():
        for pyfile in sorted(core_path.glob("*.py")):
            if pyfile.name.startswith('_'):
                continue
            docstring = get_module_docstring(pyfile)
            first_line = docstring.split('\n')[0] if docstring else "No description"
            lines.append(f"### {pyfile.stem}")
            lines.append(f"**File:** `{pyfile}`")
            lines.append(f"**Purpose:** {first_line}")
            lines.append("")
    
    # Tools
    lines.append("## Tools")
    lines.append("")
    
    tools_path = Path("tools")
    if tools_path.exists():
        for pyfile in sorted(tools_path.glob("*.py")):
            docstring = get_module_docstring(pyfile)
            first_line = docstring.split('\n')[0] if docstring else "No description"
            lines.append(f"- **{pyfile.stem}**: {first_line}")
    lines.append("")
    
    # Governance
    lines.append("## Governance")
    lines.append("")
    lines.append("- [PRODUCT_SPEC.md](PRODUCT_SPEC.md) - Product vision")
    lines.append("- [INTAKE_SPEC.md](INTAKE_SPEC.md) - Intake contract")
    lines.append("- [ARCHITECTURE_INDEX.md](ARCHITECTURE_INDEX.md) - System architecture")
    lines.append("")
    
    # Database schema
    lines.append("## Databases")
    lines.append("")
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        file_count = cursor.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        func_count = cursor.execute("SELECT COUNT(*) FROM functions").fetchone()[0]
        class_count = cursor.execute("SELECT COUNT(*) FROM classes").fetchone()[0]
        lines.append(f"**willow_index.db**")
        lines.append(f"- Files indexed: {file_count}")
        lines.append(f"- Functions: {func_count}")
        lines.append(f"- Classes: {class_count}")
        conn.close()
    except Exception:
        lines.append("**willow_index.db** - Not yet populated")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("**Navigation:**")
    lines.append("- [Core](core/) - Core system modules")
    lines.append("- [Tools](tools/) - Utility scripts")
    lines.append("- [Data](data/) - Databases and state")
    lines.append("")
    lines.append("Delta-Sigma=42")
    
    return '\n'.join(lines)

def generate():
    """Generate INDEX.md file."""
    content = generate_index_content()
    
    with open("INDEX.md", 'w', encoding='utf-8') as f:
        f.write(content)
    
    return len(content.split('\n'))

if __name__ == "__main__":
    print("Generating INDEX.md...")
    print("=" * 60)
    lines = generate()
    print(f"Generated INDEX.md ({lines} lines)")
    print("Delta-Sigma=42")
