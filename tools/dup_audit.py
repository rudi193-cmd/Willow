import sys, os, re
from collections import defaultdict
from datetime import date

os.environ['WILLOW_DB_URL'] = 'postgresql://willow:willow@localhost:5437/willow'
sys.path.insert(0, r'C:\Users\Sean\Documents\GitHub\Willow\core')
import db

conn = db.get_connection()
cur = conn.cursor()

# Set schema
cur.execute("SET search_path = sweet_pea_rudi19, public")

# Get total counts
cur.execute("SELECT COUNT(*) FROM entities")
total = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM entities WHERE never_promote = 1")
blocked = cur.fetchone()[0]

print(f"Total entities: {total}, Blocked: {blocked}")

# Fetch all non-blocked entities
cur.execute("""
    SELECT id, name, entity_type, mention_count, layer, reference_string,
           promotion_status, never_promote, domain
    FROM entities
    WHERE never_promote != 1
    ORDER BY mention_count DESC
""")
rows = cur.fetchall()
cols = ['id','name','entity_type','mention_count','layer','reference_string',
        'promotion_status','never_promote','domain']
entities = [dict(zip(cols, r)) for r in rows]
print(f"Active entities fetched: {len(entities)}")

# ---------------------------------------------------------
# CHECK 1: Exact case-insensitive duplicates
# ---------------------------------------------------------
ci_groups = defaultdict(list)
for e in entities:
    ci_groups[e['name'].lower()].append(e)

check1_groups = {k: v for k, v in ci_groups.items() if len(v) > 1}
print(f"Check 1 (case-insensitive): {len(check1_groups)} groups")

# ---------------------------------------------------------
# CHECK 2: Whitespace/punctuation normalized
# ---------------------------------------------------------
def normalize(name):
    n = name.lower().strip()
    n = re.sub(r'\s+', ' ', n)
    n = re.sub(r'^[\s\W]+|[\s\W]+$', '', n)
    return n

norm_groups = defaultdict(list)
for e in entities:
    norm_groups[normalize(e['name'])].append(e)

check2_groups = {}
for k, v in norm_groups.items():
    if len(v) > 1:
        raw_names = set(x['name'].lower() for x in v)
        if len(raw_names) > 1:
            check2_groups[k] = v

print(f"Check 2 (whitespace/punct normalized): {len(check2_groups)} groups")

# ---------------------------------------------------------
# CHECK 3: r/ and u/ prefix variants
# ---------------------------------------------------------
prefixed = [e for e in entities if e['name'].startswith('r/') or e['name'].startswith('u/')]
check3_groups = {}
name_lookup = {e['name'].lower(): e for e in entities}

for e in prefixed:
    bare = e['name'].split('/', 1)[1].lower()
    if bare in name_lookup:
        key = f"prefix:{bare}"
        if key not in check3_groups:
            check3_groups[key] = []
        if e not in check3_groups[key]:
            check3_groups[key].append(e)
        bare_ent = name_lookup[bare]
        if bare_ent not in check3_groups[key]:
            check3_groups[key].append(bare_ent)

print(f"Check 3 (prefix variants r/u/): {len(check3_groups)} groups")

# ---------------------------------------------------------
# CHECK 4: Trailing punctuation variants
# ---------------------------------------------------------
def strip_trailing_punct(name):
    return re.sub(r'[\s.,!?;:\-]+$', '', name.lower().strip())

trail_groups = defaultdict(list)
for e in entities:
    trail_groups[strip_trailing_punct(e['name'])].append(e)

check4_groups = {}
for k, v in trail_groups.items():
    if len(v) > 1:
        raw_names = set(x['name'].lower() for x in v)
        if len(raw_names) > 1:
            check4_groups[k] = v

print(f"Check 4 (trailing punct): {len(check4_groups)} groups")

# ---------------------------------------------------------
# CHECK 5: Plural/singular variants
# ---------------------------------------------------------
def depluralize(name):
    n = name.lower().strip()
    if n.endswith('ies') and len(n) > 4:
        return n[:-3] + 'y'
    if n.endswith('ses') and len(n) > 4:
        return n[:-2]
    if n.endswith('ches') and len(n) > 5:
        return n[:-1]
    if n.endswith('s') and len(n) > 3 and not n.endswith('ss'):
        return n[:-1]
    return n

plural_groups = defaultdict(list)
for e in entities:
    plural_groups[depluralize(e['name'])].append(e)

check5_groups = {}
for k, v in plural_groups.items():
    if len(v) > 1:
        raw_names = set(x['name'].lower() for x in v)
        if len(raw_names) > 1:
            check5_groups[k] = v

print(f"Check 5 (plural/singular): {len(check5_groups)} groups")

# ---------------------------------------------------------
# CHECK 6: Substring/abbreviation pairs (same type)
# ---------------------------------------------------------
type_groups_map = defaultdict(list)
for e in entities:
    if e['entity_type']:
        type_groups_map[e['entity_type']].append(e)

check6_groups = {}
for etype, ents in type_groups_map.items():
    ents_limited = ents[:500]
    for i, a in enumerate(ents_limited):
        for b in ents_limited[i+1:]:
            na = a['name'].lower()
            nb = b['name'].lower()
            if len(na) >= 3 and len(nb) >= 3:
                if na in nb or nb in na:
                    key = f"substr:{min(na,nb)}:{etype}"
                    if key not in check6_groups:
                        check6_groups[key] = []
                    if a not in check6_groups[key]:
                        check6_groups[key].append(a)
                    if b not in check6_groups[key]:
                        check6_groups[key].append(b)

print(f"Check 6 (substring/abbreviation): {len(check6_groups)} groups")

# ---------------------------------------------------------
# Merge all groups, deduplicate, filter by >= 2 mentions combined
# ---------------------------------------------------------
all_groups = {}
method_counts = {
    'case_insensitive': 0,
    'whitespace_punct': 0,
    'prefix_variant': 0,
    'trailing_punct': 0,
    'plural_singular': 0,
    'substring': 0,
}

def add_group(groups_dict, method, prefix=''):
    for k, v in groups_dict.items():
        total_mentions = sum(e['mention_count'] or 0 for e in v)
        if total_mentions < 2:
            continue
        key = f"{prefix}{k}"
        if key not in all_groups:
            all_groups[key] = {'entities': v, 'method': method, 'norm': k}
            method_counts[method] += 1
        else:
            existing_ids = {e['id'] for e in all_groups[key]['entities']}
            for e in v:
                if e['id'] not in existing_ids:
                    all_groups[key]['entities'].append(e)

add_group(check1_groups, 'case_insensitive', 'ci:')
add_group(check2_groups, 'whitespace_punct', 'wp:')
add_group(check3_groups, 'prefix_variant', '')
add_group(check4_groups, 'trailing_punct', 'tp:')
add_group(check5_groups, 'plural_singular', 'ps:')
add_group(check6_groups, 'substring', '')

print(f"\nAll merged groups (>= 2 mentions): {len(all_groups)}")

# Sort by total mentions DESC
sorted_groups = sorted(
    all_groups.items(),
    key=lambda x: sum(e['mention_count'] or 0 for e in x[1]['entities']),
    reverse=True
)

total_merge_candidates = sum(
    len(g['entities']) - 1
    for _, g in sorted_groups
)
total_canonical = len(sorted_groups)

print(f"Total merge candidates: {total_merge_candidates} entities -> {total_canonical} canonical")

# ---------------------------------------------------------
# Build report
# ---------------------------------------------------------
REPORT_LIMIT = 100
show_groups = sorted_groups[:REPORT_LIMIT]
extra_groups = len(sorted_groups) - REPORT_LIMIT if len(sorted_groups) > REPORT_LIMIT else 0

lines = []
lines.append("# Duplicate Entity Audit")
lines.append(f"Date: {date.today().isoformat()}")
lines.append(f"Total entities scanned: {total}")
lines.append(f"Blocked (never_promote=1): {blocked}")
lines.append("")
lines.append("## Summary")
lines.append(f"- Exact case-insensitive matches: {method_counts['case_insensitive']} groups")
lines.append(f"- Whitespace/punct variants: {method_counts['whitespace_punct']} groups")
lines.append(f"- Prefix variants (r/, u/): {method_counts['prefix_variant']} groups")
lines.append(f"- Trailing punct variants: {method_counts['trailing_punct']} groups")
lines.append(f"- Plural/singular: {method_counts['plural_singular']} groups")
lines.append(f"- Substring/abbreviation: {method_counts['substring']} groups")
lines.append(f"- **Total merge candidates: {total_merge_candidates} entities to {total_canonical} canonical entries**")
if extra_groups > 0:
    lines.append(f"- Note: Showing top {REPORT_LIMIT} groups by mention count. {extra_groups} additional groups omitted.")
lines.append("")

# Type breakdown
type_counts = defaultdict(int)
for _, g in sorted_groups:
    for e in g['entities']:
        type_counts[e['entity_type'] or 'unknown'] += 1

lines.append("## Merge Candidates (sorted by total mentions DESC)")
lines.append("")

for norm_key, g in show_groups:
    ents = sorted(g['entities'], key=lambda x: x['mention_count'] or 0, reverse=True)
    total_m = sum(e['mention_count'] or 0 for e in ents)
    method = g['method']
    norm = g['norm']

    display_norm = norm.replace('prefix:', '').replace('substr:', '')
    if ':' in display_norm:
        display_norm = display_norm.rsplit(':', 1)[0]

    lines.append(f"### GROUP `{display_norm}` -- {total_m} total mentions [{method}]")
    lines.append("")
    lines.append("| id | name | type | mentions | RECOMMENDED ACTION |")
    lines.append("|----|------|------|----------|--------------------|")

    for i, e in enumerate(ents):
        action = "KEEP (primary)" if i == 0 else f"MERGE to {ents[0]['id']}"
        name_escaped = e['name'].replace('|', '\\|')
        etype = e['entity_type'] or 'unknown'
        lines.append(f"| {e['id']} | {name_escaped} | {etype} | {e['mention_count'] or 0} | {action} |")

    lines.append("")

if extra_groups > 0:
    lines.append(f"*... {extra_groups} additional duplicate groups not shown (all have fewer mentions than those above)*")
    lines.append("")

lines.append("## Statistics")
lines.append("")
lines.append("### By Detection Method")
lines.append("| Method | Groups |")
lines.append("|--------|--------|")
for m, c in method_counts.items():
    lines.append(f"| {m} | {c} |")
lines.append("")
lines.append("### By Entity Type (in duplicate groups)")
lines.append("| Type | Count |")
lines.append("|------|-------|")
for etype, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
    lines.append(f"| {etype} | {cnt} |")
lines.append("")

report = '\n'.join(lines)

out_path = r'C:\Users\Sean\Documents\GitHub\Willow\tools\dup_audit_report.md'
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(report)

print(f"\n{'='*50}")
print(f"Total groups found: {len(sorted_groups)}")
print(f"Total entities that could be merged: {total_merge_candidates}")
print(f"File written: {out_path}")

cur.close()
conn.close()
