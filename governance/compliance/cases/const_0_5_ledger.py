"""CONST-0-5 — The Record is append-only and its keepers are bound by it.

Declarative compliance card (charter). No executable probe body.

The forbidden act, in one line: *silently rewriting what was already recorded.*
"""
from __future__ import annotations

TRACE_ID = "CONST-0-5"
CLAUSE = (
    "The Record is append-only and tamper-evident: a past ledger entry's content "
    "may never be silently rewritten; the hash chain detects any alteration, and no "
    "API alters a past entry's content (Article VI; FRANK hash-chained ledger)."
)
