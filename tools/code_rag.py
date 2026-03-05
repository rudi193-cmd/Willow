"""
Code RAG - Index Python/MD files for semantic search

Extracts functions, classes, docstrings and embeds them.
Similar to conversation_rag but for code.

CHECKSUM: ΔΣ=42
"""

import os
import sys
import ast
import hashlib
from pathlib import Path
from typing import List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
import conversation_rag  # Reuse existing RAG infrastructure

def extract_python_chunks(filepath: Path) -> List[Dict[str, Any]]:
    """Extract functions and classes from Python file."""
    chunks = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Extract function
                docstring = ast.get_docstring(node) or ""
                start_line = node.lineno
                end_line = node.end_lineno or start_line
                
                chunks.append({
                    'type': 'function',
                    'name': node.name,
                    'docstring': docstring,
                    'line_range': f"{start_line}-{end_line}",
                    'content': f"def {node.name}(...): {docstring}"
                })
                
            elif isinstance(node, ast.ClassDef):
                # Extract class
                docstring = ast.get_docstring(node) or ""
                start_line = node.lineno
                end_line = node.end_lineno or start_line
                
                chunks.append({
                    'type': 'class',
                    'name': node.name,
                    'docstring': docstring,
                    'line_range': f"{start_line}-{end_line}",
                    'content': f"class {node.name}: {docstring}"
                })
    except:
        # Fallback: chunk by lines
        chunks.append({
            'type': 'file',
            'name': filepath.name,
            'content': content[:1000] if 'content' in locals() else '[Error reading file]'
        })
    
    return chunks

def extract_markdown_chunks(filepath: Path) -> List[Dict[str, Any]]:
    """Extract sections from Markdown file."""
    chunks = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split by headers
        sections = []
        current_section = []
        current_header = None
        
        for line in content.split('\n'):
            if line.startswith('#'):
                if current_section:
                    sections.append({
                        'header': current_header,
                        'content': '\n'.join(current_section)
                    })
                current_header = line
                current_section = []
            else:
                current_section.append(line)
        
        if current_section:
            sections.append({
                'header': current_header,
                'content': '\n'.join(current_section)
            })
        
        for section in sections:
            chunks.append({
                'type': 'section',
                'name': section['header'] or filepath.name,
                'content': f"{section['header']}\n{section['content'][:500]}"
            })
    except:
        pass
    
    return chunks

def index_code_file(filepath: Path) -> int:
    """Index a single code file into RAG."""
    if filepath.suffix == '.py':
        chunks = extract_python_chunks(filepath)
    elif filepath.suffix == '.md':
        chunks = extract_markdown_chunks(filepath)
    else:
        return 0
    
    # Store chunks using existing RAG infrastructure
    db = conversation_rag.init_db()
    indexed = 0
    
    for chunk in chunks:
        content_text = f"{filepath.relative_to(Path.cwd())}\n"
        content_text += f"Type: {chunk.get('type', 'unknown')}\n"
        content_text += f"Name: {chunk.get('name', 'N/A')}\n"
        content_text += chunk.get('content', '')
        
        # Create unique chunk ID
        chunk_id = hashlib.md5(f"{filepath}:{chunk.get('name', '')}".encode()).hexdigest()
        
        # Embed and store
        import sqlite3
        conn = sqlite3.connect(conversation_rag.DB_PATH)
        cursor = conn.cursor()
        
        import embeddings
        embedding_bytes = embeddings.embed(content_text)
        
        cursor.execute("""
            INSERT OR REPLACE INTO conversation_chunks
            (chunk_id, session_id, timestamp, role, content, embedding, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            chunk_id,
            str(filepath.parent),
            None,
            chunk.get('type', 'code'),
            content_text,
            embedding_bytes,
            str({'file': str(filepath), 'line_range': chunk.get('line_range')})
        ))
        conn.commit()
        conn.close()
        indexed += 1
    
    return indexed

def index_all_code(base_path: Path = Path.cwd()) -> Dict[str, int]:
    """Index all Python and MD files."""
    stats = {'files': 0, 'chunks': 0, 'errors': 0}
    
    for filepath in base_path.rglob("*.py"):
        if '.git' in str(filepath) or 'data' in str(filepath):
            continue
        try:
            chunks = index_code_file(filepath)
            stats['files'] += 1
            stats['chunks'] += chunks
        except Exception as e:
            stats['errors'] += 1
            print(f"Error indexing {filepath}: {e}")
    
    for filepath in base_path.rglob("*.md"):
        if '.git' in str(filepath):
            continue
        try:
            chunks = index_code_file(filepath)
            stats['files'] += 1
            stats['chunks'] += chunks
        except Exception as e:
            stats['errors'] += 1
            print(f"Error indexing {filepath}: {e}")
    
    return stats

if __name__ == "__main__":
    print("Code RAG Indexer")
    print("=" * 60)
    stats = index_all_code()
    print(f"Indexed: {stats['files']} files")
    print(f"Created: {stats['chunks']} chunks")
    print(f"Errors: {stats['errors']}")
    print("Delta-Sigma=42")
