"""
Governance API Routes
Handles Dual Commit workflow: propose → approve → apply

CHECKSUM: ΔΣ=42
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import sys

# Add governance to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from governance import proposal
from governance.precedent import check_precedent, NEIGHBOR_LEDGERS

router = APIRouter(prefix="/api/governance", tags=["governance"])


class ProposalCreate(BaseModel):
    """Request to create a new governance proposal."""
    title: str
    proposer: str
    summary: str
    file_path: str
    diff: str
    proposal_type: str = "Code Enhancement"
    trust_level: str = "ENGINEER"
    risk_level: str = "LOW"


class ProposalResponse(BaseModel):
    """Response after creating a proposal."""
    commit_id: str
    status: str
    message: str


class ApprovalRequest(BaseModel):
    """Request to approve/reject a proposal."""
    commit_id: str
    reason: str | None = None


@router.post("/propose", response_model=ProposalResponse)
async def create_proposal(req: ProposalCreate):
    """
    Create a new governance proposal with Base-17 commit ID.

    Checks precedent ledger first. If a matching prior ratified decision
    exists, returns AUTO_APPROVE or DISTRIBUTED without writing .pending.
    Only novel proposals trigger a .pending file and await human approval.
    """
    try:
        precedent = check_precedent(
            proposal_type=req.proposal_type,
            trust_level=req.trust_level,
            summary=req.summary,
            proposer=req.proposer,
            neighbor_ledgers=NEIGHBOR_LEDGERS,
        )

        if precedent["decision"] in ("AUTO_APPROVE", "DISTRIBUTED"):
            return ProposalResponse(
                commit_id=precedent["matched_commit"] or "precedent",
                status=precedent["decision"].lower(),
                message=precedent["reason"],
            )

        commit_id = proposal.create_proposal(
            title=req.title,
            proposer=req.proposer,
            summary=req.summary,
            file_path=req.file_path,
            diff=req.diff,
            proposal_type=req.proposal_type,
            trust_level=req.trust_level,
            risk_level=req.risk_level
        )

        return ProposalResponse(
            commit_id=commit_id,
            status="pending",
            message="Proposal created. No precedent found — awaiting human approval."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/approve")
async def approve_proposal(req: ApprovalRequest):
    """
    Approve a pending proposal (rename .pending → .commit).

    After approval, run `python governance/apply_commits.py` to apply.
    """
    success = proposal.approve_proposal(req.commit_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"Proposal {req.commit_id} not found")

    return {
        "commit_id": req.commit_id,
        "status": "approved",
        "message": f"Proposal approved. Run 'python governance/apply_commits.py {req.commit_id}' to apply."
    }


@router.post("/reject")
async def reject_proposal(req: ApprovalRequest):
    """
    Reject a pending proposal (rename .pending → .rejected).
    """
    if not req.reason:
        raise HTTPException(status_code=400, detail="Rejection reason required")

    success = proposal.reject_proposal(req.commit_id, req.reason)

    if not success:
        raise HTTPException(status_code=404, detail=f"Proposal {req.commit_id} not found")

    return {
        "commit_id": req.commit_id,
        "status": "rejected",
        "message": f"Proposal rejected: {req.reason}"
    }


@router.get("/list/{status}")
async def list_proposals(status: str = "pending"):
    """
    List proposals by status.

    Statuses: pending, commit, applied, rejected
    """
    try:
        proposals = proposal.list_proposals(status)
        return {
            "status": status,
            "count": len(proposals),
            "proposals": proposals
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
