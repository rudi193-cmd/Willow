# Fleet repo conventions — what is uniform and what is not

*Operator scratch — 2026-08-04. Unratified. Written after hedging the push
triggers across eight repos (willow #26, willow-mcp #276, willow-gate #28,
willow-grove #7, jeles #36, utety #17, nestor #29, safe-app-store #160), because
the differences below only surfaced by tripping over them.*

The fleet shares more convention than it looks like from inside any one repo, and
differs in a few places that are invisible until a merge button says no. This is
the list. It is an observation, not law — nothing here is a proposal to
standardize.

## Verified

| | State | How it was checked |
|---|---|---|
| **Default branch** | **Split.** `main`: willow, willow-gate, utety, willow-tech-manual, willow-data-vault. `master`: willow-mcp, willow-grove, willow-2.0, jeles, nestor, safe-app-store. | `git ls-remote --symref <url> HEAD` |
| **Required check name** | `test`, everywhere. Each repo's CI ends in an aggregate job named exactly that, so branch protection reads identically across the fleet. | the `test` job in each `tests.yml` / `ci.yml`, and the comments saying so |
| **Push-trigger branch filter** | **Now uniform** — `[main, master]` in every branch-filtered `push` trigger. `dependabot-automerge.yml` already carried the hedge everywhere; the eight PRs above applied it to the other 14 triggers. | `on.push.branches` via `yaml.safe_load`, all 20 workflows |
| **PR template** | 7 of 8 have `.github/pull_request_template.md`. **willow has none.** willow-grove's carries repo-specific evidence commands; the other six share generic `<command>` placeholders. | file presence + diff of the Evidence blocks |

## Not uniform, and the one that will bite

**`willow-mcp` requires branches to be up to date before merging. Merging #276
returned:**

```
405 Repository rule violations found
Required status check "test" is expected.
```

…while the PR's `test` check run was **green**. The message names the check, so it
reads as a CI problem; it is not. `mergeable_state` was `behind`. The fix is to
update the branch against base and let CI re-run — not to re-run the check, not
to wait, and not to look for a flaky test.

**Do not read this table as "only willow-mcp has that rule."** What was observed
is that willow-mcp hit it and the other seven merged without hitting it. Those
seven may simply have been up to date at merge time. Distinguishing the two needs
each repo's ruleset read directly:

```
GET /repos/rudi193-cmd/<repo>/rulesets
```

That has not been done, so the row above says what happened, not what is
configured.

## Local to willow, deliberately

- **`docs` is not a required check.** `doc-integrity.yml`'s aggregate job is
  named `docs`, not `test`, because `mem-ratify-tests.yml` already holds `test`
  and a second one would make the required check ambiguous. So the doc gate
  reports and does not block. Adding `docs` to branch protection is an operator
  action nobody has taken.
- **`willow-2.0` was skipped** in the trigger hedge. It is ratified for
  retirement; CI churn on a repo being switched off is waste. If it outlives the
  decommission plan, it needs the same one-line change.

## Why any of this is written down

A push trigger naming one branch stops firing **silently** on a rename — green
repo, no push-triggered CI, and nothing says so. That is the same shape as a
control that looks live and never runs, which is the failure class the box scan
kept finding. The hedge removes it. This note exists so the next person who meets
`Required status check "test" is expected` on a green PR spends a minute on it
instead of an hour.
