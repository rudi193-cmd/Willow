#!/usr/bin/env python3
"""Doc-integrity gate for willow-grove.

willow-grove owns no runtime code — its product is prose whose whole value is
that every claim is traceable. The README says so directly: every claim carries
a ``file:line`` citation, and each finding carries a "re-verify with" command. A
citation that has rotted is worse than none, because it trains a reader to stop
checking. So the one thing CI can enforce without the sibling repos present is
that the docs' *internal* links and section anchors still resolve.

This is the fleet's stdlib source-scanner pattern (cf. safe-app-store's
drift-guards): no third-party deps, fails closed on a broken reference.

Deliberately **not** checked here:

* External links (``http``/``https``/``mailto``) — flaky in CI and not this
  repo's contract.
* Citations into sibling repos — those appear as inline ``code`` spans, never as
  markdown links, and belong to each finding's per-item "re-verify with" command,
  not to CI.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# [label](target) — inline links. Reference-style/autolinks aren't used in these
# docs; keep the matcher narrow so inline `code` and citations are never links.
_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_EXTERNAL = ("http://", "https://", "mailto:", "tel:", "//")


def slug(heading: str) -> str:
    """GitHub-flavoured heading -> anchor slug.

    Lowercase, drop everything that isn't a word char / space / hyphen (so
    backticks, asterisks, em dashes and colons vanish), then spaces to hyphens.
    """
    s = heading.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    return s.replace(" ", "-")


def anchors_of(text: str) -> set[str]:
    """Every heading anchor a reader can link to, GitHub's disambiguation included."""
    out: set[str] = set()
    seen: dict[str, int] = {}
    for line in text.splitlines():
        m = _HEADING.match(line)
        if not m:
            continue
        base = slug(m.group(2))
        n = seen.get(base, 0)
        out.add(base if n == 0 else f"{base}-{n}")  # GitHub: repeats get -1, -2, …
        seen[base] = n + 1
    return out


# Generated / vendored dirs that may hold stray .md files (e.g. pytest's cache
# README) — never part of the repo's own prose.
_SKIP_DIRS = {".git", ".pytest_cache", "__pycache__", "node_modules", ".venv"}


def _md_files(root: Path) -> list[Path]:
    return sorted(
        p for p in root.rglob("*.md") if _SKIP_DIRS.isdisjoint(p.parts)
    )


def _targets(text: str) -> list[str]:
    out = []
    for raw in _LINK.findall(text):
        target = raw.strip()
        # Drop an optional link title: [x](path "title") / [x](#a 'title').
        if " " in target:
            target = target.split(" ", 1)[0]
        out.append(target)
    return out


def check(root: Path = ROOT) -> list[str]:
    """Return a list of broken-reference messages (empty == clean)."""
    errors: list[str] = []
    cache: dict[Path, str] = {}

    def read(p: Path) -> str:
        if p not in cache:
            cache[p] = p.read_text(encoding="utf-8")
        return cache[p]

    for md in _md_files(root):
        text = read(md)
        rel = md.relative_to(root)
        for target in _targets(text):
            if not target or target.startswith(_EXTERNAL) or "://" in target:
                continue
            if target.startswith("#"):
                anchor = target[1:]
                if anchor and anchor.lower() not in anchors_of(text):
                    errors.append(f"{rel}: anchor '#{anchor}' not found in this file")
                continue
            path_part, _, anchor = target.partition("#")
            if not path_part:
                continue
            tgt = (md.parent / path_part).resolve()
            if not tgt.exists():
                errors.append(f"{rel}: link target '{path_part}' does not exist")
                continue
            if anchor and tgt.suffix == ".md" and anchor.lower() not in anchors_of(read(tgt)):
                errors.append(
                    f"{rel}: anchor '#{anchor}' not found in {tgt.relative_to(root)}"
                )
    return errors


def main() -> int:
    files = _md_files(ROOT)
    errors = check(ROOT)
    if errors:
        print("Doc-integrity check FAILED:\n")
        for e in errors:
            print(f"  ✗ {e}")
        print(f"\n{len(errors)} broken reference(s) across {len(files)} doc(s).")
        return 1
    print(
        f"Doc-integrity check passed: internal links and anchors resolve across "
        f"{len(files)} doc(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
