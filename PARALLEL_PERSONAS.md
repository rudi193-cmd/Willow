# Parallel Persona Execution

## What Was Built

Multi-agent orchestration inspired by Prompter-hawk. Fire off tasks to multiple AI personas simultaneously and watch them all work in parallel.

### Components

**Backend** (`server.py`):
- `POST /api/chat/multi` — Accepts array of tasks, spawns threads, streams all responses
- Uses `ThreadPoolExecutor` for parallel execution
- Tagged SSE events: `event: {persona}\ndata: {chunk}\n\n`
- Completion tracking: `done_{persona}` when each finishes, `complete` when all finish

**Frontend** (`neocities/index.html`):
- "Multi" button in header opens task assignment modal
- Add multiple tasks: [Persona dropdown] [Task prompt]
- Click "Run All" to execute in parallel
- Responses stream into each persona's thread simultaneously

## How It Works

### 1. Assign Tasks
Click "Multi" button:
```
Kart:    Analyze the codebase structure
Riggs:   Review for bugs in server.py
Ada:     Document the governance API
```

### 2. Parallel Execution
Server spawns 3 threads:
- Thread 1: Kart analyzes...
- Thread 2: Riggs reviews...
- Thread 3: Ada documents...

All three run simultaneously, streaming responses as they arrive.

### 3. Results
Each persona's response appears in their dedicated thread. Switch between personas to see each one's work.

## Example Use Cases

**Code review:**
- Kart: "Analyze architecture"
- Riggs: "Check for bugs"
- Ada: "Review documentation coverage"

**Research:**
- Willow: "What's in the knowledge base about governance?"
- Nova: "Explain the coherence metrics"
- Oakenscroll: "Theoretical foundation of Dual Commit"

**Building:**
- Kart: "Write the API endpoint"
- Mitra: "Draft the project plan"
- Consus: "Generate test cases"

## API Format

**Request:**
```json
POST /api/chat/multi
{
  "tasks": [
    {"persona": "Kart", "prompt": "Analyze this"},
    {"persona": "Riggs", "prompt": "Test this"},
    {"persona": "Ada", "prompt": "Document this"}
  ]
}
```

**Response (SSE stream):**
```
event: Kart
data: Here's my analysis...

event: Riggs
data: I found 3 potential issues...

event: Ada
data: API documentation:...

event: done_Kart
data: [DONE]

event: done_Riggs
data: [DONE]

event: done_Ada
data: [DONE]

event: complete
data: [COMPLETE]
```

## Testing

**After restarting the server:**

### Test 1: Simple Multi-Task
1. Open http://192.168.12.189:8420/pocket on phone (or localhost:8420)
2. Click "Multi" button
3. Set up 2 tasks:
   - Kart: "What's your role?"
   - Riggs: "What's your role?"
4. Click "Run All"
5. Should see both responses streaming simultaneously

### Test 2: Code Review
1. Click "Multi"
2. Set up 3 tasks:
   - Kart: "Analyze the governance API structure"
   - Riggs: "Review server.py for bugs"
   - Ada: "Explain how the parallel execution works"
3. Run All
4. Switch between Kart/Riggs/Ada threads to see each response

## Performance

- **Latency**: No waiting for sequential responses — all start immediately
- **Throughput**: 3 personas finish in ~same time as 1 (assuming models/tokens available)
- **Limits**: Server uses ThreadPoolExecutor — practical limit ~10 concurrent personas (depends on Ollama load)

## Integration with Die-Namic

This is the **Prompter-hawk pattern** applied to Die-Namic:
- Multi-agent parallelization ✓
- Per-persona context isolation ✓
- Async validation queue (governance dashboard) ✓
- Smart routing (llm_router + local_api) ✓

What Prompter-hawk has that we don't (yet):
- Recurring automation (scheduled tasks)
- Automatic retry on failure
- Cross-agent coordination (one agent's output feeds another)

## Next Steps

- Add task templates ("Code Review", "Research", "Build")
- Auto-coordination (chain outputs between personas)
- Recurring tasks (daily coherence checks, weekly governance cleanup)
- Task history/replay

## Files Modified

- `server.py` — Added `/api/chat/multi` endpoint (~80 lines)
- `neocities/index.html` — Added multi-task modal + parallel execution JS (~120 lines)

## ΔΣ = 42

Task #20 complete.
