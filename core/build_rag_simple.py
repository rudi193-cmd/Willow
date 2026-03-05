from core.db import get_connection
import os
import sqlite3
import ast
import re
from pathlib import Path

REPOS = {
    'willow': 'C:/Users/Sean/Documents/GitHub/Willow',
    'die-namic': 'C:/Users/Sean/Documents/GitHub/die-namic-system'
}

DB_PATH = 'C:/Users/Sean/Documents/GitHub/Willow/core/rag.db'

def init_db():
    conn = get_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            repo TEXT,
            file_path TEXT,
            type TEXT,
            entity_name TEXT
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_repo ON chunks(repo)')
    conn.commit()
    return conn

def extract_py_chunks(file_path, content):
    chunks = []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return chunks
    
    module_doc = ast.get_docstring(tree)
    if module_doc:
        chunks.append({
            'text': module_doc,
            'type': 'module',
            'entity_name': 'module'
        })
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            doc = ast.get_docstring(node)
            if doc:
                chunks.append({
                    'text': doc,
                    'type': 'function',
                    'entity_name': node.name
                })
        elif isinstance(node, ast.ClassDef):
            doc = ast.get_docstring(node)
            if doc:
                chunks.append({
                    'text': doc,
                    'type': 'class',
                    'entity_name': node.name
                })
    
    return chunks

def extract_md_chunks(file_path, content):
    chunks = []
    sections = re.split(r'^(##\s+.+)$', content, flags=re.MULTILINE)
    
    if sections[0].strip():
        chunks.append({
            'text': sections[0].strip(),
            'type': 'intro',
            'entity_name': 'intro'
        })
    
    for i in range(1, len(sections), 2):
        if i >= len(sections):
            break
        header = sections[i]
        body = sections[i + 1] if i + 1 < len(sections) else ''
        header_name = header.replace('##', '').strip()
        
        if body.strip():
            chunks.append({
                'text': f"{header_name}\n\n{body.strip()}",
                'type': 'spec',
                'entity_name': header_name
            })
    
    return chunks

def index_repo(repo_path, repo_name):
    conn = init_db()
    cur = conn.cursor()
    
    skip_dirs = {'__pycache__', '.git', '.pytest_cache', 'venv', 'env', 'node_modules'}
    indexed = 0
    
    repo_dir = Path(repo_path)
    
    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        
        for file in files:
            if file.startswith('test_') or file.endswith('_test.py'):
                continue
            
            file_path = os.path.join(root, file)
            
            try:
                rel_path = os.path.relpath(file_path, repo_dir)
            except (ValueError, OSError):
                continue
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except (UnicodeDecodeError, IOError, OSError):
                continue
            
            chunks = []
            
            if file.endswith('.py'):
                chunks = extract_py_chunks(rel_path, content)
            elif file.endswith('.md'):
                chunks = extract_md_chunks(rel_path, content)
            
            for chunk in chunks:
                try:
                    cur.execute('''
                        INSERT INTO chunks (text, repo, file_path, type, entity_name)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (
                        chunk['text'],
                        repo_name,
                        rel_path,
                        chunk.get('type', 'doc'),
                        chunk.get('entity_name', '')
                    ))
                    indexed += 1
                except Exception:
                    pass
    
    conn.commit()
    conn.close()
    return indexed

def search_rag(query, limit=5):
    conn = get_connection()
    cur = conn.cursor()
    
    search_term = f"%{query}%"
    cur.execute('''
        SELECT text, repo, file_path, type, entity_name
        FROM chunks
        WHERE text LIKE ? OR entity_name LIKE ?
        LIMIT ?
    ''', (search_term, search_term, limit))
    
    results = []
    for row in cur.fetchall():
        results.append({
            'text': row[0][:200],
            'repo': row[1],
            'file_path': row[2],
            'type': row[3],
            'entity_name': row[4]
        })
    
    conn.close()
    return results

def main():
    print("Building RAG index (text search, no embeddings)...")
    
    willow_count = index_repo(REPOS['willow'], 'willow')
    print(f"Indexed {willow_count} chunks from Willow")
    
    dinamic_count = index_repo(REPOS['die-namic'], 'die-namic')
    print(f"Indexed {dinamic_count} chunks from Die-namic")
    
    total = willow_count + dinamic_count
    print(f"\nTotal chunks indexed: {total}")
    print(f"Database: {DB_PATH}")
    
    if total > 0:
        print("\nSample search test:")
        results = search_rag("function", limit=2)
        for r in results:
            print(f"  - {r['entity_name']} ({r['type']}) in {r['file_path']}")

if __name__ == '__main__':
    main()
