"""
ecosystem_writer.py — Maintains ECOSYSTEM.md for the Willow project.

Provides read/write helpers for the section-based Markdown file stored in
Google Drive. All functions read the file fresh on every call (no caching)
and use atomic writes (tmp -> rename).
"""

import os
import re
from datetime import date
from pathlib import Path

ECOSYSTEM_PATH = Path(
    r"C:\Users\Sean\My Drive\Willow\Auth Users\Sweet-Pea-Rudi19\ECOSYSTEM.md"
)


def _read() -> str:
    try:
        return ECOSYSTEM_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _write_atomic(text: str) -> bool:
    tmp = ECOSYSTEM_PATH.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, ECOSYSTEM_PATH)
    return True


def _update_last_updated(text: str) -> str:
    today = date.today().isoformat()
    return re.sub(r"(\*\*Last updated:\*\*\s*).*", r"\g<1>" + today, text)


def get_section(section_name: str) -> str:
    """Return the body of section_name. Returns empty string if not found."""
    text = _read()
    if not text:
        return ""
    pattern = r"^## " + re.escape(section_name) + r"\s*\n(.*?)(?=^## |\Z)"
    m = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    if not m:
        return ""
    return m.group(1).rstrip("\n")


def update_section(section_name: str, content: str) -> bool:
    """Replace the body of section_name with content. Appends if not found."""
    text = _read()
    if not text:
        text = "**Last updated:** " + date.today().isoformat() + "\n\n---\n"
    body = content.rstrip("\n") + "\n"
    header_line = "## " + section_name
    pattern = r"(^## " + re.escape(section_name) + r"\s*\n)(.*?)(?=^## |\Z)"
    m = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    if m:
        new_text = text[: m.start(2)] + body + text[m.end(2):]
    else:
        new_section = "\n" + header_line + "\n" + body
        sep_match = re.search(r"^---\s*$", text, re.MULTILINE)
        if sep_match:
            insert_at = sep_match.start()
            new_text = text[:insert_at] + new_section + "\n" + text[insert_at:]
        else:
            new_text = text.rstrip("\n") + "\n" + new_section
    new_text = _update_last_updated(new_text)
    return _write_atomic(new_text)


def append_decision(decision: str) -> bool:
    """Append numbered entry to ## Design Decisions. Format: N. **YYYY-MM-DD — decision**"""
    section_body = get_section("Design Decisions")
    existing = re.findall(r"^\s*(\d+)\.", section_body, re.MULTILINE)
    next_n = (max(int(n) for n in existing) + 1) if existing else 1
    today = date.today().isoformat()
    new_entry = f"{next_n}. **{today} \u2014 {decision}**"
    updated_body = (
        section_body.rstrip("\n") + "\n" + new_entry + "\n"
        if section_body.strip()
        else new_entry + "\n"
    )
    return update_section("Design Decisions", updated_body)


def update_app_status(app_name: str, state: str, notes: str = "") -> bool:
    """Update State column for row matching app_name in ## Repos table."""
    section_body = get_section("Repos")
    if not section_body:
        return False
    lines = section_body.split("\n")
    header_idx = next(
        (i for i, l in enumerate(lines) if re.match(r"^\s*\|", l) and "|" in l), None
    )
    if header_idx is None:
        return False
    header_cells = [c.strip() for c in lines[header_idx].strip().strip("|").split("|")]
    col_map = {name.lower(): idx for idx, name in enumerate(header_cells)}
    app_col = col_map.get("app / working name") or col_map.get("app")
    state_col = col_map.get("state")
    why_col = col_map.get("why built")
    if app_col is None or state_col is None:
        return False
    updated = False
    for i in range(header_idx + 1, len(lines)):
        line = lines[i]
        if not re.match(r"^\s*\|", line):
            continue
        cells = line.strip().strip("|").split("|")
        if len(cells) <= max(app_col, state_col):
            continue
        if app_name.lower() in cells[app_col].strip().lower():
            cells[state_col] = " " + state + " "
            if notes and why_col is not None and len(cells) > why_col:
                existing_why = cells[why_col].strip()
                cells[why_col] = (
                    " " + existing_why + " " + notes + " "
                    if existing_why
                    else " " + notes + " "
                )
            lines[i] = "|" + "|".join(cells) + "|"
            updated = True
            break
    if not updated:
        return False
    return update_section("Repos", "\n".join(lines))


if __name__ == "__main__":
    print("ecosystem_writer OK — System section found:", bool(get_section("System")))
