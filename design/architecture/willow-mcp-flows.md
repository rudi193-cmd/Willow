# willow-mcp — individual flow charts

MCP-only I/O: no Willow bench, SAFE store, or optional app repos. For the full new-user picture see [willow-new-user-draft.drawio](willow-new-user-draft.drawio). Canonical runtime layout: [willow-mcp `product-layout.md`](https://github.com/rudi193-cmd/willow-mcp/blob/master/docs/design/product-layout.md).

**Validated layout:** vault-full (`WILLOW_HOME == WILLOW_STORE_ROOT`) — see [sandbox/SANDBOX-LAYOUTS.md](sandbox/SANDBOX-LAYOUTS.md).

---

## 1. MCP tool request (every call)

How a single MCP tool invocation moves through the hub.

```mermaid
flowchart LR
  subgraph client["MCP client"]
    IDE[Cursor · Claude Code · …]
  end
  subgraph hub["willow-mcp"]
    SRV[stdio / serve]
    GATE[gate.py — manifest ACL]
    HND[tool handler]
  end
  subgraph home["$WILLOW_HOME"]
    MAN[mcp_apps/app_id/manifest.json]
    CFG[config/settings.global.json]
  end
  subgraph data["$WILLOW_STORE_ROOT"]
    SOIL[(collection/store.db)]
    SEC[vault.key · vault.db]
    PG[(Postgres KB + tasks)]
  end

  IDE -->|tool + app_id| SRV
  SRV --> GATE
  GATE -->|read permissions| MAN
  GATE -->|consent checks| CFG
  GATE -->|allow| HND
  GATE -->|deny| IDE
  HND --> SOIL
  HND --> SEC
  HND --> PG
  HND -->|redacted response| SRV
  SRV --> IDE
```

| Step | What happens |
|------|----------------|
| 1 | Client sends tool name + `app_id` (matches manifest seat). |
| 2 | Gate loads `mcp_apps/<app_id>/manifest.json` permissions. |
| 3 | Handler reads/writes SOIL, secrets, or Postgres as allowed. |
| 4 | Response passes through redaction funnel before return. |

---

## 2. Session entry (`session_enter`)

First MCP call of every session — picks human vs dispatch path.

```mermaid
flowchart TD
  START([session_enter app_id session_id dispatch_id])
  W{app_id == willow?}
  D{dispatch_id set?}
  HO[entry_mode: human_orchestrator]
  REJ[REJECTED orchestrator_human_only]
  HUM[entry_mode: human]
  DSP[entry_mode: dispatch]
  ASN[Return assignment.md + meta]
  CLOSE_H[Closeout: session_handoff_write]
  CLOSE_D[Closeout: handoff_write_v4]

  START --> W
  W -->|yes, no dispatch| HO
  W -->|yes + dispatch_id| REJ
  W -->|no| D
  D -->|no| HUM
  D -->|yes| DSP
  HO --> CLOSE_H
  HUM --> CLOSE_H
  DSP --> ASN
  ASN --> CLOSE_D
```

| `entry_mode` | Typical `app_id` | Closeout tool |
|--------------|------------------|---------------|
| `human_orchestrator` | `willow` (operator seat only) | `session_handoff_write` |
| `human` | specialist, no packet | `session_handoff_write` / `context_save` |
| `dispatch` | specialist + `dispatch_id` | `handoff_write_v4` |

Orchestrator write tools (`dispatch_send`, `verify_handoff`, `agent_clear`) require `WILLOW_HUMAN_ORCHESTRATOR=1` on the host.

---

## 3. Dispatch packet lifecycle

Orchestrator ↔ specialist work loop inside `$WILLOW_HOME/dispatch/{id}/`.

```mermaid
stateDiagram-v2
  [*] --> pending: dispatch_send
  pending --> working: dispatch_accept
  working --> complete: handoff_write_v4
  complete --> verified: verify_handoff
  verified --> cleared: agent_clear
  cleared --> [*]
```

```mermaid
flowchart TB
  subgraph orch["Orchestrator app_id=willow"]
    SEND[dispatch_send]
    READ[dispatch_list / dispatch_read]
    VERIFY[verify_handoff]
    CLEAR[agent_clear]
  end
  subgraph pkt["dispatch/dispatch_id/"]
    META[meta.json]
    ASG[assignment.md]
    STAT[status.json]
    HO[handoff.json]
    CO[closeout.md]
  end
  subgraph spec["Specialist app_id"]
    ACC[dispatch_accept]
    HW[handoff_write_v4]
  end

  SEND --> META
  SEND --> ASG
  SEND --> STAT
  ACC --> STAT
  READ --> ASG
  HW --> HO
  HW --> CO
  HW --> STAT
  VERIFY --> STAT
  CLEAR --> STAT
```

---

## 4. SOIL store I/O (`store_*`)

Per-app KV records under the store root (vault-full: same tree as `$WILLOW_HOME`).

```mermaid
flowchart LR
  TOOL[store_put / get / search / list]
  SCOPE[manifest store_scope]
  PATH["WILLOW_STORE_ROOT / collection / store.db"]
  SQLITE[(SQLite SOIL)]

  TOOL --> SCOPE
  SCOPE -->|allowed collection| PATH
  PATH --> SQLITE
```

| Env | vault-full | hub layout |
|-----|------------|------------|
| `WILLOW_HOME` | `…/data-vault` | `…/willow-home` |
| `WILLOW_STORE_ROOT` | same as home | `…/willow-home/store` |

---

## 5. Knowledge base (`knowledge_*` / `kb_*`)

Postgres-backed KB when a database is reachable (schema via `schema_confirm_mapping`).

```mermaid
flowchart LR
  ING[kb_ingest / knowledge_ingest]
  SRCH[knowledge_search / kb_at]
  SCH[schema_confirm_mapping]
  PG[(Postgres willow_sandbox)]
  PGDATA[postgres/data PGDATA in vault-full]

  ING --> SCH
  SRCH --> SCH
  SCH --> PG
  PG --- PGDATA
```

Standalone fallback: SQLite knowledge paths under `$WILLOW_HOME/knowledge/` when PG is absent.

---

## 6. Kart task queue (`task_*`)

Shell work runs out-of-process in bwrap; hub owns the queue.

```mermaid
flowchart TB
  SUB[task_submit]
  Q[(Postgres tasks queue)]
  WRK[willow-mcp worker --lane fast --once]
  KART[Kartikeya bwrap sandbox]
  VAULT["WILLOW_HOME bind rw"]
  RES[task_status / result]

  SUB -->|manifest task_queue| Q
  WRK -->|claim| Q
  WRK --> KART
  KART --> VAULT
  KART -->|stdout| RES
  Q --> RES
```

Fallback: `kart.db` at store root when Postgres queue is unavailable.

---

## 7. Egress gate (internet)

Three keys must align before a net-enabled task runs.

```mermaid
flowchart TD
  T[task_submit allow_net=true]
  M{manifest has task_net?}
  C{consent.internet in settings.global.json?}
  L{operator lease grant-net unexpired?}
  SIG[signed net envelope on task]
  DENY[DENIED]
  OK[Kart worker with egress]

  T --> M
  M -->|no| DENY
  M -->|yes| C
  C -->|no| DENY
  C -->|yes| L
  L -->|no| DENY
  L -->|yes| SIG
  SIG -->|invalid| DENY
  SIG -->|valid| OK
```

Egress keypair lives outside the vault: `~/.config/willow-mcp/egress/` (operator-global by design).

---

## 8. Hub ↔ vault boundary (vault-full)

What willow-mcp reads and writes in the sovereign box.

```mermaid
flowchart TB
  subgraph compute["Compute ephemeral"]
    MCP[willow-mcp serve]
    WKR[Kart worker]
  end
  subgraph box["data-vault WILLOW_HOME == WILLOW_STORE_ROOT"]
    SEC[vault.key · vault.db]
    SOIL[collection/store.db]
    RCP[mcp_receipt.db]
    KDB[kart.db fallback]
  subgraph pg["postgres/data"]
      PG[(KB · tasks · agents)]
    end
    CFG[config/ · mcp_apps/]
    DISP[dispatch/ · sessions/]
  end

  MCP -->|in-place I/O| box
  WKR -->|rw bind| box
```

Provision: `willow-mcp-init` + optional `willow-data-vault/bootstrap/provision.sh` for greenfield box seed.

---

## Related docs

| Doc | Location |
|-----|----------|
| Session lifecycle design | `willow-mcp/docs/design/session-lifecycle.md` |
| Operator session flow | `willow-mcp/docs/SESSION_FLOW.md` |
| Sandbox smoke (vault-full) | [sandbox/sandbox-vault-smoke.sh](sandbox/sandbox-vault-smoke.sh) |
| Layout comparison | [sandbox/SANDBOX-LAYOUTS.md](sandbox/SANDBOX-LAYOUTS.md) |
