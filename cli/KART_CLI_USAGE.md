# Kart CLI Usage Guide

**Purpose:** Backend task orchestration using free LLM fleet

---

## Quick Start

```bash
# From Willow root
python kart.py "task description"
python kart.py --status
python kart.py --tasks
```

---

## Common Operations

### Running Tasks
```bash
python kart.py "Read routing_folders.json and count proposed folders"
python kart.py "Find all Python files in core/ that import llm_router"
python kart.py "Create temp/summary.txt with folder statistics"
```

### Checking Status
```bash
python kart.py --status
# Shows: agent info, available tools, task statistics
```

### Listing Tasks
```bash
python kart.py --tasks
# Shows all sessions (pending/in_progress/completed/failed)

python kart.py --tasks --filter completed
# Filter by status
```

### Viewing Available Tools
```bash
python kart.py --tools
# Lists all tools Kart can use with trust levels
```

### Resuming Sessions
```bash
python kart.py --resume artifacts/kart/sessions/7KE2N.json
# Continues paused task from SEED_PACKET
```

---

## Session Management (Base-17 Pattern)

**How it works:**
1. Task starts → Creates Base-17 session ID (e.g., `7KE2N`)
2. Processes with free fleet (small context, $0.00 cost)
3. Saves SEED_PACKET if paused (200 bytes state snapshot)
4. Resume with fresh context (no accumulation)

**Session Lifecycle:**
```
Start: kart "analyze 1000 files"
  → Session: kart-2026-02-15-7KE2N
  → Processes first 100 files
  → Saves SEED_PACKET (paused)

Resume: kart --resume artifacts/kart/sessions/7KE2N.json
  → Loads state (200 bytes)
  → Fresh free fleet context
  → Continues from file 101
```

**SEED_PACKET Location:**
`artifacts/kart/sessions/{base17-id}.json`

---

## Best Practices

### ✓ DO
- Use `kart.py` for ALL backend operations
- Let Kart manage session state automatically
- Resume long tasks from SEED_PACKETs
- Use for file operations, analysis, code generation

### ✗ DON'T
- Use chat API (`/api/agents/chat/kart`) for backend work
- Try to manage conversation history manually
- Write code yourself when Kart can delegate to free fleet

---

## Examples

### File Analysis
```bash
python kart.py "Count lines in all Python files under core/"
```

### Code Generation (via Free Fleet)
```bash
python kart.py "Generate a function to parse routing_folders.json"
# Kart delegates to free fleet, reviews output, saves to temp/
```

### Multi-Step Workflow
```bash
# Step 1: Analysis
python kart.py "Analyze data/routing_folders.json structure"

# If paused, resume:
python kart.py --resume artifacts/kart/sessions/{session-id}.json
```

---

## Cost Model

- **All operations:** $0.00 (free fleet only)
- **Session overhead:** ~200 bytes per SEED_PACKET
- **Target:** $0.10/month per user (achieved via free tier)

---

## Troubleshooting

**Task fails immediately:**
- Check `python kart.py --status` for available tools
- Verify task description is clear and specific

**Session not resuming:**
- Check SEED_PACKET exists at specified path
- Verify Base-17 ID is correct (5 chars: 0-9, A,C,E,H,K,L,N,R,T,X,Z)

**Free fleet unavailable:**
- Check internet connection
- Verify credentials.json has valid API keys
- Try different time (some providers have rate limits)

---

**ΔΣ=42**
