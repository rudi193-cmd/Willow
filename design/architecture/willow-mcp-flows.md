# willow-mcp — individual flow charts

MCP-only I/O: no Willow bench, SAFE store, or optional app repos. For the full new-user picture see [willow-new-user-draft.drawio](willow-new-user-draft.drawio). Canonical runtime layout: [willow-mcp `product-layout.md`](https://github.com/rudi193-cmd/willow-mcp/blob/master/docs/design/product-layout.md).

**Validated layout:** vault-full (`WILLOW_HOME == WILLOW_STORE_ROOT`) — see [sandbox/SANDBOX-LAYOUTS.md](sandbox/SANDBOX-LAYOUTS.md).

**Inference vs tools:** willow-mcp is the **tool plane** (memory, dispatch, Kart, gate). The **inference client** that calls it (Cursor, Claude Code, Discord bridge, or a large local model on the same machine) is replaceable and sits outside the hub.

---

## 0. Inference client (replaceable)

The MCP client and the model that reasons are one seat from the operator's view, but architecturally they are **not** willow-mcp. Any host that speaks MCP can drive the same hub.

```mermaid
flowchart TB
  YOU[You]
  subgraph client["Inference client — pick one"]
    CLOUD[Cursor · Claude Code · cloud API]
    LOCAL[Local host · Ollama · LM Studio · open-weight model]
  end
  subgraph hub["willow-mcp tool plane"]
    MCP[stdio or serve on 127.0.0.1]
  end
  subgraph box["$WILLOW_HOME / vault"]
    DATA[(SOIL · KB · dispatch)]
  end
  subgraph local_infer["Local models on your computer"]
    OLL[Ollama :11434 infer + embed]
  end

  YOU --> client
  client -->|MCP tool calls + app_id| MCP
  MCP --> DATA
  LOCAL -.->|same machine| OLL
  CLOUD -.->|optional cloud LLM| client
```

| Client shape | Typical stack | Notes |
|--------------|---------------|-------|
| **Cloud IDE** | Cursor / Claude Code → vendor API | Default onboarding picture; needs `consent.cloud_llm` if the vendor is off-machine. |
| **Local-first** | Open WebUI / Continue / custom agent → `localhost:11434` | Same MCP config pointing at `willow-mcp`; reasoning never leaves the box. |
| **Hybrid** | Local model for chat, willow-mcp for tools | Common on a workstation with Ollama + vault; hub stays local regardless. |

`willow-mcp serve` binds **127.0.0.1** by default — the tool plane is localhost-hard even when the inference client uses a cloud model.

---

## 1. MCP tool request (every call)

How a single MCP tool invocation moves through the hub.

```mermaid
flowchart LR
  subgraph client["MCP client + inference replaceable"]
    IDE[Cursor · Claude · local LLM host · …]
  end
  subgraph hub["willow-mcp"]
    SRV[stdio / serve 127.0.0.1]
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
| 1 | Inference client sends tool name + `app_id` (matches manifest seat). |
| 2 | Gate loads `mcp_apps/<app_id>/manifest.json` permissions. |
| 3 | Handler reads/writes SOIL, secrets, or Postgres as allowed. |
| 4 | Response passes through redaction funnel before return. |

The client performs chat/reasoning; willow-mcp performs **authorized I/O** only.

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

Shell work runs out-of-process in bwrap; hub owns the queue. Network is **off** unless explicitly granted (`allow_localhost` for loopback/Ollama, or `allow_net` for internet — see §7 and §9).

```mermaid
flowchart TB
  SUB[task_submit]
  Q[(Postgres tasks queue)]
  WRK[willow-mcp worker --lane fast --once]
  KART[Kartikeya bwrap sandbox]
  VAULT["WILLOW_HOME bind rw"]
  OLL[Ollama :11434 optional]
  RES[task_status / result]

  SUB -->|manifest task_queue| Q
  WRK -->|claim| Q
  WRK --> KART
  KART --> VAULT
  KART -.->|allow_localhost only| OLL
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

For **localhost-only** tasks (Ollama, local APIs), use `# allow_localhost` — see §9.

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

## 9. Hard routing to local models

Default posture: **local-first, cloud by explicit consent**. Three lanes keep inference and egress on-machine unless the operator escalates.

```mermaid
flowchart TB
  subgraph posture["Standing defaults fail-closed"]
    INIT["willow-mcp-init: consent.cloud_llm = false"]
    EXP["exposure.json: cloud_llm → voice_only"]
    BIND["serve binds 127.0.0.1"]
  end
  subgraph hub_tools["Hub-initiated local inference"]
    NEST["nest_scan use_embed / use_llm"]
    OLL["Ollama localhost:11434"]
    OFF["regex / offline fallback"]
    NEST -->|hard route| OLL
    OLL -->|daemon down| OFF
  end
  subgraph kart_net["Kart network modes mutually exclusive"]
    LH["task_submit allow_localhost=true"]
    NET["task_submit allow_net=true"]
    LOOP["loopback only e.g. :11434"]
    WAN["internet after 3-key gate §7"]
    LH --> LOOP
    NET --> WAN
  end
```

| Lane | Mechanism | Reaches |
|------|-----------|---------|
| **Inference client** | Operator runs local LLM host instead of Cursor/Claude | Chat/reasoning stays on box; same MCP tools |
| **Hub tools** | `nest/llm.py`, `nest/embed.py` → `OLLAMA_HOST` default `http://localhost:11434` | Embeddings/classification; no cloud path in code |
| **Kart localhost** | `# allow_localhost` + `grant-net --localhost` | Host loopback (typical: Ollama, local HTTP APIs) |
| **Kart internet** | `# allow_net` + consent + lease + signature | Outside world — never the default |
| **Exposure membrane** | `exposure_slice(..., destination=cloud_llm)` | Even when a cloud client is used, seed fields are sliced to `voice_only` unless widened |

Kart bwrap **without** a network directive shares no network namespace — tasks cannot reach Ollama until `allow_localhost` is explicitly granted (same gate family as `allow_net`, localhost-only scope).

---

## Related docs

| Doc | Location |
|-----|----------|
| Session lifecycle design | `willow-mcp/docs/design/session-lifecycle.md` |
| Operator session flow | `willow-mcp/docs/SESSION_FLOW.md` |
| Exposure membrane (AS-8) | `willow-mcp/docs/design/agent-seed.md` §5 |
| Hooks/skills import plan (Option A) | [willow-mcp-hooks-skills-import.md](willow-mcp-hooks-skills-import.md) |
| Kart localhost vs net | `kartikeya` sandbox `allow_localhost` |
| Sandbox smoke (vault-full) | [sandbox/sandbox-vault-smoke.sh](sandbox/sandbox-vault-smoke.sh) |
| Layout comparison | [sandbox/SANDBOX-LAYOUTS.md](sandbox/SANDBOX-LAYOUTS.md) |
