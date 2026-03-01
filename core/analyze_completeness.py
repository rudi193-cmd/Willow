from core.db import get_connection
import sqlite3
from collections import defaultdict
import re

DB_PATH = 'C:/Users/Sean/Documents/GitHub/Willow/core/rag.db'

def analyze_wip():
    """Find TODO, FIXME, WIP markers in codebase."""
    conn = get_connection()
    cur = conn.cursor()
    
    wip_patterns = ['TODO', 'FIXME', 'WIP', 'HACK', 'XXX', 'NOTE: incomplete']
    wip_items = defaultdict(list)
    
    cur.execute('SELECT repo, file_path, text FROM chunks')
    
    for repo, file_path, text in cur.fetchall():
        for pattern in wip_patterns:
            if pattern in text:
                # Extract context
                lines = text.split('\n')
                for line in lines:
                    if pattern in line:
                        wip_items[repo].append({
                            'file': file_path,
                            'marker': pattern,
                            'context': line.strip()[:100]
                        })
    
    conn.close()
    return dict(wip_items)

def analyze_skeleton_modules():
    """Find modules with very few functions (likely incomplete)."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        SELECT repo, file_path, COUNT(*) as count
        FROM chunks
        WHERE type IN ('function', 'class')
        GROUP BY repo, file_path
        HAVING count < 3
        ORDER BY repo, count
    ''')
    
    skeleton = defaultdict(list)
    for repo, file_path, count in cur.fetchall():
        skeleton[repo].append({'file': file_path, 'entities': count})
    
    conn.close()
    return dict(skeleton)

def analyze_ring_structure():
    """Analyze each ring's completeness."""
    conn = get_connection()
    cur = conn.cursor()
    
    rings = {
        'source_ring': 'die-namic',
        'bridge_ring': 'willow',
        'continuity_ring': 'willow'
    }
    
    ring_stats = {}
    
    for ring_name, repo in rings.items():
        cur.execute('''
            SELECT 
                COUNT(DISTINCT file_path) as files,
                COUNT(CASE WHEN type='class' THEN 1 END) as classes,
                COUNT(CASE WHEN type='function' THEN 1 END) as functions,
                COUNT(CASE WHEN type='module' THEN 1 END) as modules
            FROM chunks
            WHERE repo = ? AND file_path LIKE ?
        ''', (repo, f'%{ring_name}%'))
        
        result = cur.fetchone()
        if result and result[0] > 0:
            ring_stats[ring_name] = {
                'files': result[0],
                'classes': result[1],
                'functions': result[2],
                'modules': result[3]
            }
    
    conn.close()
    return ring_stats

def generate_report():
    """Generate full completeness report."""
    print("="*80)
    print("SYSTEM COMPLETENESS ANALYSIS")
    print("="*80)
    
    # Ring analysis
    print("\n[RING STRUCTURE ANALYSIS]")
    print("-"*80)
    rings = analyze_ring_structure()
    for ring_name, stats in sorted(rings.items()):
        print(f"\n{ring_name.upper()}:")
        for key, val in stats.items():
            print(f"  {key}: {val}")
    
    # Skeleton modules (likely incomplete)
    print("\n[SKELETON MODULES] (< 3 entities = likely incomplete)")
    print("-"*80)
    skeleton = analyze_skeleton_modules()
    for repo in sorted(skeleton.keys()):
        print(f"\n{repo}:")
        for item in skeleton[repo][:15]:  # Limit output
            print(f"  {item['file']}: {item['entities']} entities")
        if len(skeleton[repo]) > 15:
            print(f"  ... and {len(skeleton[repo])-15} more")
    
    # WIP items
    print("\n[WIP / INCOMPLETE MARKERS]")
    print("-"*80)
    wip = analyze_wip()
    for repo in sorted(wip.keys()):
        print(f"\n{repo}:")
        markers = defaultdict(int)
        for item in wip[repo]:
            markers[item['marker']] += 1
        for marker, count in sorted(markers.items(), key=lambda x: -x[1]):
            print(f"  {marker}: {count} occurrences")
        
        # Show sample
        print(f"  Sample issues:")
        for item in wip[repo][:5]:
            print(f"    - {item['file']}: {item['context']}")
    
    # Gap analysis
    print("\n[ARCHITECTURE GAPS]")
    print("-"*80)
    expected_modules = [
        'encryption/decryption',
        'consensus mechanism',
        'privacy verification',
        'audit trails (complete)',
        'credential management',
        'rate limiting',
        'cache layer',
        'worker pool management'
    ]
    
    print("\nExpected SAFE components (verify existence):")
    for module in expected_modules:
        print(f"  - {module}: [TODO - manual verification needed]")

if __name__ == '__main__':
    generate_report()
