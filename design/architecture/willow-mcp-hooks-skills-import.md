# willow-mcp — hooks & skills import from willow-2.0

**Status:** DRAFT — 2026-07-21  
**Posture:** **Option A — thin product** (agreed operator direction)  
**Companion:** [willow-mcp-flows.md](willow-mcp-flows.md) · [willow-mcp gap inventory](https://github.com/rudi193-cmd/willow-mcp/blob/master/docs/migrations/willow-2.0-gap-inventory.md) · `willow-mcp/docs/design/hooks-and-skills.md`

---

## 1. Option A — what we committed to

| Layer | Role |
|-------|------|
| **Skills** | Teach workflows. Boot = read and follow `session-start` skill text. |
| **Hooks** | Footguns only — wrong-but-easy paths agents take despite the tools existing. |
| **`session_enter`** | The runtime boot gate (first MCP call). Hooks do **not** substitute for it. |

Greenfield path:

```
pip install willow-mcp → willow-mcp-init → point MCP client → session_enter → work → handoff closeout
```

**Not the product model:** fylgja boot phases, hook-injected fleet context, Grove/JELES on SessionStart, declarative `loops.json`, or “fleet desk feels identical to willow-2.0.”

willow-2.0 fylgja remains the **fleet harness** when `WILLOW_STORE_ROOT` points at a shared fleet home. willow-mcp bundle is the **standalone product** layer.

---

## 2. Already shipped (willow-mcp bundle)

### Hooks — `src/willow_mcp/bundle/hooks/pre_tool_use.py`

| Guard | Class |
|-------|-------|
| Bash → raw `psql` / `sqlite3` against willow-mcp-owned stores | Footgun |
| `task_submit` with hand-embedded `# allow_net` / `# allow_localhost` | Footgun |
| Self-grant egress (mint lease, `grant-net`, add `task_net` to manifest) | Footgun (sudo invariant) |

### Skills — `src/willow_mcp/bundle/skills/`

| Skill | Role |
|-------|------|
| `session-start.md` | **Boot gate (draft — see §6)** |
| `kart-tasks.md` | Task queue, three-key egress, worker caveat |
| `schema-confirm.md` | `schema_confirm_mapping` human workflow |
| `willow-serve.md` | Long-running hub |
| `handoff-write.md` | Dispatch closeout |

### Personas — `bundle/personas/`

Voice seeds for willow, hanuman, loki, jeles, ada, skirnir, vishwakarma (not boot ceremony).

---

## 3. Skills — import shortlist (Option A)

Priority order for bundle additions. **Rewrite** = same intent, willow-mcp verbs only. **Port** = light edits. **Skip** = stays in willow-2.0.

| Priority | willow-2.0 source | Action | Notes |
|----------|-------------------|--------|-------|
| P0 | `mcp-first.md` + `boot.md` (steps only) | **Merge into `session-start.md`** | See §6 — open design |
| P1 | `consent.md` | **Adapt** | `config/settings.global.json`; CLI-only `grant-net`; no TTY `consent set` in sandbox |
| P1 | `worktree.md`, `worktree-enforce.md` | **Adapt** | PR-only git; **no `fork_*`** until tools port — git-only variant for greenfield |
| P2 | `shutdown.md` | **Merge into `handoff-write.md`** | Closeout checklist, not a Stop hook |
| P2 | `debugging.md`, `review.md`, `tdd.md`, `brainstorming.md` | **Port** | Generic discipline; rename fleet tools |
| P3 | `*-boot.md` (hanuman, loki, jeles, …) | **Slim overlays** | One paragraph after `session_enter`: voice + boundaries, not phase scripts |
| P3 | `external-guard.md` | **Adapt** | **Blocked on** `willow_web_search` / `willow_web_fetch` port |
| P3 | `kart.md` | **Skip** | Superseded by `kart-tasks.md`; steal Ollama/localhost notes if missing |
| — | `boot.md` (full), `startup.md`, `cold-recovery.md` | **Skip** | Replaced by `session_enter` + thin skill |
| — | `grove-*`, `fleet-*`, `dream.md`, `power.md`, `coordinator.md` | **Skip** | Fleet-only |
| — | `persistent-memory-stack`, `rlm/`, `iterative-retrieval` | **Skip** | Needs fleet KB / tools not in product core |
| — | `willow-remote`, `openclaw-discord`, `willow-deploy`, `release` | **Skip** | Ops integrations; link from charter docs if needed |
| — | `skill-steward`, `grove-persistent-monitor`, `babysit` | **Skip** | Fleet maintenance loops |

**Rule (from `hooks-and-skills.md`):** new tool with a footgun or multi-step human workflow ships hook and/or skill in the **same PR** as the tool.

---

## 4. Hooks — import shortlist (Option A)

### Keep (shipped)

See §2 — three guards in `pre_tool_use.py`.

### Add next (still footgun class)

| Source (fylgja `pre_tool.py`) | Product form | Blocker |
|-------------------------------|--------------|---------|
| `mcp_routing.BASH_TO_MCP` redirect table | Extend `pre_tool_use.py` — warn/block common Bash that duplicates MCP | None |
| Native `WebSearch` / `WebFetch` block | Same hook pattern as fleet | **`willow_web_search` / `willow_web_fetch` must ship first** |
| `@markdownai` Write → MCP write | Optional — charter `docs/` under willow repo | Decide scope (willow-mcp vs charter-only) |
| `security_scan` on Write/Edit | Optional second pass | Earn-first — MCP `_sanitize` may suffice |

### Explicitly not importing as hooks

| fylgja event | Why (Option A) |
|--------------|----------------|
| `session_start.py` | Fleet injection (hardware, Grove, JELES, anchor, corrections corpus) → use **`session_enter` return payload** + skill |
| `prompt_submit.py` | Persona picker + boot guard → skill + `session_enter` |
| `stop.py`, `shutdown.py`, `session_stop.py` | Closeout is **`session_handoff_write` / `handoff_write_v4`** in skill text |
| `post_tool.py` | Server has `receipts_tail`; add only if discipline fails without it |
| Boot phase sentinels (`willow-persona-done-*`) | Fights packet-is-boot model |
| Agent depth / subagent spawn limits | Fleet multi-window concern |
| `hook_list` / `loop_list` machinery | Dropped per gap inventory Bucket C |

---

## 5. Implementation slices

Ordered work units (each = bundle PR in `willow-mcp`, charter may link here):

| Slice | Deliverable |
|-------|-------------|
| **S0** | This doc ratified; `session-start.md` design closed (§6) |
| **S1** | Rewrite `session-start.md` + sync `skills/session-start.md` at repo root |
| **S2** | Add `consent.md`, `worktree.md` to bundle |
| **S3** | Extend `handoff-write.md` with shutdown checklist |
| **S4** | `pre_tool_use.py` — Bash→MCP redirect table (from fylgja routing, trimmed) |
| **S5** | Port `debugging` / `review` / `tdd` / `brainstorming` |
| **S6** | Slim persona overlay snippets (or pointers in `session-start`) |
| **S7** | After web tools port: native web hook + `external-guard.md` |

**Cross-repo:** tool ports (`willow_web_*`, `fork_*`) live in willow-mcp repo per [gap inventory](https://github.com/rudi193-cmd/willow-mcp/blob/master/docs/migrations/willow-2.0-gap-inventory.md); skills/hooks that depend on them wait.

---

## 6. `session-start` — open design (discussion)

**Current bundle text** (`willow-mcp/.../skills/session-start.md`) covers:

- First call: `session_enter(app_id, session_id, dispatch_id="")`
- Orchestrator (`willow`) vs specialist entry modes
- Closeout tool per mode (`session_handoff_write` vs `handoff_write_v4`)

**What fylgja `boot.md` + `mcp-first.md` added (fleet)** — for comparison only:

| Fleet behavior | willow-mcp replacement? |
|----------------|-------------------------|
| SessionStart hook injects hardware, status, corrections | **No hook** — `diagnostic_summary` in skill? |
| `boot_digest` + MCP inventory | `session_enter` return + `whoami`? |
| `handoff_latest` continuity | `handoff_read` / `kb_startup_continuity`? |
| 3-phase boot (persona → fleet → work) | **Rejected** — single `session_enter` |
| Postgres down = hard stop | Skill says check `diagnostic_summary` verdict |
| Persona picker on turn 1 | **TBD** — manifest `app_id` is fixed per MCP config |
| Parallel boot calls table | **TBD** — what must run besides `session_enter`? |

### Questions to settle (talk track)

1. **Minimum parallel calls** — Is `session_enter` alone sufficient, or does every session also require `diagnostic_summary` + `whoami` before first user-facing reply?

2. **What `session_enter` must return** — Should the skill mandate reading `assignment.md` from the tool response for dispatch mode only, or always list `entry_mode`, active `dispatch_id`, and suggested next tools?

3. **Orchestrator desk** — For `app_id=willow`, should the skill script `dispatch_list(status=pending)` immediately after enter, or only on operator request?

4. **Exposure / seed** — Does session open include `exposure_config_get` or `agent_seed_mirror` for specialists, or is that dispatch-only / earn-first?

5. **Local-first default** — Should session-start explicitly say: inference client may be cloud IDE **or** local Ollama host; either way call `session_enter` first (ties to [willow-mcp-flows.md §0](willow-mcp-flows.md))?

6. **Failure posture** — If `diagnostic_summary` is `degraded` vs `broken`, does the skill allow work, block, or branch (e.g. SOIL-only mode)? Sandbox accepts `ok` or `degraded`.

7. **Client without hooks** — Skill must stand alone for Cursor users who only wire MCP stdio and never install Claude `pre_tool_use` hook. Confirm wording: “hooks optional; skill mandatory.”

8. **Persona** — Load `personas/<role>.md` from bundle after enter, or rely on MCP config + `session_enter` only?

### Draft skeleton (not ratified)

```
1. session_enter(app_id, session_id, dispatch_id="")
2. If dispatch: read assignment from response; do not improvise scope
3. diagnostic_summary — if broken, stop and report; if degraded, note gaps
4. [TBD] whoami / dispatch_list / kb_startup_continuity
5. Work (MCP tools only for fleet stores — see mcp-first doctrine, rewritten)
6. Close: session_handoff_write | handoff_write_v4 per entry_mode
```

---

## 7. References

| Artifact | Location |
|----------|----------|
| fylgja skills (source) | `willow-2.0/willow/fylgja/skills/` |
| fylgja hooks (source) | `willow-2.0/willow/fylgja/events/` |
| Product bundle | `willow-mcp/src/willow_mcp/bundle/` |
| Hooks & skills design rule | `willow-mcp/docs/design/hooks-and-skills.md` |
| Session lifecycle (packet = boot) | `willow-mcp/docs/design/session-lifecycle.md` |
| Deliberately dropped tools | gap inventory §4 (Bucket C) |

---

*Next step: close §6 questions, then implement S1 in willow-mcp bundle.*
