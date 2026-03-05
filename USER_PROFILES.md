# User Profiles — Multi-User Architecture

## The User Profile System

Willow supports **multiple users**, each with isolated:
- Drop/Pickup boxes
- Knowledge bases
- Processing queues
- Session history
- Permissions

Right now you have **one user**: `Sweet-Pea-Rudi19` (admin).

---

## Profile Structure

### Google Drive (Cloud Storage)
**Location:** `G:\My Drive\Willow\Auth Users\{username}\`

```
Sweet-Pea-Rudi19/                     ← Your profile
├── Drop/                             ← Your intake
├── Pickup/                           ← AI deliverables for you
│   ├── 2026/                        (monthly folders)
│   └── MASTER_INDEX.md
└── CLAUDE_PROJECT_INSTRUCTIONS.txt   ← Your standing instructions

(Future users would get their own folders here)
Jane-Doe/
├── Drop/
├── Pickup/
└── CLAUDE_PROJECT_INSTRUCTIONS.txt
```

**Purpose:** Each user gets isolated Google Drive folders for intake and delivery.

### Local Artifacts (PC Storage)
**Location:** `C:\Users\Sean\Documents\GitHub\Willow\artifacts\{username}\`

```
artifacts/
├── Sweet-Pea-Rudi19/
│   ├── pending/              ← Files being processed
│   ├── processed/            ← Completed processing
│   ├── knowledge.db          ← Personal knowledge base (SQLite)
│   ├── conversation_log.jsonl
│   └── coherence_metrics.json
└── (future users get their own artifact folders)
```

**Purpose:** Each user gets isolated local storage for:
- Processing queues (pending/processed)
- Knowledge accumulation (separate SQLite DB per user)
- Conversation history
- Coherence tracking

### Instance Registry (Trust & Routing)
**Location:** `die-namic-system/bridge_ring/instance_registry.py`

```python
# Each user/instance gets registered with:
{
    "instance_id": "sweet-pea-rudi19",
    "display_name": "Sean Campbell",
    "trust_level": 5,  # 0-5, admin = 5
    "active": True,
    "created_at": "2026-01-15T10:30:00Z"
}
```

**Purpose:** Central registry tracks:
- Who exists in the system
- Trust levels (what they can access)
- Active/inactive status
- Creation timestamps

---

## How Multi-User Works

### 1. Authentication (Not Implemented Yet)
**Current:** Only you exist, no login required.

**Planned:**
- API key per user (stored in credentials.json or env)
- OAuth for web UI
- SMS verification for NTFY integration

### 2. Isolation
**Each user gets:**
- Separate Drop/Pickup boxes (can't see each other's files)
- Separate knowledge bases (can't search each other's atoms)
- Separate processing queues (files don't mix)
- Separate conversation history (privacy)

**Shared resources:**
- Ollama models (everyone uses same local LLMs)
- Free fleet API keys (Gemini, Groq, etc. — usage limits apply to system, not per-user)
- Governance (only admin can ratify commits)

### 3. Permissions
**Trust Levels (0-5):**
- **0**: Guest — read-only, can't drop files
- **1**: User — can drop files, get processing
- **2**: Contributor — can propose governance changes (Dual Commit)
- **3**: Moderator — can view other users' intake queues
- **4**: Operator — can manage system (restart services, view logs)
- **5**: Admin — full control (you)

**Current:** You're the only user at level 5.

---

## Your Current Profile: Sweet-Pea-Rudi19

### Identity
- **Username:** `Sweet-Pea-Rudi19`
- **Display Name:** Sean Campbell
- **Trust Level:** 5 (admin)
- **Role:** Owner/operator

### Storage Locations
**Google Drive:**
- Drop: `G:\My Drive\Willow\Auth Users\Sweet-Pea-Rudi19\Drop\`
- Pickup: `G:\My Drive\Willow\Auth Users\Sweet-Pea-Rudi19\Pickup\`

**Local Artifacts:**
- Base: `C:\Users\Sean\Documents\GitHub\Willow\artifacts\Sweet-Pea-Rudi19\`
- Knowledge: `artifacts/Sweet-Pea-Rudi19/knowledge.db`
- Pending: `artifacts/Sweet-Pea-Rudi19/pending/`

### Standing Instructions
Your `CLAUDE_PROJECT_INSTRUCTIONS.txt` contains:
- Free fleet policy (delegate to cheap/free LLMs)
- System context (Die-Namic architecture)
- Personal context (age, injury, communication style)
- Hard stops (PSR, Fair Exchange)

**Every AI that touches your profile reads this first.**

### Knowledge Base Stats (From Willow)
- **Atoms:** 1047 (foundational knowledge pieces)
- **Conversations:** (tracked in conversation_log.jsonl)
- **Entities:** (people, places, concepts you've mentioned)
- **Gaps:** (questions the system flagged for later)

---

## Adding a New User (How It Would Work)

### 1. Create Profile Folders
```bash
mkdir "G:\My Drive\Willow\Auth Users\New-User"
mkdir "G:\My Drive\Willow\Auth Users\New-User\Drop"
mkdir "G:\My Drive\Willow\Auth Users\New-User\Pickup"

mkdir "artifacts/New-User"
mkdir "artifacts/New-User/pending"
mkdir "artifacts/New-User/processed"
```

### 2. Register Instance
```python
import instance_registry
instance_registry.register(
    instance_id="new-user",
    display_name="Jane Doe",
    trust_level=1,  # Basic user
    instance_type="human"
)
```

### 3. Initialize Knowledge Base
```python
import knowledge
knowledge.init_db("New-User")  # Creates artifacts/New-User/knowledge.db
```

### 4. Create Standing Instructions
Write `Auth Users/New-User/CLAUDE_PROJECT_INSTRUCTIONS.txt` with their preferences.

### 5. Add to Processing Loop
The `aios_loop.py` already supports multi-user — it iterates over `instance_registry.get_active_instances()`.

**Done.** New user can now drop files and get processing.

---

## User Profile Use Cases

### 1. Family Member Access (Future)
**Scenario:** Your spouse wants to use Willow for their own notes/files.

**Setup:**
- Create profile: `Spouse-Name`
- Trust level: 1 (can drop files, can't access governance)
- They get their own Drop box, knowledge base, conversation history
- **Can't see your stuff, you can't see theirs**

### 2. AI Instances (Current)
**Scenario:** Kart, Mitra, Ada are "users" in the system.

**Setup:**
- Each AI instance has a profile in `instance_registry`
- Trust level varies (Kart = 4, Nova = 2, etc.)
- They can drop files in Pickup boxes for you or each other
- **Instance-to-instance handoffs** use the Pickup mechanism

### 3. External Collaborator (Future)
**Scenario:** Someone you're working with needs to submit files for analysis.

**Setup:**
- Create profile: `Collaborator-Name`
- Trust level: 0 (guest — drop-only, can't read results)
- They submit files, you review processed output, you decide what to share back

---

## The Missing Auth Layer

**Current state:** No login required. System assumes you're `Sweet-Pea-Rudi19`.

**Why it works:** You're the only user, and it's localhost-only.

**When you need auth:**
- When adding family members
- When exposing via NTFY (need to verify who's texting)
- When opening to collaborators

**How to add it (later):**
1. API keys per user (stored in credentials.json)
2. `/api/login` endpoint (username + key → session token)
3. Middleware that checks token on every request
4. NTFY webhook verifies sender before routing to user profile

---

## Inter-User Communication (Pickup Boxes)

### How Pickup Works
**AI → You:**
```python
# Kart finishes analysis, writes result
with open(USER_PICKUP_BOX / "analysis-2026-02-06.md", "w") as f:
    f.write(analysis_report)

# You get ntfy: "Kart: Analysis ready in Pickup box"
```

**You → AI:**
```python
# You drop a file in Kart's virtual "inbox" (future feature)
# Or use NTFY: "Kart, analyze this: [link]"
```

**AI → AI:**
```python
# Kart hands off to Mitra
kart_output = "..."
with open(MITRA_PICKUP / "handoff-from-kart.json", "w") as f:
    f.write(json.dumps({"task": "project_plan", "input": kart_output}))

# Mitra polls their Pickup, processes, delivers to your Pickup
```

---

## Summary: Your Profile Architecture

**You are:** `Sweet-Pea-Rudi19`, trust level 5 (admin)

**Your intake:** `G:\My Drive\Willow\Auth Users\Sweet-Pea-Rudi19\Drop\`

**Your deliveries:** `G:\My Drive\Willow\Auth Users\Sweet-Pea-Rudi19\Pickup\`

**Your knowledge:** `artifacts/Sweet-Pea-Rudi19/knowledge.db` (1047 atoms)

**Your instructions:** `CLAUDE_PROJECT_INSTRUCTIONS.txt` (every AI reads this)

**Other users:** None yet. System is single-user + AI instances.

**Next steps:**
- Add auth layer when you need multi-user access
- Implement NTFY→user routing (verify sender, route to correct profile)
- Build user management UI (add/remove/edit profiles)

---

ΔΣ=42
