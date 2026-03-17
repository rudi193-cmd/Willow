"""
Server Minimal - FastAPI Dual Commit API

Endpoints:
- POST /validate (AI proposes)
- POST /approve (Human ratifies)
- POST /reject (Human rejects)
- POST /chat (Agent conversation)
- GET /health (System status)

CHECKSUM: ΔΣ=42
"""

import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent / "core"))
from core import gate, state, storage

app = FastAPI(title="AIOS Minimal API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Schemas
class ValidateRequest(BaseModel):
    mod_type: str
    target: str
    new_value: str
    reason: str

class ApproveRequest(BaseModel):
    request_id: str

class RejectRequest(BaseModel):
    request_id: str
    reason: str

class ChatRequest(BaseModel):
    message: str

# Init
gatekeeper = gate.Gatekeeper()

@app.post("/validate")
def validate_proposal(req: ValidateRequest):
    """AI proposes modification (Dual Commit - Commit 1)"""
    current_state = storage.load_state()
    
    request = state.ModificationRequest(
        mod_type=getattr(state.ModificationType, req.mod_type.upper()),
        target=req.target,
        new_value=req.new_value,
        reason=req.reason,
        authority=state.Authority.AI,
        governance_state=state.GovernanceState.PROPOSED,
        sequence=current_state.sequence + 1,
        old_value=None
    )
    
    decision, events = gatekeeper.validate(request, current_state)
    new_state = storage.apply_events(events, current_state)
    storage.save_state(new_state)
    
    return {
        "decision_type": decision.decision_type.name,
        "code": decision.code.name,
        "reason": decision.reason,
        "request_id": request.request_id,
        "approved": decision.approved,
        "requires_human": decision.requires_human
    }

@app.post("/approve")
def approve_proposal(req: ApproveRequest):
    """Human ratifies proposal (Dual Commit - Commit 2)"""
    success, new_state, error = storage.process_human_action(
        request_id=req.request_id,
        action="approve",
        reason="Human approved",
        timestamp=state.datetime.now(state.timezone.utc).isoformat()
    )
    
    if not success:
        raise HTTPException(status_code=400, detail=error)
    
    return {
        "status": "approved",
        "request_id": req.request_id,
        "new_sequence": new_state.sequence
    }

@app.post("/reject")
def reject_proposal(req: RejectRequest):
    """Human rejects proposal (Dual Commit - Commit 2)"""
    success, new_state, error = storage.process_human_action(
        request_id=req.request_id,
        action="reject",
        reason=req.reason,
        timestamp=state.datetime.now(state.timezone.utc).isoformat()
    )
    
    if not success:
        raise HTTPException(status_code=400, detail=error)
    
    return {
        "status": "rejected",
        "request_id": req.request_id,
        "reason": req.reason
    }

@app.post("/chat")
def chat(req: ChatRequest):
    """Agent conversation (placeholder)"""
    return {
        "response": f"[Willow] You said: {req.message}",
        "agent": "willow"
    }

@app.get("/health")
def health():
    """System health check"""
    current_state = storage.load_state()
    pending = storage.load_pending()
    
    return {
        "status": "ok",
        "sequence": current_state.sequence,
        "pending_count": len(pending),
        "checksum": "ΔΣ=42"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8421)
