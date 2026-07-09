# Willow — SAFE Beta (Friends & Family)

> A dual-commit AI governance system for collaborative knowledge management and task orchestration.

## Overview

Willow is an experimental framework for human-AI collaboration built on **dual-commit governance**: AI proposes actions, humans ratify them. The system integrates multi-provider LLM orchestration, knowledge base management, and tamper-evident audit trails to enable trustworthy autonomous workflows.

**Status:** Beta (Friends & Family release)

## Architecture

```
┌─────────────────────────────────────────────────┐
│           AIOS Main Loop (aios_loop.py)          │
│    Harvest → Vision → Route → Govern             │
└─────────────────────────────────────────────────┘
          ↓              ↓              ↓
    ┌─────────┐   ┌──────────┐   ┌──────────┐
    │ Willow  │   │ Local    │   │ Gate /   │
    │ Harvester   │ API      │   │ State /  │
    │ (Drive→    │ (Ollama  │   │ Storage  │
    │  Roots)    │  Persona)│   │(Govern)  │
    └─────────┘   └──────────┘   └──────────┘
           ↓              ↓              ↓
    ┌──────────────────────────────────────────┐
    │     LLM Router (Multi-Provider)          │
    │ Ollama | Gemini | Groq | Cerebras | ...  │
    └──────────────────────────────────────────┘
           ↓
    ┌──────────────────────────────────────────┐
    │  Knowledge Base + Audit Trail (MCP)      │
    │  Postgres: KB reads/writes via MCP only   │
    └──────────────────────────────────────────┘
```

### Core Modules

| Module | Purpose | Key Exports |
|--------|---------|-------------|
| **willow.py** | Drive harvester | Atmosphere → Roots file collection |
| **aios_loop.py** | Main orchestrator | Harvest, Vision, Route, Govern cycle |
| **local_api.py** | Interactive persona | Ollama + coherence tracking |
| **llm_router.py** | Multi-provider LLM cascade | `ask()` with fallback strategy |
| **coherence.py** | Conversation coherence | ΔE color-space similarity tracking |
| **kart.py** | File classification | L5 narrative / L6 specifications |
| **gate.py** | Action validator | Dual-commit proposal/ratify |
| **state.py** | Session state | Workspace metadata & context |
| **storage.py** | Data persistence | Vault, archive, audit chain |

## Governance Model

### Dual Commit (Proposal → Ratification)

1. **AI Proposes** → `gate.propose(action)`
   - Validates preconditions
   - Generates human-readable summary
   - Returns `ProposalId`

2. **Human Reviews** → `gate.ratify(proposal_id)`
   - Inspects proposal details
   - Approves or rejects
   - Triggers execution or rollback

3. **Audit Trail** → `data/audit.jsonl`
   - Hash-chained records
   - Tamper-evident (ΔΣ = 42)
   - Full decision history

### MCP-Mandatory Rules

All knowledge base and store operations **must use MCP clients**, never raw Postgres:

```python
# ✅ Correct
response = mcp__willow__willow_knowledge_search(query="...")
mcp__willow__willow_knowledge_ingest(atoms=[...])

# ❌ Never do this
cursor.execute("SELECT * FROM knowledge_base")
```

**Subagent constraint:** Agents spawned via the Agent tool have no MCP access—they handle filesystem/bash only. KB writes remain with the main instance.

## Free Fleet Policy

Willow delegates non-critical work to free LLM providers to conserve Claude tokens:

| Task | Provider | Method |
|------|----------|--------|
| Code generation | qwen2.5-coder:7b (Ollama) or Groq | `llm_router.ask(prompt)` |
| File comparison | Gemini or Ollama | `llm_router.ask(prompt)` |
| Classification/sorting | Any free provider | `llm_router.ask(prompt)` |
| Summarization | Gemini or Groq | `llm_router.ask(prompt)` |
| Image analysis | Gemini 2.5 Flash Vision | Gemini Vision API |
| Architecture/governance | Claude | Direct |

### Quick Router Usage

```python
import llm_router

llm_router.load_keys_from_json()
response = llm_router.ask("Classify these files", preferred_tier="free")
if response:
    print(response.content)
```

## Agent System

Agents run with `WILLOW_AGENT=<name>` environment variable. Bootloader injects agent profiles:

```
agents/<name>/AGENT_PROFILE.md  # Loaded at startup
```

**Named Agents:** `hanuman`, `ganesha`, `kart`, `gerald`, `willow`

## Setup

### Prerequisites
- Python 3.8+
- PostgreSQL (with Willow schema)
- Google OAuth credentials (`credentials.json`)
- LLM provider API keys (Gemini, Groq, Cerebras, etc.)

### Installation

```bash
git clone https://github.com/rudi193-cmd/Willow.git
cd Willow
pip install -r requirements.txt
```

### Configuration

1. **Store credentials** in `credentials.json`:
   ```json
   {
     "google_oauth": { "... ": "..." },
     "gemini_api_key": "...",
     "groq_api_key": "...",
     "ollama_base_url": "http://localhost:11434"
   }
   ```

2. **Initialize Postgres**:
   ```bash
   psql -f schema.sql
   ```

3. **Start Ollama** (if using local provider):
   ```bash
   ollama serve
   ```

### Running

```bash
# Start main loop
python aios_loop.py

# Start interactive persona
python local_api.py

# Harvest Drive files
python willow.py --harvest
```

## Archive, Don't Delete

Stale atoms → `domain='archived'`. Nothing deleted without explicit instruction. All changes flow through dual-commit governance.

## Language Composition

- **Python** (73.7%) — Core orchestration & governance
- **HTML** (13.3%) — Persona UI
- **Makefile** (7.9%) — Build & deployment
- **JavaScript** (2.5%) — Frontend interactivity
- **PLpgSQL** (1%) — Postgres schema & triggers
- **Batchfile** (0.6%) — Windows scripting
- **Other** (1%)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Submit a pull request
4. Await dual-commit ratification

## License

Beta release — Terms to follow.

## Contact

For questions or collaboration inquiries, reach out to the team.

---

**Checksum:** ΔΣ = 42  
**Last Updated:** 2026-07-09
