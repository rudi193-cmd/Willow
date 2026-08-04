# Handoff — box-audit semgrep coverage gap (2026-08-04)

Closes the tooling gap named at the end of `design/box-scan-2026-07-24.md`:

> *"semgrep could not run — the outbound proxy blocks its rule registry
> (`semgrep.dev` 403), so deeper taint/template-injection rules did not run."*

**Does not supersede** `handoff-2026-07-27-box-audit-remediation.md`. That doc
remains the live status of the scan's findings and its scorecard stands
unchanged. This one only answers the question the scan left open because a tool
would not run: *what would semgrep have found?*

**Bottom line: nothing new.** 226 findings across the seven box repos, zero new
true positives. Everything triaged resolved to config-by-design,
allowlist-by-construction, or a control the 2026-07-27 handoff already records
as landed.

## Registry still blocked

`semgrep.dev` returns **403 Forbidden** through the egress proxy — the same
denial, eleven days on. Per the proxy's own documentation this is an
organization egress-policy denial: reported, **not** routed around.
`semgrep --validate` also fetches `p/semgrep-rule-lints` and fails identically,
so the rules used here are unvalidated by Semgrep's own linter. Scanning needs
no network.

The registry blocks semgrep's *rules*, not semgrep. Ten rules were written
locally for the two classes the scan named — taint and template injection —
plus the specific shapes B15 and B16 left latent. **Ten rules is not two
thousand.** If that host is ever unblocked, the registry pass is still worth
running; this does not retire that.

Rules: `quick-stupids/audits/taint-rules.yaml` (playground tier, not a
dependency — re-land here if this becomes recurring).

## Scope

| repo | commit |
| --- | --- |
| `willow` | `9b66937` |
| `willow-mcp` | `1c9b91a` |
| `willow-gate` | `9ef837c` |
| `jeles` | `14c265c` |
| `utety` | `8023080` |
| `nestor` | `a095722` |
| `safe-app-store` | `98f2c63` |

`semgrep 1.172.0`, Python only. Excluded: `*/tests/*`, `test_*`,
`*/_archived/*`, `node_modules`.

## The rules were proved able to fire first

All ten were run against a deliberately-bad smoke file and all ten fired before
the sweep began. That step caught a defect in the rule set itself:

```yaml
- id: sql-built-by-string-interpolation
  patterns:
    - pattern-either: [ ... $CUR.execute(f"...{$X}...", ...) ... ]
    - pattern-not: $CUR.execute(f"...", ...)      # <- cancels the rule
```

`f"..."` as a semgrep pattern matches **any** f-string, so the `pattern-not`
excluded everything the rule matched. It parsed, ran, and reported clean while
being structurally unable to fire. Without the smoke file this handoff would
report *no SQL injection found* on the authority of a dead check — the failure
class the box scan exists to catch, committed by the tool brought in to close
its gap.

**Re-verify with:** run the rules against any file containing
`cur.execute(f"SELECT {col} FROM t")`; all ten rule ids must appear before a
clean result on real code is believed.

## Results

| repo | n |  | class | n |
| --- | --- | --- | --- | --- |
| `safe-app-store` | 127 | | `taint-env-to-filesystem-path` | 103 |
| `willow-mcp` | 93 | | `sql-built-by-string-interpolation` | 75 |
| `willow` | 4 | | `html-built-from-fstring-with-variable` | 29 |
| `jeles` | 1 | | `taint-stored-value-to-http-fetch` | 16 |
| `utety` | 1 | | `full-environ-passed-to-subprocess` | 2 |
| `willow-gate` | **0** | | `subprocess-shell-true-nonliteral` | 1 |
| `nestor` | **0** | | | |

### The 75 SQL hits are the allowlist-column class, still latent

Every site sampled builds table or column names from a module constant or an
allowlist, values still parameterized: `willow-mcp` `governance_ledger.py:75,179`
(table name constant), `server.py:2224` (columns from a schema map, quoted),
`egress_authorization.py:312` (columns from `_ROW_GATE_FIELDS`). B16 called this
*"safe today, allowlist columns"*; that holds at 75 sites. The 2026-07-27 handoff
records `sql.Identifier` landing on the safe-app-store column-name sites in #101,
which is the same class handled one repo over.

### B15 and B16 — independently corroborated, already recorded closed

Both were already marked closed in the 2026-07-27 handoff. This is corroboration
from a different direction, not a discovery.

- **B15** (jeles env-var path traversal): `jeles/jeles/corpus.py` fires only on
  `_store_root()` reading `WILLOW_STORE_ROOT`, a config root. The vector B15
  named — the *collection* — is validated by `_validate_collection(collection)`
  in `_conn()`.
  **Re-verify with:** `sed -n '84,92p' jeles/jeles/corpus.py`
- **B16** (source-trail SSRF): guarded by `_fetch_host_allowed(url)`, which
  checks the scheme, requires a hostname, resolves through `getaddrinfo`, and
  fails closed on any parse or DNS error. Its docstring cites box audit B16
  directly.
  **Re-verify with:** `sed -n '285,335p' safe-app-store/apps/source-trail/sources_db.py`

### The one lead chased to the end: the `OLLAMA_HOST` seam

`nest/embed.py` and `nest/llm.py` — and their canonical originals in
`safe-app-store/libs/nest-pipeline` — reach an env-controlled `OLLAMA_HOST` via
`urlopen` with no scheme or host check. `willow-mcp/src/willow_mcp/model_egress.py`
pre-empts this in its own docstring: it names the hazard, explains the gate sits
at the tool boundary because those files are vendored byte-for-byte under a CI
drift-guard and are deliberately policy-free, and states its own residual TOCTOU
(gate-time resolution, connect-time connection).

The open question was whether that gate is *complete*, since only one of nine
`from .nest import` sites in `server.py` carries `model_egress.denial()`. It is:
`build_digest` and `build_bridge` reference `_embed` only for the string constant
`DEFAULT_EMBED_MODEL`, never `_post`, `embed_document` or `installed_models`.
`nest_scan` is the only Nest tool that computes embeddings, and it is the gated
one.

**Re-verify with:**

```sh
grep -n "_embed\." willow-mcp/src/willow_mcp/nest/digest.py \
                   willow-mcp/src/willow_mcp/nest/bridge.py
# DEFAULT_EMBED_MODEL only; any _post/embed_* call reopens this
```

## Overlap with what already exists

The 2026-07-27 handoff records source-scanner drift-guards already landed in
safe-app-store's store-ci `gates` job — no raw SOIL read (B3), no f-string schema
SQL (A6/B13), no inline vault-root (A5), no hardcoded `0.0.0.0` bind (B9). Three
of the ten rules here overlap that job's territory for safe-app-store. They are
not redundant for `willow-mcp`, `jeles`, `utety`, `nestor` or `willow-gate`,
which have no equivalent sweep — but if this becomes recurring, extending the
store-ci scanners outward is the cheaper move than standing up a second
mechanism.

## Limits

- **Ten rules, not a registry pass.** Scoped to the two named classes plus
  B15/B16's shapes.
- **Python only.** safe-app-store's JS/TS is unruled here.
- **The 29 HTML f-string hits were not individually triaged.** That rule is the
  noisiest of the ten; treat the count as unexamined, not as clean.
- **Tests and `_archived/` excluded** — anything living only there is unseen.
- **Nothing was re-attacked.** This confirms guards exist and are wired on the
  paths traced; it does not attempt to defeat them.
- **box-scan's other named gap is untouched** — ~19 safe-app-store sub-app
  dependency trees were never individually audited, and still have not been.
