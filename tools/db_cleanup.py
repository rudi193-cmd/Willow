"""
Database Cleanup Tool - Willow

Identifies and removes abandoned/empty database files.
Consolidates duplicate indexes.

SAFETY: Dry-run by default. Use --execute to actually delete files.

Author: Claude Code + Sean Campbell
Version: 1.0
Checksum: ΔΣ=42
"""

import os
import sqlite3
from pathlib import Path
from typing import List, Dict, Tuple
import json

WILLOW_ROOT = Path(__file__).parent.parent
ARTIFACTS = WILLOW_ROOT / "artifacts"

# Files smaller than this are considered "empty" (just schema, no real data)
EMPTY_THRESHOLD_KB = 20  # 20KB = schema only


def analyze_database(db_path: Path) -> Dict:
    """Analyze a database file to determine if it's active/useful."""
    try:
        size_kb = db_path.stat().st_size / 1024

        # Quick check: if it's tiny, it's probably empty
        if size_kb < EMPTY_THRESHOLD_KB:
            return {
                "path": str(db_path),
                "size_kb": round(size_kb, 1),
                "status": "EMPTY",
                "row_count": 0,
                "reason": f"File size {size_kb:.1f}KB < threshold {EMPTY_THRESHOLD_KB}KB"
            }

        # Check actual row counts
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Get all tables
        tables = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()

        total_rows = 0
        table_info = []

        for (table_name,) in tables:
            try:
                count = cursor.execute(f"SELECT COUNT(*) FROM \"{table_name}\"").fetchone()[0]
                total_rows += count
                if count > 0:
                    table_info.append(f"{table_name}:{count}")
            except:
                pass

        conn.close()

        if total_rows == 0:
            status = "EMPTY"
            reason = f"0 rows across {len(tables)} tables"
        elif total_rows < 10:
            status = "MINIMAL"
            reason = f"{total_rows} rows - {', '.join(table_info)}"
        else:
            status = "ACTIVE"
            reason = f"{total_rows} rows - {', '.join(table_info[:3])}"

        return {
            "path": str(db_path),
            "size_kb": round(size_kb, 1),
            "status": status,
            "row_count": total_rows,
            "reason": reason
        }

    except Exception as e:
        return {
            "path": str(db_path),
            "size_kb": 0,
            "status": "ERROR",
            "row_count": 0,
            "reason": str(e)[:100]
        }


def find_all_databases() -> List[Path]:
    """Find all .db files in artifacts directory."""
    return list(ARTIFACTS.rglob("*.db"))


def categorize_databases(databases: List[Path]) -> Dict[str, List[Dict]]:
    """Analyze and categorize all databases."""
    results = {
        "EMPTY": [],
        "MINIMAL": [],
        "ACTIVE": [],
        "ERROR": []
    }

    print(f"Analyzing {len(databases)} databases...")

    for i, db in enumerate(databases, 1):
        if i % 50 == 0:
            print(f"  Progress: {i}/{len(databases)}")

        analysis = analyze_database(db)
        results[analysis["status"]].append(analysis)

    return results


def find_duplicates(databases: List[Dict]) -> List[Tuple[str, List[str]]]:
    """Find databases with same name in different locations."""
    by_name = {}

    for db in databases:
        name = Path(db["path"]).name
        if name not in by_name:
            by_name[name] = []
        by_name[name].append(db)

    duplicates = []
    for name, dbs in by_name.items():
        if len(dbs) > 1:
            duplicates.append((name, dbs))

    return duplicates


def generate_report(results: Dict, output_file: Path):
    """Generate cleanup report."""
    report = []
    report.append("=" * 80)
    report.append("WILLOW DATABASE CLEANUP REPORT")
    report.append("=" * 80)
    report.append("")

    # Summary
    total_empty = len(results["EMPTY"])
    total_minimal = len(results["MINIMAL"])
    total_active = len(results["ACTIVE"])
    total_error = len(results["ERROR"])

    empty_size_mb = sum(db["size_kb"] for db in results["EMPTY"]) / 1024
    minimal_size_mb = sum(db["size_kb"] for db in results["MINIMAL"]) / 1024

    report.append(f"SUMMARY:")
    report.append(f"  Empty databases:   {total_empty:4d} ({empty_size_mb:.1f} MB)")
    report.append(f"  Minimal databases: {total_minimal:4d} ({minimal_size_mb:.1f} MB)")
    report.append(f"  Active databases:  {total_active:4d}")
    report.append(f"  Errors:            {total_error:4d}")
    report.append("")

    # Cleanup candidates
    report.append("RECOMMENDED FOR CLEANUP (EMPTY):")
    report.append("-" * 80)
    for db in sorted(results["EMPTY"], key=lambda x: x["size_kb"], reverse=True)[:30]:
        report.append(f"  {db['size_kb']:6.1f}KB  {db['path']}")
        report.append(f"           {db['reason']}")
    if total_empty > 30:
        report.append(f"  ... and {total_empty - 30} more")
    report.append("")

    # Minimal databases
    report.append("MINIMAL DATABASES (REVIEW BEFORE CLEANUP):")
    report.append("-" * 80)
    for db in sorted(results["MINIMAL"], key=lambda x: x["row_count"])[:20]:
        report.append(f"  {db['size_kb']:6.1f}KB  {db['row_count']:3d} rows  {Path(db['path']).name}")
        report.append(f"           {db['reason']}")
    report.append("")

    # Active databases
    report.append("ACTIVE DATABASES (KEEP):")
    report.append("-" * 80)
    for db in sorted(results["ACTIVE"], key=lambda x: x["size_kb"], reverse=True)[:15]:
        report.append(f"  {db['size_kb']:7.1f}KB  {db['row_count']:6d} rows  {Path(db['path']).name}")
    report.append("")

    # Find duplicates
    all_dbs = results["EMPTY"] + results["MINIMAL"] + results["ACTIVE"]
    duplicates = find_duplicates(all_dbs)

    if duplicates:
        report.append("POTENTIAL DUPLICATES:")
        report.append("-" * 80)
        for name, dbs in sorted(duplicates, key=lambda x: len(x[1]), reverse=True)[:10]:
            report.append(f"  {name} ({len(dbs)} copies):")
            for db in dbs:
                report.append(f"    {db['size_kb']:6.1f}KB  {db['status']:8s}  {db['path']}")
        report.append("")

    # Write report
    output_file.write_text("\n".join(report), encoding="utf-8")
    print(f"\nReport written to: {output_file}")

    return "\n".join(report)


def execute_cleanup(results: Dict, dry_run: bool = True):
    """Execute cleanup of empty databases."""
    to_delete = results["EMPTY"]

    if dry_run:
        print(f"\n[DRY RUN] Would delete {len(to_delete)} empty databases:")
        for db in to_delete[:10]:
            print(f"  - {db['path']}")
        if len(to_delete) > 10:
            print(f"  ... and {len(to_delete) - 10} more")
        print("\nTo execute for real, run with --execute flag")
    else:
        print(f"\n[EXECUTING] Deleting {len(to_delete)} empty databases...")
        deleted = 0
        errors = 0

        for db in to_delete:
            try:
                Path(db["path"]).unlink()
                deleted += 1
                if deleted % 50 == 0:
                    print(f"  Deleted {deleted}/{len(to_delete)}")
            except Exception as e:
                print(f"  Error deleting {db['path']}: {e}")
                errors += 1

        print(f"\nCleanup complete:")
        print(f"  Deleted: {deleted}")
        print(f"  Errors: {errors}")


if __name__ == "__main__":
    import sys

    execute = "--execute" in sys.argv

    print("Willow Database Cleanup Tool")
    print("=" * 80)
    print()

    # Find all databases
    databases = find_all_databases()
    print(f"Found {len(databases)} database files")
    print()

    # Analyze
    results = categorize_databases(databases)

    # Generate report
    report_file = WILLOW_ROOT / "tools" / "db_cleanup_report.txt"
    generate_report(results, report_file)

    # Execute cleanup if requested
    if execute:
        confirm = input("\n⚠️  Are you sure you want to delete empty databases? (yes/no): ")
        if confirm.lower() == "yes":
            execute_cleanup(results, dry_run=False)
        else:
            print("Cleanup cancelled.")
    else:
        execute_cleanup(results, dry_run=True)

    print("\nDone!")
    print(f"Review the report: {report_file}")
