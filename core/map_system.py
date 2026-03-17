from core.db import get_connection
from collections import defaultdict
from pathlib import Path

DB_PATH = 'C:/Users/Sean/Documents/GitHub/Willow/core/rag.db'

def get_all_entities():
    """Extract all functions and classes from RAG."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        SELECT repo, file_path, type, entity_name, text
        FROM chunks
        WHERE type IN ('function', 'class')
        ORDER BY repo, file_path, entity_name
    ''')
    
    results = cur.fetchall()
    conn.close()
    return results

def build_map():
    """Build a hierarchical map of the system."""
    entities = get_all_entities()
    
    # Organize by repo, then file, then type
    structure = defaultdict(lambda: defaultdict(lambda: {'functions': [], 'classes': []}))
    
    for repo, file_path, entity_type, entity_name, text in entities:
        if entity_type == 'function':
            structure[repo][file_path]['functions'].append(entity_name)
        elif entity_type == 'class':
            structure[repo][file_path]['classes'].append(entity_name)
    
    return dict(structure)

def print_map(structure):
    """Print a formatted system map."""
    for repo in sorted(structure.keys()):
        print(f"\n{'='*70}")
        print(f"REPO: {repo.upper()}")
        print(f"{'='*70}")
        
        files = structure[repo]
        
        # Group by directory
        by_dir = defaultdict(list)
        for file_path in files:
            dir_path = str(Path(file_path).parent)
            by_dir[dir_path].append(file_path)
        
        for dir_path in sorted(by_dir.keys()):
            if dir_path != '.':
                print(f"\n[D] {dir_path}/")
            
            for file_path in sorted(by_dir[dir_path]):
                entities = files[file_path]
                print(f"\n  [F] {Path(file_path).name}")
                
                if entities['classes']:
                    print(f"     Classes: {', '.join(entities['classes'][:5])}", end='')
                    if len(entities['classes']) > 5:
                        print(f" (+{len(entities['classes'])-5} more)", end='')
                    print()
                
                if entities['functions']:
                    print(f"     Functions: {', '.join(entities['functions'][:5])}", end='')
                    if len(entities['functions']) > 5:
                        print(f" (+{len(entities['functions'])-5} more)", end='')
                    print()

def print_stats(structure):
    """Print statistics."""
    print(f"\n{'='*70}")
    print("SYSTEM STATISTICS")
    print(f"{'='*70}")
    
    total_files = sum(len(files) for files in structure.values())
    total_classes = sum(len(f['classes']) for files in structure.values() for f in files.values())
    total_functions = sum(len(f['functions']) for files in structure.values() for f in files.values())
    
    for repo in sorted(structure.keys()):
        files = structure[repo]
        num_files = len(files)
        num_classes = sum(len(f['classes']) for f in files.values())
        num_functions = sum(len(f['functions']) for f in files.values())
        
        print(f"\n{repo}:")
        print(f"  Files: {num_files}")
        print(f"  Classes: {num_classes}")
        print(f"  Functions: {num_functions}")
    
    print(f"\nTOTAL:")
    print(f"  Files: {total_files}")
    print(f"  Classes: {total_classes}")
    print(f"  Functions: {total_functions}")

if __name__ == '__main__':
    print("Building system map from RAG...")
    structure = build_map()
    
    print_stats(structure)
    print_map(structure)
