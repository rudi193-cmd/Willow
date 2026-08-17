# Remote Path Unification — one Pangolin-fronted MCP endpoint

Status: **DRAFT** · 2026-08-17 · seat: willow · author: instance (proposes; operator ratifies)
Source: read-only survey of `safe-app-willow-grove/grove/mcp_local.py` + `mcp_auth.py` +
`docs/runbooks/grove.md`; `willow-2.0/scripts/discord_remote.py` + the `willow-remote` /
`openclaw-discord` skills; `willow-2.0/apps/ratatosk/` README, `transport/grove_client.py`
(rewritten `b6f4fce`), `transport/config.py`. No code changed by this document.

Verify-don't-assert: every migration step below carries an observable gate. Nothing here is
built without operator ratification — this is a design + migration plan, not an authorization
to touch `safe-app-willow-grove` or `willow-2.0`.

---

## 1. Problem

The willow fleet grew **three** independent "remote control" paths that all end up reading
and writing the same `grove.messages` Postgres table, each with its own transport, its own
auth model, and its own failure surface:

1. **MCP/OAuth direct** (`safe-app-willow-grove`) — the canonical remote surface.
2. **Discord phone bridge** (`willow-2.0`) — a REST polling relay plus a Claude Code skill.
3. **ratatosk** (`willow-2.0/apps/ratatosk`) — a Termux phone↔desktop console, until
   `b6f4fce` a phantom REST client, now a real MCP client of path 1's own endpoint.

Three paths means three things to keep alive, three auth stories to reason about, and three
places a fix has to be re-applied. Path 3 collapsing into an MCP client of path 1 is the
opening this plan takes: it is evidence that the fleet's own engineering is already
converging on one endpoint. This document makes that convergence a decision instead of an
accident.

---

## 2. Current state

### 2.1 Comparison table

| | **MCP/OAuth direct** | **Discord bridge** | **ratatosk** |
|---|---|---|---|
| Repo | `safe-app-willow-grove` | `willow-2.0` | `willow-2.0/apps/ratatosk` |
| Transport | Streamable-HTTP MCP (JSON-RPC), stdio for local | Discord REST API, 15–30s poll loop | Streamable-HTTP MCP (JSON-RPC), hand-rolled over `requests` |
| Auth | OAuth 2.0 + PKCE, dynamic client registration, human click at `/grove-approve`; new `grove:read`/`grove:write` per-tool scopes, `grove` back-compat superscope | Static `DISCORD_BOT_TOKEN` (bot-level trust) + Grove's own implicit local trust (`sender` is a free-text field, no auth on the DB write) | Static bearer (`GROVE_TOKEN` env or `~/.willow/grove_token`) sent as `Authorization: Bearer`; does not perform the OAuth dance itself — expects a token already minted via `/grove-approve` (or hand-dropped for dev) |
| Initiator | claude.ai / any MCP client reaching the tunnel; or local Claude Code over stdio | Phone → Discord app → bot polls `channels/{id}/messages`; separately Claude Code's `willow-remote` skill tails a log via `Monitor` | Termux phone app or desktop `ratatosk listen`, over tailnet by default (`RATATOSK_TRANSPORT=tailnet`), with `ngrok`/`cloudflare`/`pangolin`/`funnel` as adapters — URL selection only, same MCP client underneath |
| Capabilities | Full tool surface: messaging, bus (`grove_bus_send/receive`, priorities, correlation), threads/flags, fleet awareness (`grove_agents`, `grove_fleet_status`, `grove_human_required`), channel mgmt, resource subscriptions (`subscriptions/listen`, LISTEN/NOTIFY push) | One channel (`hanuman`), free-text pass-through; no structured tool surface, no bus semantics, no fleet-awareness tools | Subset wired today: `get_history`, `post`, `post_envelope`, `list_channels`, `ping`/`tail_cursor` — a thin client over the same tool surface path 1 exposes; nothing stops it calling the rest |
| Where it runs | Grove host, `127.0.0.1:8765`, fronted by a tunnel (Pangolin/ngrok/cloudflared/Tailscale Funnel — code is tunnel-agnostic) | Grove host, as a standalone poll-loop process (cannot persist inside bwrap/Kart per the `willow-remote` skill — must run in a separate terminal or systemd unit) plus a Discord-side bot process; `willow_discord_responder.py` (Ollama) is the always-on fallback when no Claude Code session is live | Phone (Termux) and/or desktop, over tailnet primarily |
| Failure modes | Tunnel down = no remote reach, but local stdio still works; stale/expired 30-day token requires re-approval; `GROVE_MCP_AUTO_APPROVE=1` behind a tunnel is a known footgun (any caller reaching `/authorize` gets a full-scope token) | Poll-interval latency (15–30s) both directions; bridge daemon death is silent unless someone runs `status`; loop-prevention is a sender-name convention (`hanuman` vs `discord-bridge`), not enforced; Discord bot token compromise = full read/write to the `hanuman` channel with no further gate | Depends on tailnet reachability; if `GROVE_TOKEN` is stale/missing, `TransportConfig.issues()` catches it locally but nothing revokes or rotates it remotely; `public_exposure` misconfiguration is caught by a config-level check, not enforced by the server |
| Redundancy with path 1 | — (canonical) | Full — same `grove.messages` table, coarser tools, weaker auth, added latency | Now none at the protocol level — same endpoint, same tools, subset of calls |

### 2.2 What "redundant" actually means here

- **ratatosk is no longer architecturally distinct.** After `b6f4fce` it is a dependency-light
  MCP client hitting the same `{grove_url}/mcp` endpoint with the same JSON-RPC shapes
  (`initialize`, `tools/call`) that any other MCP client uses. Its only remaining
  differentiator is *packaging* — a phone-first CLI/GUI and a tailnet-first default — not
  protocol.
- **The Discord bridge is redundant at the data layer** (same table) but **not at the UX
  layer** — it is the only path of the three that pushes a notification to a phone the human
  didn't have open, and the only one with an existing "just type in the app you already use"
  interface. That distinction is what makes its retirement a product decision, not a pure
  engineering cleanup (see §5).
- **MCP/OAuth direct is already the superset.** Every capability the other two paths use is a
  subset of its tool surface; neither adds a tool the other lacks.

---

## 3. Target architecture

**One Pangolin-fronted MCP endpoint is the single remote surface for the fleet.**
`safe-app-willow-grove`'s `grove/mcp_local.py --serve`, reached through a stable Pangolin
resource (Newt or reverse-proxy mode, per `docs/runbooks/grove.md`), becomes the only process
that terminates remote traffic against `grove.messages`. Every remote client — claude.ai,
ratatosk, a future mobile MCP client, a future Discord replacement — is an MCP client of that
one endpoint, distinguished only by OAuth scope and client identity, never by a separate
protocol or a separate trust story.

```
                         ┌───────────────────────────┐
   claude.ai ───────────►│                           │
                          │   Pangolin (public HTTPS) │
   mobile MCP client ────►│         resource          │
                          │                           │
   ratatosk (phone/desk) ►│  → 127.0.0.1:8765/mcp     │
                          └─────────────┬─────────────┘
                                        │  OAuth 2.0/PKCE
                                        │  grove:read / grove:write
                                        ▼
                          grove.mcp_local --serve
                          (safe-app-willow-grove)
                                        │
                                        ▼
                          Postgres: grove.messages
                          (LISTEN/NOTIFY fan-out)
```

### 3.1 Path-by-path mapping

**MCP/OAuth direct → stays, becomes THE endpoint.** No architectural change; the target state
*is* this path, generalized to be reached over Pangolin specifically rather than
"tunnel-agnostic." Pangolin is already one of the four documented options
(`docs/runbooks/grove.md` §"Remote access") and already has both a Newt mode and a
reverse-proxy mode written up — this plan promotes it from "one of several" to "the
supported one," so operators stop re-deciding tunnel choice per deployment.

**Discord bridge → replaced by the MCP endpoint for the *command* channel; Discord's role
narrows to notification, or retires entirely (operator choice — §6).** Can the polling relay
be replaced outright? Mechanically, yes: a phone that can run an MCP client speaking to the
same Pangolin URL gets the full tool surface — `grove_send_message`, `grove_get_history`,
`grove_bus_send`, fleet-awareness tools — none of which the Discord bridge exposes today (it
is a single free-text channel with no tool schema). The open question is not capability, it is
*client maturity on a phone* (see §3.2) and *push*. What is lost and how it's mitigated:

- **Lost: push notification to a phone the human isn't actively looking at.** MCP as specced
  has no native push/webhook to a mobile OS notification tray; a client has to be open and
  polling, or the OS has to be running a background service that polls on the client's behalf
  — which is architecturally the same shape as the Discord bridge's poll loop, just aimed at
  the MCP endpoint instead of Discord's REST API. **Mitigation:** keep a *thin* notifier that
  polls `grove_watch_all` / `grove_human_required` and pushes to a channel with real mobile
  push — Discord itself (kept narrowly as a notify-only leg, §5) or a platform push service —
  while the actual command/response loop moves to MCP. This makes Discord (if kept) a
  **read-only alert fan-out**, not a second read/write path into `grove.messages`.
- **Lost: the Discord app as a familiar phone UI with no extra install.** Every family member
  of "phone remote control" this fleet has built so far (Discord bridge, ratatosk's Termux
  GUI) exists because a bare MCP client is not yet a comfortable phone experience — there is
  no equivalent of "open the app you already have" for MCP today. **Mitigation:** this is
  exactly ratatosk's job (§3.1 next) — a purpose-built thin front-end is the right place to
  absorb that UX gap, rather than re-solving it inside a Discord-specific bridge.

**ratatosk → is now, correctly, a thin MCP front-end over the same endpoint.** Its
`GroveClient` (rewritten `b6f4fce`) already speaks the identical wire protocol
(`initialize` → `tools/call`) against `{grove_url}/mcp`; the only thing separating it from
"the reference MCP client" is that it wires a subset of tools and reads its bearer token from
`GROVE_TOKEN`/`~/.willow/grove_token` rather than performing OAuth itself. **This is the
target shape for a phone-first remote, not a separate system to unify away** — the unification
work here is (a) pointing its `pangolin` transport mode at the *same* Pangolin resource the
other clients use rather than a parallel one, and (b) closing the auth gap in §4 rather than
building a new transport.

### 3.2 Is mobile MCP mature enough? — be honest

Not fully, and this plan says so rather than assuming it. `ratatosk`'s own `TransportConfig`
still treats non-tailnet modes (`ngrok`, `cloudflare`, `pangolin`, `funnel`) as "a public
relay" requiring an explicit `RATATOSK_PUBLIC_EXPOSURE=1` opt-in — i.e. even the fleet's own
MCP-native phone client does not yet treat "MCP over the public internet, phone-initiated" as
a default-safe posture. claude.ai's own mobile app MCP-connector support is a moving target
outside this repo's control. Until an operator has actually driven a full Pangolin-fronted
OAuth approval flow (`/grove-approve`, click Allow) from a phone browser and confirmed a
token lands where `ratatosk`/claude.ai mobile expects it, "mobile MCP replaces Discord" is a
target, not a shipped fact. See kill criteria in §5.

---

## 4. Auth unification

**Target: OAuth 2.0 + PKCE with `grove:read`/`grove:write` is the one auth story.** Every
remote actor authenticates the same way; the only axis of difference is which scopes its
token carries and who clicked Allow.

| Actor | Today | Target |
|---|---|---|
| claude.ai | OAuth/PKCE, `/grove-approve` click, `grove:read`+`grove:write` by default (`DEFAULT_SCOPES`) | unchanged — already the target shape |
| ratatosk | Static bearer token, pre-minted by hand or by a prior `/grove-approve` flow; no refresh logic of its own | Same token *mechanism*, but the token must come from a real `/grove-approve` grant per install (or per device) rather than a hand-copied shared secret — i.e. treat ratatosk as a first-class OAuth client that registers dynamically like any other, not a bearer pasted once. `mcp_auth.py`'s `exchange_refresh_token` already exists; ratatosk should use it before the 30-day access token expires instead of going stale silently. |
| Discord bridge | No auth on the Grove side at all — the bridge process itself is the trust boundary (`DISCORD_BOT_TOKEN` gates who can post to the channel; anyone who can write into `hanuman` with the right sender name is trusted implicitly by `grove_db.send_message`) | Retired as a write path (§5). If a notify-only leg survives, it never writes to Grove — it only *reads* (ideally via a `grove:read`-scoped token of its own) and pushes to Discord; it has no `grove:write` capability, so a compromised bot token can leak messages but cannot forge fleet commands. |
| Scope granularity | `grove:read` / `grove:write` landed; `grove` kept as a back-compat superscope that implies both (`_expand_scopes`) | Use scopes deliberately per client: a notify-only Discord leg gets `grove:read` only; ratatosk and claude.ai keep both by default since they're full remote-control clients. No client should be minted `grove` (the superscope) going forward — it exists only to keep pre-existing 30-day tokens working, not as a thing new clients ask for. |
| Auto-approve | `GROVE_MCP_AUTO_APPROVE=1` exists as an operator opt-in, off by default, loud when on | No change proposed — already fail-closed by default. Explicitly **do not** turn this on to make ratatosk/mobile onboarding smoother; the correct fix is real dynamic client registration per device, not skipping the human click. |

This closes the biggest asymmetry in the current state: the Discord bridge's trust model is
"whoever holds the bot token, plus a sender-name convention for loop-prevention" with **zero**
connection to Grove's own auth server, while the MCP path already has a real authorization
server with scopes, expiry, and a human-in-the-loop consent screen. Folding Discord's
remaining role (if any) behind `grove:read` removes the one place in the fleet where a
non-Grove credential can write directly into `grove.messages`.

---

## 5. Migration plan

Ordered, reversible, old-and-new run in parallel until each retirement's kill criteria are
met. No step here disables anything by itself — disabling a running leg is a separate gated
act per this repo's own convention (see `willow-2.0-decommission-plan.md` §1: "staged +
reversible — disable → stop → observe → uninstall → archive. Never delete.").

**Step 0 — Freeze scope creep on the losing paths (no code change).**
Stop adding new Discord-bridge commands or new ratatosk-bespoke transport logic; both were
already trending toward "wrap the MCP endpoint" and further divergence just adds migration
surface. Gate: no new non-MCP command added to `discord_remote.py` / `openclaw-discord` after
this plan is ratified.

**Step 1 — Stand up the Pangolin resource as the one documented remote path (already possible
today, zero code change).** Point Newt (or a reverse-proxy resource) at
`127.0.0.1:8765`, set `GROVE_MCP_URL` to the Pangolin hostname, run `scripts/grove-serve on`.
Gate: `scripts/grove-serve status` shows the unit up and the claude.ai connector URL resolving;
a manual `/grove-approve` flow completes end to end from an external network.

**Step 2 — Point ratatosk's `pangolin` transport mode at that same resource, in parallel with
its existing tailnet default.** No change to `GroveClient` itself — this is a config/token
step: mint a real OAuth grant for a ratatosk client id via `/grove-approve` rather than a
hand-copied bearer, store it at `~/.willow/grove_token`. Gate: `ratatosk doctor` / `ping()`
succeeds over the Pangolin URL with a token minted through the real OAuth flow, not a manually
placed secret.

**Step 3 — Stand up a Discord *notify-only* leg (if the operator keeps Discord at all — see
open decision in §6) that reads via `grove:read` and never writes.** This can run alongside
the existing full bridge with zero risk, since it's strictly less capable. Gate: alert traffic
(fleet status changes, `grove_human_required` items) reaches Discord through the new leg while
the old bridge is still live, side by side, for a comparison window.

**Step 4 — Redirect Discord's *inbound* command path to MCP instead of the poll loop, if
mobile MCP is judged ready (§3.2 gate).** Either (a) a phone-side MCP client good enough to
replace "type in Discord," making inbound Discord commands unnecessary, or (b) if not ready,
explicitly keep Discord inbound alive longer under its own tracked exception rather than
silently letting it linger. This is the fork the operator has to call — see §6.

**Step 5 — Observe.** Run whichever legs remain in parallel for a defined window (propose:
minimum two weeks of normal fleet use) with the old Discord bridge process left running but
demoted to "fallback only" — i.e. `willow_discord_responder.py`'s Ollama fallback keeps working
as the safety net it already is, unaffected by any of this.

**Step 6 — Retire per kill criteria, never delete.** Per path:

- **Discord full read/write bridge (`discord_remote.py` daemon + `willow-remote` skill's
  claim/inbound flow):** retire once (a) the notify-only leg has been live and correct for the
  observation window, and (b) either mobile MCP command entry is confirmed working from a real
  phone, or the operator has explicitly decided to keep Discord command-entry indefinitely
  (§6) — in which case this step does not fire and the plan's job is done at Step 3. If
  retired: stop the daemon, archive `discord_remote.py`/`willow-remote` skill under the
  existing archive-don't-delete convention, leave `DISCORD_BOT_TOKEN` vaulted (unused, not
  deleted) in case of rollback.
- **openclaw-discord (Mode A bridge):** same kill criteria as above — it's a second
  implementation of the identical bridge pattern (`grove:` prefix commands over Discord) and
  should be retired or kept on the same schedule and the same decision, not independently.
- **ratatosk's tailnet-only default:** not retired — tailnet stays the recommended default per
  `transport/config.py`'s own posture (`public_exposure` opt-in required for every other mode).
  Pangolin becomes an additional supported mode for when tailnet reach isn't available (travel,
  cellular-only), not a replacement for it.

**Rollback at any step:** every step above is additive (new leg stood up alongside old) until
Step 6, and Step 6 only stops a process/service — it does not touch `grove.messages`,
`grove_db.py`, or the Postgres schema, and archived scripts remain in git history and on disk
under the archive convention. Un-retiring means starting the daemon again, not restoring data.

---

## 6. Risks & open decisions for the operator

These are the genuine forks — this plan does not pre-decide them:

1. **Keep Discord as a notify channel, or retire it fully?** The engineering case for
   retiring the *write* path is strong (§4 — it's the one uncredentialed write surface into
   Grove). The UX case for keeping Discord as a *read-only* push channel is also strong (§3.1 —
   MCP has no native mobile push story yet). The operator has to decide whether that channel
   is worth the ongoing maintenance of a second (even if narrowed) process, or whether losing
   push notifications until a better mobile MCP story exists is an acceptable cost of full
   consolidation.
2. **Is mobile MCP mature enough to be the *inbound command* path today, or only the target?**
   §3.2 is explicit that this hasn't been operator-verified end to end from an actual phone.
   Shipping Step 4 before that verification risks silently losing the one working "type a
   command from my phone" path the fleet has (Discord) in exchange for one that hasn't been
   proven. Recommendation embedded in the migration order: Step 4 does not fire until its own
   gate passes, and Step 3 (notify-only) is safe to ship regardless of how this resolves.
3. **Does ratatosk get its own OAuth client identity, or reuse claude.ai's approval flow
   conceptually?** `mcp_auth.py`'s dynamic client registration already supports arbitrary
   client ids; the open question is operational — does each ratatosk install (each phone,
   potentially each Termux reinstall) get its own `/grove-approve` click, or is there a
   provisioning shortcut the operator wants (e.g. a longer-lived scoped token minted once per
   device via a documented manual step)? This plan recommends per-device registration (cleaner
   revocation, matches the existing consent model) but flags it as a real UX cost on a phone.
4. **Auto-approve for ratatosk specifically?** Given `GROVE_MCP_AUTO_APPROVE` is fleet-wide
   (not per-client), turning it on to smooth ratatosk onboarding would also remove the human
   click for claude.ai and anyone else who can reach `/authorize` — explicitly rejected in §4,
   flagged here because it will keep being tempting during Step 2's config friction.
5. **Retention/latency of the Postgres LISTEN/NOTIFY push under Pangolin.** Not surveyed by
   this plan — `docs/runbooks/grove.md` documents the NOTIFY path but this plan did not verify
   `subscriptions/listen` behavior across a Pangolin hop for a long-lived mobile connection
   (backgrounded app, cellular handoff). Worth a dedicated spike before Step 4 if push-via-MCP
   (rather than poll) is wanted on mobile.

---

## 7. Non-goals / out of scope

- **Not touching the Grove data model.** `grove.messages`, the bus columns
  (`to_agent`/`bus_type`/`priority`/`correlation_id`), flags, and channels are unchanged by
  this plan — this is a transport/auth consolidation, not a schema migration.
- **Not building a new mobile app or MCP client.** ratatosk already exists and already speaks
  MCP; this plan routes it and evaluates it, it does not propose a new build.
- **Not deciding tunnel technology fleet-wide beyond "Pangolin is the supported default."**
  ngrok/cloudflared/Tailscale Funnel remain documented, tunnel-agnostic fallbacks in
  `docs/runbooks/grove.md`; this plan does not propose removing that documentation, only that
  Pangolin is the one operators are steered toward for new setups.
- **Not the `willow-2.0` decommission itself.** That is `willow-2.0-decommission-plan.md`'s
  scope. This plan notes (per that document's own finding) that Grove is *not* a `willow-mcp`
  dependency and that `willow-2.0`'s own `the_grove.py`/local Grove concepts are unrelated to
  `safe-app-willow-grove`'s server — the two should not be conflated, and nothing here changes
  that document's retirement schedule for `willow-2.0`'s code apparatus.
- **Not touching `willow_discord_responder.py`'s Ollama always-on fallback.** It answers when
  no Claude Code session is live regardless of which bridge is running; this plan neither
  relies on it nor proposes removing it.
- **Not a security audit of Pangolin itself.** This plan assumes Pangolin's own resource/Newt
  auth is sound and out of scope; it only unifies what sits *behind* the tunnel.

---

## 8. Verify-don't-assert — what "done" looks like

- One documented remote endpoint (`<pangolin-host>/mcp`) that claude.ai, ratatosk, and (if
  kept) a Discord notify leg all point at.
- Zero credentials that write to `grove.messages` outside an OAuth-issued, scoped,
  human-approved token — no bot token, no static bearer minted outside `/grove-approve` or its
  refresh flow.
- The Discord *write* path either archived-not-deleted with a dated retirement note, or kept
  under an explicit, operator-logged exception with its own review date — never left running by
  default drift.
- This document itself superseded or updated, not silently ignored, the next time any of the
  three paths' code changes in a way that would invalidate a row of §2.1's table.

---

ΔΣ=42
