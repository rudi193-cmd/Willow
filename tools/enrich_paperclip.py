#!/usr/bin/env python3
"""
Operation Paperclip Scientist Enricher
=======================================
Fetches biographical data for unenriched scientists via Wikipedia API,
updates operation_paperclip_genealogy.db, then syncs to Willow knowledge graph.

Run:
    /home/sean/.willow-venv/bin/python tools/enrich_paperclip.py [--limit N] [--dry-run]

Uses Wikipedia API (free, no key needed). Rate limited to ~1 req/sec.
Idempotent: skips scientists with birth_year already set.
"""

import sys
import time
import json
import sqlite3
import logging
import argparse
import urllib.request
import urllib.parse
from datetime import datetime, UTC
from pathlib import Path

REPO = "/mnt/c/Users/Sean/Documents/GitHub/Willow"
sys.path.insert(0, REPO)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("enrich")

PAPERCLIP_DB = "/mnt/c/Users/Sean/My Drive (rudi193@gmail.com)/Willow/Nest/operation_paperclip_genealogy.db"
WILLOW_DB    = f"{REPO}/artifacts/Sweet-Pea-Rudi19/willow_knowledge.db"

WIKIPEDIA_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKIPEDIA_SEARCH = "https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={query}&format=json&srlimit=3"


HEADERS = {"User-Agent": "WillowEnricher/1.0"}


def _get(url: str) -> dict | None:
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        log.debug(f"HTTP failed: {url}: {e}")
        return None


def wiki_get(title: str) -> dict | None:
    """Fetch Wikipedia REST summary for a page title."""
    url = WIKIPEDIA_API.format(title=urllib.parse.quote(title, safe=""))
    return _get(url)


def wiki_search(query: str) -> str | None:
    """Search Wikipedia, return first result title."""
    url = WIKIPEDIA_SEARCH.format(query=urllib.parse.quote(query))
    data = _get(url)
    if data:
        results = data.get("query", {}).get("search", [])
        if results:
            return results[0]["title"]
    return None


def wikidata_years(wiki_title: str) -> tuple[int | None, int | None]:
    """Fetch birth/death years from Wikidata via the Wikipedia article title."""
    # Step 1: Get Wikidata entity ID from Wikipedia
    url = (f"https://en.wikipedia.org/w/api.php?action=query"
           f"&titles={urllib.parse.quote(wiki_title)}&prop=pageprops&format=json")
    data = _get(url)
    if not data:
        return None, None

    wikidata_id = None
    for page in data.get("query", {}).get("pages", {}).values():
        wikidata_id = page.get("pageprops", {}).get("wikibase_item")
        break
    if not wikidata_id:
        return None, None

    # Step 2: Get birth (P569) and death (P570) from Wikidata
    wd_url = (f"https://www.wikidata.org/w/api.php?action=wbgetentities"
              f"&ids={wikidata_id}&props=claims&format=json")
    wd = _get(wd_url)
    if not wd:
        return None, None

    claims = wd.get("entities", {}).get(wikidata_id, {}).get("claims", {})
    birth = death = None

    for prop, key in [("P569", "birth"), ("P570", "death")]:
        try:
            val = claims[prop][0]["mainsnak"]["datavalue"]["value"]["time"]
            year = int(val[1:5])  # "+YYYY-MM-DDT..."
            if key == "birth":
                birth = year
            else:
                death = year
        except (KeyError, IndexError, ValueError):
            pass

    return birth, death


def fetch_scientist_data(name: str) -> dict:
    """Fetch biographical data for a scientist from Wikipedia + Wikidata."""
    result = {"birth_year": None, "death_year": None, "wikipedia_url": None, "notes": None}

    # Try direct name lookup first
    data = wiki_get(name)
    if not data or data.get("type") == "disambiguation":
        search_title = wiki_search(f"{name} engineer scientist Operation Paperclip Germany")
        if search_title:
            data = wiki_get(search_title)

    if not data:
        return result

    page_title = data.get("title", "")
    extract = data.get("extract", "")
    wiki_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(page_title.replace(' ', '_'))}"

    result["wikipedia_url"] = wiki_url
    result["notes"] = extract[:500] if extract else None

    # Get birth/death from Wikidata (structured, reliable)
    time.sleep(0.5)  # small pause between wiki + wikidata calls
    birth, death = wikidata_years(page_title)
    result["birth_year"] = birth
    result["death_year"] = death

    return result


def update_willow_atom(wdb: sqlite3.Connection, scientist_id: int, name: str, field: str,
                       birth: int | None, death: int | None, affil: str | None,
                       wiki: str | None, notes: str | None):
    """Update Willow knowledge atom and entity description for an enriched scientist."""
    source_id = f"paperclip-scientist-{scientist_id}"

    content = (
        f"Operation Paperclip scientist: {name}\n"
        f"Field: {field}\n"
        + (f"Born: {birth}  " if birth else "")
        + (f"Died: {death}\n" if death else "\n")
        + f"Nazi affiliation: {affil or 'unknown'}\n"
        + (f"Wikipedia: {wiki}\n" if wiki else "")
        + (f"Notes: {notes}" if notes else "")
    ).strip()

    summary = (
        f"{name} was a German {field.lower()} specialist brought to the United States "
        f"under Operation Paperclip after World War II."
        + (f" Nazi affiliation: {(affil or '')[:80]}." if affil and affil != "unknown" else "")
    )

    wdb.execute(
        "UPDATE knowledge SET summary = ?, content_snippet = ? "
        "WHERE source_type = 'paperclip' AND source_id = ?",
        (summary, content[:1000], source_id)
    )

    description = f"Operation Paperclip scientist, {field}"
    if birth: description += f", b.{birth}"
    if death: description += f"–d.{death}"
    wdb.execute(
        "UPDATE entities SET description = ? WHERE name = ? AND entity_type = 'person'",
        (description, name)
    )


def main():
    parser = argparse.ArgumentParser(description="Enrich Paperclip scientist records from Wikipedia")
    parser.add_argument("--limit", type=int, default=0, help="Max scientists to enrich (0=all)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fetched without writing")
    parser.add_argument("--force", action="store_true", help="Re-enrich already-enriched records")
    args = parser.parse_args()

    src = sqlite3.connect(PAPERCLIP_DB)
    src.row_factory = sqlite3.Row
    wdb = sqlite3.connect(WILLOW_DB, timeout=30)
    wdb.execute("PRAGMA journal_mode=WAL")

    now = datetime.now(UTC).isoformat()

    # Fetch unenriched scientists (or all if --force)
    if args.force:
        scientists = src.execute("SELECT * FROM scientists ORDER BY field, full_name").fetchall()
    else:
        scientists = src.execute(
            "SELECT * FROM scientists WHERE birth_year IS NULL ORDER BY field, full_name"
        ).fetchall()

    total = len(scientists)
    if args.limit > 0:
        scientists = scientists[:args.limit]

    log.info(f"Unenriched: {total}, processing: {len(scientists)}")

    enriched = 0
    not_found = 0

    for i, row in enumerate(scientists, start=1):
        name = row["full_name"]
        field = row["field"] or "Unknown"
        log.info(f"[{i}/{len(scientists)}] {name} ({field})")

        if args.dry_run:
            print(f"  [DRY-RUN] Would fetch: {name}")
            continue

        data = fetch_scientist_data(name)

        if not data["birth_year"] and not data["wikipedia_url"]:
            log.debug(f"  No data found for {name}")
            not_found += 1
        else:
            # Write to genealogy DB
            src.execute(
                """UPDATE scientists SET
                   birth_year = COALESCE(?, birth_year),
                   death_year = COALESCE(?, death_year),
                   wikipedia_url = COALESCE(?, wikipedia_url),
                   notes = COALESCE(?, notes),
                   updated_at = ?
                   WHERE id = ?""",
                (data["birth_year"], data["death_year"], data["wikipedia_url"],
                 data["notes"], now, row["id"])
            )

            # Sync to Willow
            update_willow_atom(
                wdb, row["id"], name, field,
                data["birth_year"], data["death_year"],
                row["nazi_affiliation"], data["wikipedia_url"], data["notes"]
            )

            enriched += 1
            years = f"{data['birth_year']}–{data['death_year']}" if data['birth_year'] else "dates unknown"
            log.info(f"  -> {years}  {data['wikipedia_url'] or 'no wiki'}")

        # Commit every 10
        if i % 10 == 0:
            src.commit()
            wdb.commit()
            log.info(f"  Checkpoint: {enriched} enriched, {not_found} not found so far")

        # Rate limit — Wikipedia asks for 1 req/sec
        time.sleep(1.1)

    src.commit()
    wdb.commit()

    log.info("=" * 50)
    log.info(f"Enriched:   {enriched}")
    log.info(f"Not found:  {not_found}")
    total_enriched = src.execute("SELECT COUNT(*) FROM scientists WHERE birth_year IS NOT NULL").fetchone()[0]
    log.info(f"Total with birth_year: {total_enriched} / {src.execute('SELECT COUNT(*) FROM scientists').fetchone()[0]}")
    log.info("Done.")

    wdb.close()
    src.close()


if __name__ == "__main__":
    main()
