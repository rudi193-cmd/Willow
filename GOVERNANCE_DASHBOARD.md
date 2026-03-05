# Governance Dashboard

## What Was Built

A full Dual Commit governance dashboard for reviewing and ratifying AI proposals.

### Components

**Backend APIs** (`server.py`):
- `GET /api/governance/pending` — List pending commits
- `GET /api/governance/history` — List ratified/rejected commits
- `GET /api/governance/diff/{commit_id}` — View commit contents
- `POST /api/governance/approve` — Ratify a pending commit
- `POST /api/governance/reject` — Reject a pending commit with reason

**Frontend** (`governance/dashboard.html`):
- Pending commits table with review buttons
- History log showing approved/rejected commits
- Modal diff viewer for reviewing proposals
- Approve/Reject actions with confirmation
- Rejection reason prompt

**File Structure**:
```
governance/
├── commits/
│   ├── *.pending   ← AI proposed, awaiting ratification
│   ├── *.commit    ← Approved by human
│   └── *.reject    ← Rejected with reason
└── dashboard.html  ← UI
```

## How It Works

### 1. AI Proposes
Any AI agent (Willow, Kart, etc.) creates a `.pending` file:
```
governance/commits/proposal_2026-02-06_config-change.pending
```

### 2. Human Reviews
You open http://127.0.0.1:8420/governance and see:
- All pending commits
- Click "Review" to see full diff
- Click "Approve" or "Reject"

### 3. Ratification
- **Approve**: `.pending` → `.commit` (proposal accepted)
- **Reject**: `.pending` → `.reject` with appended reason (proposal denied)

## Testing

**After restarting the server**:

### Test 1: View Dashboard
```
http://127.0.0.1:8420/governance
```
Should show 1 test pending commit.

### Test 2: Review Commit
1. Click "Review" on the test commit
2. Modal opens showing full proposal
3. Should see configuration change details

### Test 3: Approve
1. Click "Approve" in modal
2. Confirm the action
3. Commit moves to History as "approved"

### Test 4: Reject (Create Another Test Commit First)
1. Create a new `.pending` file in `governance/commits/`
2. Refresh dashboard
3. Click "Review" → "Reject"
4. Enter rejection reason
5. Commit moves to History as "rejected"

## Example Governance Flow

```
┌─────────────┐
│  Kart AI    │ Proposes: "Add new routing rule for .jsonl files"
└──────┬──────┘
       │ Creates: kart_routing_2026-02-06.pending
       ▼
┌─────────────┐
│ Dashboard   │ You review: Shows full proposal with reasoning
└──────┬──────┘
       │ Decision: Approve or Reject
       ▼
┌─────────────┐
│  File       │ → kart_routing_2026-02-06.commit (if approved)
│  System     │ → kart_routing_2026-02-06.reject (if rejected)
└─────────────┘
```

## Integration with Die-Namic System

This is a **lightweight Windows-compatible** governance layer. The canonical Gatekeeper lives in `die-namic-system/governance/` but uses Unix-only `fcntl` locking.

**Sync strategy**:
- Willow creates commits locally in `governance/commits/`
- Periodically sync to `die-namic-system` via git
- Die-namic's Gatekeeper is the source of truth for complex multi-instance scenarios
- Willow's dashboard is for local-first single-user governance

## Security

**Current**: No authentication (localhost-only).

**Planned**: Admin key in config modal that validates against env var or credentials.json.

## Next Steps

- Add admin authentication
- Wire AI agents to actually create proposals (currently manual test file only)
- Add git sync to die-namic-system repo
- History pagination (currently limited to 50)

## Files Modified/Created

- `server.py` — Added 5 governance endpoints + dashboard route
- `governance/dashboard.html` — Full UI (330 lines)
- `governance/commits/test_2026-02-06_proposal.pending` — Test commit

## ΔΣ = 42

Task #19 complete.
