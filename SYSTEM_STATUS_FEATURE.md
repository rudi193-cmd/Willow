# System Status Feature

## What Was Added

### 1. New API Endpoint: `/api/system/status`
Returns comprehensive system health metrics in JSON format:

```json
{
  "ollama": {"running": bool, "models": [str]},
  "server": {"uptime_seconds": int, "port": 8420},
  "governance": {"pending_commits": int, "last_ratification": str},
  "intake": {"dump": int, "hold": int, "process": int, "route": int, "clear": int},
  "engine": {"running": bool},
  "tunnel": {"url": str, "reachable": bool}
}
```

### 2. Chat Integration (Willow Persona Only)
When talking to Willow, you can now ask:
- "How's the system?"
- "System status report"
- "Check system health"
- "Are you running?"
- etc.

Willow will automatically call `/api/system/status` and format a human-readable report.

## Testing

**After restarting the server** (close and reopen WILLOW.bat):

### Test 1: Direct API Call
```bash
curl http://127.0.0.1:8420/api/system/status | python -m json.tool
```

### Test 2: Chat Query (Desktop)
1. Open http://127.0.0.1:8420
2. Select "Willow" persona
3. Type: "how's the system?"
4. Should receive formatted status report

### Test 3: Mobile (/pocket)
1. Open http://192.168.12.189:8420/pocket on phone
2. Select "Willow" persona
3. Ask: "system status"
4. Should stream back formatted report

## Example Output

```
System Status Report:

✓ Ollama: Running (3 models: llama3.2, qwen2.5-coder:7b, kart)
✓ Server: Running for 45 minutes (port 8420)
✓ Governance: No pending commits
  Last ratification: 2026-02-06T10:30:15
✓ Intake: Pipeline clear
✓ Engine: Kart loop active
✓ Tunnel: https://bird-str-fruit-butter.trycloudflare.com (reachable)
```

## Files Modified

- `server.py` — Added `/api/system/status` endpoint, imported `httpx`, `psutil`, `datetime`
- `local_api.py` — Added `_check_system_status_query()` helper, integrated into `process_smart_stream()`

## Dependencies

New imports (already in use elsewhere):
- `httpx` (async HTTP client)
- `psutil` (process monitoring)

## Next Steps

Task #18 complete. Remaining tasks:
- #19: Build async governance dashboard
- #20: Add parallel persona execution
- #21: Restyle /pocket CSS theme
