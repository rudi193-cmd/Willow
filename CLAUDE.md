# Willow Project Instructions

## Free Fleet Policy — MANDATORY
Do NOT burn Claude tokens on tasks the free fleet can handle. Delegate first, orchestrate second.

### Delegation Targets
| Task | Provider | Method |
|------|----------|--------|
| Code generation | qwen2.5-coder:7b (Ollama) or Groq | `llm_router.ask(prompt)` |
| File comparison | Gemini or Ollama | `llm_router.ask(prompt)` |
| Classification/sorting | Any free provider | `llm_router.ask(prompt)` |
| Summarization | Gemini or Groq | `llm_router.ask(prompt)` |
| Image analysis | Gemini 2.5 Flash Vision | Gemini Vision API |
| Architecture/governance | Claude (you) | Direct |

### Quick Access
```python
import llm_router
llm_router.load_keys_from_json()
response = llm_router.ask("prompt", preferred_tier="free")
if response:
    print(response.content)
```

### Available Free Providers
Ollama (local), Gemini, Groq, Cerebras, SambaNova, HuggingFace

## Project Structure
- `willow.py` — Drive harvester (Atmosphere → Roots)
- `aios_loop.py` — Main loop (Harvest → Vision → Route → Govern)
- `local_api.py` — Interactive persona interface (Ollama + coherence tracking)
- `gate.py` / `state.py` / `storage.py` — Governance trinity
- `llm_router.py` — Multi-provider LLM cascade
- `coherence.py` — ΔE conversation coherence tracking
- `kart.py` — File classification (L5 narrative / L6 specs)
- `credentials.json` — Google OAuth + LLM API keys

## Governance
- Dual Commit: AI proposes, human ratifies
- All file moves validated through gate.validate()
- Audit chain in data/audit.jsonl (hash-chained, tamper-evident)
- Checksum: ΔΣ=42

## Willow Integration (MCP-Mandatory Rules)

**These rules apply to all Claude Code instances working in this repo.**

### KB Operations — Use MCP, Not Raw SQL

| Operation | Correct | Never |
|-----------|---------|-------|
| KB reads | `mcp__willow__willow_knowledge_search` | raw `SELECT` via psycopg2 |
| KB writes | `mcp__willow__willow_knowledge_ingest` | raw `INSERT` via psycopg2 |
| Store reads | `mcp__willow__store_get` / `store_list` | direct psycopg2 |
| Store writes | `mcp__willow__store_put` / `store_update` | direct psycopg2 |
| Queue work | `mcp__willow__willow_task_submit` | spawning subagents for KB writes |

Direct Postgres only for: schema inspection, connection debugging, admin ops Sean explicitly requests.

### Subagent Constraint
Subagents spawned via the Agent tool have **no MCP access**. They handle filesystem/bash work only. KB writes stay with the main instance via MCP.

### Agent Sessions
Each agent runs with `WILLOW_AGENT=<name>` env var. Aliases: `hanuman`, `ganesha`, `kart`, `gerald`, `willow`.
Bootloader reads the env var and injects the agent's `agents/<name>/AGENT_PROFILE.md` at boot.

### Archive, Don't Delete
Stale atoms → `domain='archived'`. Nothing deleted without explicit instruction from Sean.
