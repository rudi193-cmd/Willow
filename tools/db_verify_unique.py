"""
Database Uniqueness Verification - Willow

Before cleanup, verify that "empty" databases don't contain unique data.
Compares against main databases to ensure nothing valuable is lost.

Author: Claude Code + Sean Campbell
Version: 1.0
"""

import sqlite3
import json
from pathlib import Path
from typing import Dict, List, Set
import hashlib

WILLOW_ROOT = Path(__file__).parent.parent
ARTIFACTS = WILLOW_ROOT / "artifacts"

# Main databases to compare against
MAIN_KNOWLEDGE_DB = ARTIFACTS / "Sweet-Pea-Rudi19" / "willow_knowledge.db"
MAIN_INDEX_DB = ARTIFACTS / "Sweet-Pea-Rudi19" / "database" / ".index.db"


def get_table_hashes(db_path: Path, table_name: str) -> Set[str]:
    """Get hashes of all rows in a table for comparison."""
    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get all rows
        rows = cursor.execute(f'SELECT * FROM "{table_name}"').fetchall()

        # Create hash for each row
        hashes = set()
        for row in rows:
            # Convert row to sorted tuple (to handle column order differences)
            row_data = json.dumps(dict(row), sort_keys=True, default=str)
            row_hash = hashlib.md5(row_data.encode()).hexdigest()
            hashes.add(row_hash)

        conn.close()
        return hashes

    except Exception as e:
        return set()


def analyze_database_uniqueness(db_path: Path) -> Dict:
    """Check if database contains any unique data."""
    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
        cursor = conn.cursor()

        # Get all tables
        tables = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()

        result = {
            "path": str(db_path),
            "has_unique_data": False,
            "tables": {},
            "total_rows": 0,
            "unique_rows": 0
        }

        for (table_name,) in tables:
            try:
                # Get row count
                count = cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
                result["total_rows"] += count

                if count == 0:
                    result["tables"][table_name] = {"rows": 0, "unique": 0, "status": "empty"}
                    continue

                # For knowledge tables, compare against main DB
                if table_name == "knowledge" and MAIN_KNOWLEDGE_DB.exists():
                    db_hashes = get_table_hashes(db_path, table_name)
                    main_hashes = get_table_hashes(MAIN_KNOWLEDGE_DB, table_name)

                    unique_hashes = db_hashes - main_hashes
                    unique_count = len(unique_hashes)

                    result["tables"][table_name] = {
                        "rows": count,
                        "unique": unique_count,
                        "status": "UNIQUE DATA!" if unique_count > 0 else "duplicate"
                    }

                    if unique_count > 0:
                        result["has_unique_data"] = True
                        result["unique_rows"] += unique_count

                        # Get sample of unique data
                        try:
                            sample_rows = cursor.execute(
                                f'SELECT id, title, source_type FROM "{table_name}" LIMIT 3'
                            ).fetchall()
                            result["tables"][table_name]["sample"] = [
                                {"id": r[0], "title": r[1][:50] if r[1] else "", "type": r[2]}
                                for r in sample_rows
                            ]
                        except:
                            pass

                # For catalog tables
                elif table_name == "catalog":
                    # Check if it has actual file entries
                    result["tables"][table_name] = {
                        "rows": count,
                        "unique": "unknown",
                        "status": "has_data" if count > 0 else "empty"
                    }

                    if count > 0:
                        result["has_unique_data"] = True  # Mark for review
                        result["unique_rows"] += count

                        # Get sample
                        try:
                            sample = cursor.execute(f'SELECT * FROM "{table_name}" LIMIT 3').fetchall()
                            result["tables"][table_name]["sample"] = [str(r)[:100] for r in sample]
                        except:
                            pass

                else:
                    # Other tables - just flag if they have data
                    result["tables"][table_name] = {
                        "rows": count,
                        "unique": count,
                        "status": "has_data" if count > 0 else "empty"
                    }

                    if count > 0:
                        result["has_unique_data"] = True
                        result["unique_rows"] += count

            except Exception as e:
                result["tables"][table_name] = {"error": str(e)[:100]}

        conn.close()
        return result

    except Exception as e:
        return {
            "path": str(db_path),
            "error": str(e)[:200],
            "has_unique_data": False
        }


def verify_empty_databases(empty_db_list: List[str]) -> Dict:
    """Verify all 'empty' databases for unique data."""
    print("Verifying 'empty' databases for unique data...")
    print("=" * 80)

    results = {
        "safe_to_delete": [],
        "has_unique_data": [],
        "has_unknown_data": [],
        "errors": []
    }

    for i, db_path in enumerate(empty_db_list, 1):
        if i % 50 == 0:
            print(f"  Progress: {i}/{len(empty_db_list)}")

        analysis = analyze_database_uniqueness(Path(db_path))

        if "error" in analysis:
            results["errors"].append(analysis)
        elif analysis["has_unique_data"]:
            if analysis["unique_rows"] > 0:
                results["has_unique_data"].append(analysis)
            else:
                results["has_unknown_data"].append(analysis)
        else:
            results["safe_to_delete"].append(analysis)

    return results


def generate_verification_report(results: Dict, output_file: Path):
    """Generate detailed verification report."""
    report = []
    report.append("=" * 80)
    report.append("DATABASE UNIQUENESS VERIFICATION REPORT")
    report.append("=" * 80)
    report.append("")

    safe_count = len(results["safe_to_delete"])
    unique_count = len(results["has_unique_data"])
    unknown_count = len(results["has_unknown_data"])
    error_count = len(results["errors"])

    report.append(f"SUMMARY:")
    report.append(f"  ✅ Safe to delete:       {safe_count:4d} (truly empty, no unique data)")
    report.append(f"  ⚠️  Has unique data:      {unique_count:4d} (DO NOT DELETE)")
    report.append(f"  🔍 Needs review:         {unknown_count:4d} (has data, unclear if unique)")
    report.append(f"  ❌ Errors:               {error_count:4d}")
    report.append("")

    # Show databases with UNIQUE data (critical)
    if results["has_unique_data"]:
        report.append("⚠️  DATABASES WITH UNIQUE DATA (DO NOT DELETE):")
        report.append("=" * 80)
        for db in results["has_unique_data"][:20]:
            report.append(f"\n  📁 {Path(db['path']).name}")
            report.append(f"     Path: {db['path']}")
            report.append(f"     Unique rows: {db['unique_rows']}")
            for table_name, info in db["tables"].items():
                if info.get("status") == "UNIQUE DATA!" or info.get("unique", 0) > 0:
                    report.append(f"     - {table_name}: {info['unique']} unique rows")
                    if "sample" in info:
                        for sample in info["sample"][:2]:
                            report.append(f"       Sample: {sample}")

        if len(results["has_unique_data"]) > 20:
            report.append(f"\n  ... and {len(results['has_unique_data']) - 20} more")
        report.append("")

    # Show databases needing review
    if results["has_unknown_data"]:
        report.append("🔍 DATABASES NEEDING REVIEW:")
        report.append("=" * 80)
        for db in results["has_unknown_data"][:15]:
            report.append(f"\n  📁 {Path(db['path']).name}")
            report.append(f"     Path: {db['path']}")
            report.append(f"     Total rows: {db['total_rows']}")
            for table_name, info in db["tables"].items():
                if isinstance(info, dict) and info.get("rows", 0) > 0:
                    report.append(f"     - {table_name}: {info['rows']} rows ({info.get('status')})")
        report.append("")

    # Safe to delete
    report.append("✅ SAFE TO DELETE (no unique data):")
    report.append("=" * 80)
    report.append(f"  {safe_count} databases are truly empty and safe to delete")
    for db in results["safe_to_delete"][:10]:
        report.append(f"  - {Path(db['path']).name}")
    if safe_count > 10:
        report.append(f"  ... and {safe_count - 10} more")
    report.append("")

    # Errors
    if results["errors"]:
        report.append("❌ ERRORS:")
        report.append("=" * 80)
        for db in results["errors"][:10]:
            report.append(f"  - {Path(db['path']).name}: {db.get('error', 'Unknown error')}")
        report.append("")

    # Write report
    output_file.write_text("\n".join(report), encoding="utf-8")
    print(f"\n✅ Verification report written to: {output_file}")

    return "\n".join(report)


if __name__ == "__main__":
    import json

    print("Database Uniqueness Verification Tool")
    print("=" * 80)
    print()

    # Load the empty databases list from cleanup report
    cleanup_report = WILLOW_ROOT / "tools" / "db_cleanup_report.txt"

    if not cleanup_report.exists():
        print("❌ Error: Run db_cleanup.py first to generate the list of empty databases")
        exit(1)

    # Parse the report to get empty database paths
    # For now, let's re-scan
    print("Scanning for databases marked as EMPTY...")

    from db_cleanup import find_all_databases, analyze_database

    databases = find_all_databases()
    empty_dbs = []

    for db in databases:
        analysis = analyze_database(db)
        if analysis["status"] == "EMPTY":
            empty_dbs.append(str(db))

    print(f"Found {len(empty_dbs)} databases marked as EMPTY")
    print()

    # Verify them
    results = verify_empty_databases(empty_dbs)

    # Generate report
    report_file = WILLOW_ROOT / "tools" / "db_verification_report.txt"
    generate_verification_report(results, report_file)

    # Summary
    print()
    print("=" * 80)
    print("VERIFICATION COMPLETE")
    print("=" * 80)
    print(f"✅ Safe to delete:    {len(results['safe_to_delete'])}")
    print(f"⚠️  Has unique data:   {len(results['has_unique_data'])}")
    print(f"🔍 Needs review:      {len(results['has_unknown_data'])}")
    print()

    if results["has_unique_data"]:
        print("⚠️  WARNING: Some databases contain UNIQUE data!")
        print("    Review the report before deleting anything.")
    else:
        print("✅ All 'empty' databases are safe to delete (no unique data found)")

    print()
    print(f"📄 Full report: {report_file}")
