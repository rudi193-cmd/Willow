"""
Populate Index - Extract metadata into willow_index.db

Scans Python files for imports, classes, functions.
Creates structured, searchable database.

CHECKSUM: ΔΣ=42
"""

import os
import ast
import sys
from pathlib import Path
from typing import Set, List

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.db import get_connection

def init_db():
    """Create tables for code metadata."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            file_id INTEGER PRIMARY KEY,
            path TEXT UNIQUE NOT NULL,
            module_name TEXT,
            docstring TEXT,
            line_count INTEGER,
            last_indexed TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS functions (
            func_id INTEGER PRIMARY KEY,
            file_id INTEGER,
            name TEXT NOT NULL,
            docstring TEXT,
            line_start INTEGER,
            line_end INTEGER,
            FOREIGN KEY (file_id) REFERENCES files(file_id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS classes (
            class_id INTEGER PRIMARY KEY,
            file_id INTEGER,
            name TEXT NOT NULL,
            docstring TEXT,
            line_start INTEGER,
            line_end INTEGER,
            FOREIGN KEY (file_id) REFERENCES files(file_id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS imports (
            import_id INTEGER PRIMARY KEY,
            file_id INTEGER,
            module_name TEXT NOT NULL,
            imported_names TEXT,
            FOREIGN KEY (file_id) REFERENCES files(file_id)
        )
    """)
    
    conn.commit()
    conn.close()

def extract_metadata(filepath: Path) -> dict:
    """Extract all metadata from Python file."""
    metadata = {
        'functions': [],
        'classes': [],
        'imports': [],
        'docstring': None
    }
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content)
        metadata['docstring'] = ast.get_docstring(tree)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                metadata['functions'].append({
                    'name': node.name,
                    'docstring': ast.get_docstring(node),
                    'line_start': node.lineno,
                    'line_end': node.end_lineno
                })
            elif isinstance(node, ast.ClassDef):
                metadata['classes'].append({
                    'name': node.name,
                    'docstring': ast.get_docstring(node),
                    'line_start': node.lineno,
                    'line_end': node.end_lineno
                })
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    metadata['imports'].append({
                        'module': alias.name,
                        'names': None
                    })
            elif isinstance(node, ast.ImportFrom):
                names = [alias.name for alias in node.names]
                metadata['imports'].append({
                    'module': node.module or '',
                    'names': ', '.join(names)
                })
    except:
        pass
    
    return metadata

def index_file(filepath: Path):
    """Index single file into database."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get metadata
    metadata = extract_metadata(filepath)
    
    # Insert file
    cursor.execute("""
        INSERT OR REPLACE INTO files (path, module_name, docstring, line_count, last_indexed)
        VALUES (?, ?, ?, ?, ?)
    """, (
        str(filepath),
        filepath.stem,
        metadata['docstring'],
        sum(1 for _ in open(filepath, 'r', encoding='utf-8', errors='ignore')),
        __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ))
    
    # Get file_id (works for both INSERT and REPLACE)
    file_id = cursor.execute("SELECT file_id FROM files WHERE path = ?", (str(filepath),)).fetchone()[0]
    
    # Insert functions
    for func in metadata['functions']:
        cursor.execute("""
            INSERT INTO functions (file_id, name, docstring, line_start, line_end)
            VALUES (?, ?, ?, ?, ?)
        """, (file_id, func['name'], func['docstring'], func['line_start'], func['line_end']))
    
    # Insert classes
    for cls in metadata['classes']:
        cursor.execute("""
            INSERT INTO classes (file_id, name, docstring, line_start, line_end)
            VALUES (?, ?, ?, ?, ?)
        """, (file_id, cls['name'], cls['docstring'], cls['line_start'], cls['line_end']))
    
    # Insert imports
    for imp in metadata['imports']:
        cursor.execute("""
            INSERT INTO imports (file_id, module_name, imported_names)
            VALUES (?, ?, ?)
        """, (file_id, imp['module'], imp['names']))
    
    conn.commit()
    conn.close()

def populate_all():
    """Index all Python files."""
    init_db()
    
    stats = {'files': 0, 'functions': 0, 'classes': 0, 'imports': 0}
    
    for filepath in Path.cwd().rglob("*.py"):
        if '.git' in str(filepath) or 'data' in str(filepath):
            continue
        
        try:
            index_file(filepath)
            stats['files'] += 1
        except Exception as e:
            print(f"Error: {filepath}: {e}")
    
    # Get final counts
    conn = get_connection()
    cursor = conn.cursor()
    stats['functions'] = cursor.execute("SELECT COUNT(*) FROM functions").fetchone()[0]
    stats['classes'] = cursor.execute("SELECT COUNT(*) FROM classes").fetchone()[0]
    stats['imports'] = cursor.execute("SELECT COUNT(*) FROM imports").fetchone()[0]
    conn.close()
    
    return stats

if __name__ == "__main__":
    print("Populating willow_index.db...")
    print("=" * 60)
    stats = populate_all()
    print(f"Files indexed: {stats['files']}")
    print(f"Functions: {stats['functions']}")
    print(f"Classes: {stats['classes']}")
    print(f"Imports: {stats['imports']}")
    print("Delta-Sigma=42")
