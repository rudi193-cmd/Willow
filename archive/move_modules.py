from pathlib import Path

source_dir = Path('artifacts/Sweet-Pea-Rudi19/free_fleet_builds')
dest_dir = Path('core')

files = [
    'seed_packet.py',
    'checksum_chain.py',
    'time_resume_capsule.py',
    'recursion_tracker.py',
    'workflow_state.py',
    'gate_lateral_review.py',
    'aionic_ledger.py'
]

for filename in files:
    src = source_dir / filename
    dst = dest_dir / filename

    if src.exists():
        content = src.read_text(encoding='utf-8')

        # Strip markdown code blocks
        if content.startswith('```'):
            lines = content.split('\n')
            cleaned_lines = []
            for line in lines[1:]:
                if line.strip() == '```':
                    continue
                cleaned_lines.append(line)
            content = '\n'.join(cleaned_lines)

        dst.write_text(content, encoding='utf-8')
        print(f'Moved: {filename}')
    else:
        print(f'Not found: {filename}')
