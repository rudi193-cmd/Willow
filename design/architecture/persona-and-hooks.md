# Persona vs hooks — what exists today (and what we did not ratify here)

**Status:** DRAFT — factual inventory + open question  
**Date:** 2026-08-06  
**Operator note:** Sean is **not sure** the “persona is never hook-specific” posture is right long term. This doc records the **as-built** split so we can argue from evidence, not memory.

**Companion:** [willow-mcp-hooks-skills-import.md](willow-mcp-hooks-skills-import.md) · willow-mcp `docs/design/pgp-and-persona.md` (LOCKED 2026-07-09) · charter decommission plan §1h (fylgja off charter seat)

---

## 1. Short answer

There are **no persona-specific hook programs** in the wired stacks — no separate Cursor/Claude hook command per persona (no “Ada hook” vs “Loki hook”). Hook entrypoints are **shared**; persona is applied via **context injection**, **skills**, and **markdown boot files**, not via distinct hook binaries in `hooks.json`.

That is **current behavior**, not necessarily **desired end state**.

---

## 2. willow-mcp (product hooks)

| Hook / path | Persona-specific? | How voice enters |
|-------------|-------------------|------------------|
| `session_start_hook` | No | Calls `session_enter` → `persona_context(app_id)` from specialist registry (`specialists.json`, `$WILLOW_HOME/personas/*.md`) |
| `pre_tool_hook` / `pre_tool_use.py` | No | MCP-first and policy guards; same for every `app_id` |
| `session_stop_hook` | No | Stack snapshot on SessionEnd |
| `dispatch_reconcile_hook` (planned, **4C64E7DD**) | No | Pending packet delivery; orchestrator seat skipped |

**Dispatch:** packet `meta.json` may carry `persona`, `role`, `persona_voice` — injected on specialist `session_enter` in **dispatch** mode (silent; no menu). See willow-mcp `dispatch.py` + `registry.persona_context`.

**Skills:** `persona-overlays.md` — voice and boundaries **after** `session_enter`; not a hook.

**Product design (locked elsewhere):** interactive persona **picker** is **not** willow-mcp core; charter orchestrator may use a **host** hook (historically fylgja). See willow-mcp `docs/design/pgp-and-persona.md` §2.

---

## 3. fylgja (fleet harness — still on some charter IDE configs)

Charter `.cursor/hooks.json` may still point at a **single** binary for all events:

`willow-2.0/willow/fylgja/bin/fleet-fylgja-hook cursor {session_start|prompt_submit|pre_tool|stop}`

Persona is **not** implemented as separate hook commands. It is:

| Mechanism | Persona-specific? | Role |
|-----------|-------------------|------|
| `session_start` / `prompt_submit` | No (one hook) | Injects **picker**; writes / checks `willow-persona-done-{agent}-{session}` sentinel |
| `pre_tool` boot gate | No (one hook) | **Phase 1:** block MCP/edits until persona sentinel exists; allow reads of boot/persona skill paths |
| `willow/fylgja/skills/{persona}-boot.md` | **Yes (content)** | e.g. `ada-boot.md`, `loki-boot.md`, `hanuman-boot.md` — agent reads after pick; **not** a second hook in `hooks.json` |
| `persona.py` anchor lines | No (one code path) | Injected banner after selection |

Fleet identity remains **`app_id` / `WILLOW_AGENT_NAME`** (e.g. `willow`, `hanuman`, `loki`). Persona does not retarget MCP `app_id`, Grove sender, or SOIL namespace.

**Decommission direction (§1h):** charter seat targets **willow-mcp hooks only** — fylgja persona picker and boot sentinels are explicitly **not** imported as product hooks (see hooks-skills-import §4 “Boot phase sentinels”).

---

## 4. What “persona-specific hooks” could mean (unsettled)

If we wanted hooks that **vary by persona**, we have not defined or built any of these. Candidates for future debate:

1. **Per-persona hook commands** in IDE config (different `command` per roster entry) — highest blast radius; config explosion.
2. **One hook, persona branch inside** (read active persona from sentinel / env; run different subprocess or inject different `additional_context`) — still one `hooks.json` line, behavior differs by persona.
3. **Persona as skill-only** (current willow-mcp lean) — voice in markdown; hooks stay agent-neutral.
4. **Persona-specific PreToolUse matchers** (e.g. stricter guards for “accountant” persona) — policy overlay without new binaries.

None of these are ratified on the charter seat. Option A in hooks-skills-import treats persona picker + boot sentinels as **out of product hooks**.

---

## 5. Open question (operator dissent)

**Claim on the bench (2026-08-06):** “Persona-specific behavior is boot markdown + registry text + optional dispatch fields, not persona-specific hook implementations.”

**Operator position:** **may disagree** — worth revisiting whether some personas need **hook-enforced** posture (tool allow/deny, injection, or boot gates) that cannot be trusted to skills and model compliance alone.

**If we revisit, decide explicitly:**

- Charter orchestrator only vs all specialist seats
- Picker vs silent persona on dispatch
- Whether fylgja’s persona-phase `pre_tool` gate should **survive** in thin form on willow-mcp (contradicts current Option A table)
- Whether `{persona}-boot.md` should become hook-driven injection instead of agent-read

Until then: **document as-built** (this file), **do not** assume the no-per-persona-hooks model is final law.

---

## 6. References

| Artifact | Location |
|----------|----------|
| LOCKED persona / PGP | `willow-mcp/docs/design/pgp-and-persona.md` |
| Option A — hooks not importing persona picker | `design/architecture/willow-mcp-hooks-skills-import.md` §4 |
| fylgja persona boot skills | `willow-2.0/willow/fylgja/skills/*-boot.md` |
| fylgja persona pre_tool phase | `willow-2.0/willow/fylgja/events/pre_tool.py` |
| Specialist registry | `willow-mcp/src/willow_mcp/bundle/config/specialists.json` |
