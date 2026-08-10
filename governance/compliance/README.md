# Constitutional compliance case cards

Declarative Trace-ID cards for Article 0 / eternity-clause probes.

**This directory is the law seat's half of Appendix B** — `TRACE_ID`, `CLAUSE`,
and the one-line forbidden act. Files are constants + docstring only. They do
**not** import fleet runtime (`core.*`, `constitution.compliance`). Executable
adversarial suites that attack live gates belong in `willow-mcp` (and/or
`mem_ratify`); nestor's reciprocal audit lives in Die-Namic-Systems/nestor and
*reads* these cards by parsing, never by importing.

Provenance: lifted 2026-08-10 from the archived
`willow-2.0/constitution/cases/` tree (greenfield archive
`legacy-flat-2026-08-10`). Clause text retains historical mechanism names where
they document what the probe originally meant; living enforcement is whatever
the current product gates.

Consumers:

- nestor `scripts/feed_willow_constitution.py` / `audit_against_constitution.py`
  (`--cases` → this directory)
- Future willow-mcp / mem_ratify Appendix B runners
