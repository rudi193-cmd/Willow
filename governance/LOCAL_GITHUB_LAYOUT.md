# Local GitHub layout — org workspaces on disk

**Status:** draft · operator guide · **2026-08-10**  
**Supersedes for layout:** `~/github/README-fleet-layout.md` (flat sibling tree, 2026-05-31).  
**Repo lists and tiers:** [`FLEET_PLACEMENT_DRAFT.md`](FLEET_PLACEMENT_DRAFT.md) §11 (update org names there when ratified).  
**Naming / seat / root rules:** [`safe-app-store-public` die-rules + homestead-affairs face](https://github.com/rudi193-cmd/safe-app-store-public/blob/master/docs/die-rules.md) (Aug 2026) — **Homestead · Affairs** → org **`homestead-affairs`**, not `homestead-sovereign`.  
**Worked example:** [`almanac-data`](https://github.com/almanac-data/almanac-data) meta-repo (`README.md`, `scripts/link-repos.sh`).

This document is how **`~/github/`** should look after a clean reclone: **one directory per GitHub org**, product repos inside it, **face runtime roots** as dot-directories inside the org that owns the face, optional **meta workspace** per org (like almanac), and **no** fifty unrelated top-level clones.

---

## Principles

1. **Org slug = folder name** — `willow-memory/`, `hornbook-knowledge/`, `Die-Namic-Systems/`, `almanac-data/`, `homestead-affairs/`, `forge-play/`, `terpsi-programs/`.
2. **Base seat = short repo name** — `willow`, `hornbook`, `die-namic`, `almanac`, `homestead`, `play`, `terpsi` (optional until the face has a shared artifact; mandatory seats: see die Rule 1 in SAFE `docs/die-rules.md`).
3. **Git cannot nest orgs** — disk layout is for humans and Cursor; **remotes** still use `github.com/<org>/<repo>`.
4. **Symlinks, not copies** — meta workspaces link to real clones under `~/github/<org>/<repo>/` (almanac pattern). One physical clone per repo.
5. **Runtime lives on the face's org** — each org may hold a **dot-directory** (not a git repo) for that face's persistence on the operator box: `.willow`, `.nestor`, `.hornbook`, `.almanac`, `.homestead`, `.forge`, `.terpsi`. These are **gitignored** trees (config, stores, handoffs, venvs). **`~/.willow`** (and peers) are **symlinks** into the canonical org path so legacy env vars and docs keep working.
6. **willow-config** clones into **`willow-memory/.willow/`** — not `~/github/.willow` at the trunk.
7. **Tier F stays out** — `willow-2.0`, `willow-1.9`, `willow-canonical`, `willow-compose`, duplicate flat almanac paths → archive or omit on fresh install ([`FLEET_PLACEMENT_DRAFT.md`](FLEET_PLACEMENT_DRAFT.md) §8).

---

## Target tree

```text
~/github/
├── workshop/                     # tier E — optional bucket (see below)
├── safe-app-store-public/        # tier D playground until apps promote to face orgs
│
├── Die-Namic-Systems/
│   ├── dotgithub/                # clone of Die-Namic-Systems/.github
│   ├── .nestor/                  # face runtime (gitignored) — operator Nestor/dogfood state
│   ├── die-namic/                # base seat (draft; create when opened)
│   └── nestor/
│
├── willow-memory/
│   ├── .willow/                  # willow-config + fleet runtime; symlink ~/.willow → here
│   ├── dotgithub/
│   ├── willow/                   # charter — target after transfer from rudi193-cmd/Willow
│   ├── willow-mcp/
│   ├── willow-gate/
│   └── kartikeya/
│
├── hornbook-knowledge/
│   ├── .hornbook/                # face runtime (gitignored) — campus/corpus local state
│   ├── dotgithub/
│   ├── hornbook/                 # base seat (draft)
│   ├── UTETY/
│   └── Jeles/
│
├── almanac-data/                 # meta-repo + all verticals (single org folder)
│   ├── .almanac/                 # caretaker local state (gitignored)
│   ├── dotgithub/                # almanac-data/.github
│   ├── org-dotgithub/            # → dotgithub (workspace alias)
│   ├── almanac-template/
│   ├── climate-almanac/
│   ├── civic-almanac/
│   └── … (all *-almanac verticals)
│
├── homestead-affairs/
│   ├── .homestead/               # household runtime; symlink ~/.homestead → here
│   ├── dotgithub/
│   ├── homestead/                # base seat + homestead.keep (see SAFE build plan)
│   ├── homestead-law/            # promoted law-gazelle (future)
│   └── awesome-sovereign-software/
│
├── forge-play/
│   ├── .forge/                   # Play/forge workshop runtime (gitignored)
│   ├── dotgithub/
│   ├── play/                     # base seat (draft)
│   └── forge/                    # promoted SAFE store face (future)
│
└── terpsi-programs/
    ├── .terpsi/                  # institutional/ward local state (gitignored)
    ├── dotgithub/
    ├── terpsi/                   # base seat (draft)
    ├── terpsi-template/          # draft names — §11
    ├── terpsi-core/
    └── terpsi-music/             # promoted from hornbook when split completes
```

**Org profile repos:** GitHub names them `.github`; clone into **`dotgithub/`** (almanac may use **`org-dotgithub/`** — one convention per org).

**Dot-directory names:** If you used a different label at the top of the tree (e.g. hornbook), keep **one dot-root per org** and match the **home symlink** table below.

**Postgres:** still system-wide (`willow_20`, etc.) — not under these dot trees.

---

## Buckets outside the seven orgs

| Path | Tier | Notes |
|------|------|--------|
| `~/github/safe-app-store-public/` | D | Monorepo + `apps/*`; most never promote. Symlink `~/safe-app-store` here. |
| `~/github/workshop/` | E | `sean-data-vault`, `quiet-corner`, `DispatchesFromReality`, `community`, `courtlistener-mcp`, forks — operator discretion. |
| `~/github/archive/` | F | Cold storage after `mv` of old flat tree; not for daily work. |
| `~/Desktop/Nest` | intake | Runtime drop zone — not a repo root ([`FLEET_PLACEMENT_DRAFT.md`](FLEET_PLACEMENT_DRAFT.md) §9). |

---

## Home-level symlinks (after reset)

Canonical runtime paths sit under the org folder; home entries are symlinks only.

| Link | Target |
|------|--------|
| `~/.willow` | `~/github/willow-memory/.willow` |
| `~/.homestead` | `~/github/homestead-affairs/.homestead` |
| `~/.nestor` | `~/github/Die-Namic-Systems/.nestor` *(optional; operator dogfood)* |
| `~/.hornbook` | `~/github/hornbook-knowledge/.hornbook` *(when used)* |
| `~/.almanac` | `~/github/almanac-data/.almanac` *(caretaker)* |
| `~/.forge` | `~/github/forge-play/.forge` *(Play face workshop)* |
| `~/.terpsi` | `~/github/terpsi-programs/.terpsi` *(when shipped)* |
| `~/safe-app-store` | `~/github/safe-app-store-public` |
| `~/willow-2.0` | **Remove** on reset; keep only under `~/github/archive/` if tier F is frozen |

`WILLOW_HOME` should resolve to the same directory as `~/.willow` (symlink is enough for most tooling).

Charter **git** repo: `~/github/willow-memory/willow` — set MCP `project-root` and `willow-mcp onboard --project-root` there after transfer.

---

## `link-repos.sh` pattern (non-almanac orgs)

Almanac ships the reference script: `almanac-data/scripts/link-repos.sh`. Other orgs use the same mechanics inside an optional **meta folder** (only needed if you want one Cursor workspace per face).

Example skeleton for `willow-memory/scripts/link-repos.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORG_PARENT="$(cd "$ROOT/.." && pwd)"
link() {
  local name="$1" src="${2:-$1}"
  local target="${ORG_PARENT}/willow-memory/${src}"
  local dest="${ROOT}/${name}"
  [[ -d "$target" ]] || { echo "SKIP $name — missing $target" >&2; return 0; }
  [[ -e "$dest" ]] && { echo "WARN $dest exists" >&2; return 0; }
  ln -s "$target" "$dest"
}
link dotgithub
link willow-mcp
link willow-gate
link kartikeya
link willow
```

Meta workspace repo for Willow · Memory is **optional** (unlike almanac, where `almanac-data/almanac-data` is the caretaker jump-in). Minimum viable layout: **only** `~/github/willow-memory/<repo>/` directories, no meta repo.

---

## Clone manifest (fresh machine)

Run from empty `~/github/`. Adjust branch (`main` vs `master`) per [`notes/fleet-repo-conventions-2026-08-04.md`](../notes/fleet-repo-conventions-2026-08-04.md).

```bash
mkdir -p ~/github/{Die-Namic-Systems,willow-memory,hornbook-knowledge,almanac-data,homestead-affairs,forge-play,terpsi-programs,workshop}

# Face runtime roots (empty dirs; .willow comes from willow-config clone below)
mkdir -p ~/github/Die-Namic-Systems/.nestor
mkdir -p ~/github/hornbook-knowledge/.hornbook
mkdir -p ~/github/almanac-data/.almanac
mkdir -p ~/github/homestead-affairs/.homestead
mkdir -p ~/github/forge-play/.forge
mkdir -p ~/github/terpsi-programs/.terpsi
for org in Die-Namic-Systems willow-memory hornbook-knowledge homestead-affairs forge-play terpsi-programs; do
  gh repo clone "$org/.github" "$HOME/github/$org/dotgithub" 2>/dev/null || true
done
gh repo clone almanac-data/.github "$HOME/github/almanac-data/org-dotgithub"

# Almanac — meta + verticals under one org folder
gh repo clone almanac-data/almanac-data ~/github/almanac-data
for repo in almanac-template agriculture-almanac civic-almanac climate-almanac \
  economy-almanac education-almanac energy-almanac environment-almanac health-almanac \
  justice-almanac science-almanac transportation-almanac; do
  gh repo clone "almanac-data/$repo" "$HOME/github/almanac-data/$repo"
done
gh repo clone almanac-data/.github "$HOME/github/almanac-data/dotgithub"
ln -snf dotgithub "$HOME/github/almanac-data/org-dotgithub"
cd ~/github/almanac-data && ./scripts/link-repos.sh

# Products still on rudi193-cmd until transfer — clone into org folders
gh repo clone rudi193-cmd/nestor            ~/github/Die-Namic-Systems/nestor
gh repo clone rudi193-cmd/willow-mcp        ~/github/willow-memory/willow-mcp
gh repo clone rudi193-cmd/willow-gate       ~/github/willow-memory/willow-gate
gh repo clone rudi193-cmd/kartikeya         ~/github/willow-memory/kartikeya
gh repo clone rudi193-cmd/Willow            ~/github/willow-memory/willow
gh repo clone rudi193-cmd/UTETY             ~/github/hornbook-knowledge/UTETY
gh repo clone rudi193-cmd/Jeles             ~/github/hornbook-knowledge/Jeles
gh repo clone rudi193-cmd/terpsi-music      ~/github/terpsi-programs/terpsi-music
gh repo clone rudi193-cmd/safe-app-store-public ~/github/safe-app-store-public
gh repo clone rudi193-cmd/willow-config     ~/github/willow-memory/.willow
ln -snf ~/github/willow-memory/.willow ~/.willow
ln -snf ~/github/homestead-affairs/.homestead ~/.homestead

# After GitHub transfer: replace rudi193-cmd/* with gh repo clone <org>/<repo> and fix remotes once.
```

**Tags:** for `willow-mcp` / `Jeles` stand-up, `git fetch --tags` on tag-pinned deps ([`nestor/docs/local-fleet.md`](https://github.com/rudi193-cmd/nestor/blob/master/docs/local-fleet.md)).

**Stand-up** (unchanged semantics, new paths):

```bash
cd ~/github/willow-memory/willow-mcp
NESTOR_REPO=~/github/Die-Namic-Systems/nestor \
JELES_REPO=~/github/hornbook-knowledge/Jeles \
bash scripts/fleet-standup.sh
```

---

## Cold reset — what to save first

Operator minimal stash (everything else recloneable from GitHub):

1. **Postgres** — `pg_dump -Fc` for `willow_20` (and any other DBs you still need).
2. **Git bundles** — local-only branches with no upstream, e.g. `willow-mcp` `wip/dispatch-reconcile-embed-backfill`, any WIP you have not pushed.
3. **Optional:** `~/github/willow-memory/.willow` (via `~/.willow`) store/handoffs if not fully in Postgres — tarball dot-trees per face if you care about more than PG.

Then: `mv ~/github ~/github-archive-<date>`, run clone manifest, restore PG, restore bundles into the new org paths, re-point systemd/Cursor/MCP absolute paths.

---

## Path migration checklist

After moving repos, grep and fix hardcoded `/home/.../github/willow-mcp` (etc.) in:

- `~/.config/systemd/user/*.service`
- `~/.willow` → `willow-memory/.willow`: `env`, `kart-sandbox.json`, `mcp_projects.seed.json`, venvs
- Cursor/Claude `.mcp.json`, hooks (or run `willow-mcp onboard` / `willow.sh project sync` from product docs)
- [`nestor/docs/local-fleet.md`](https://github.com/rudi193-cmd/nestor/blob/master/docs/local-fleet.md) — update when paths stabilize (upstream PR)

---

## Doc map (reorder canon)

| Question | Read |
|----------|------|
| Which repo belongs to which org? | [`FLEET_PLACEMENT_DRAFT.md`](FLEET_PLACEMENT_DRAFT.md) §11 |
| Homestead org name + Forge · Play face order | [`homestead-affairs-face.md`](https://github.com/rudi193-cmd/safe-app-store-public/blob/master/docs/homestead-affairs-face.md) |
| Mandatory base repos + seat-before-module | [`die-rules.md`](https://github.com/rudi193-cmd/safe-app-store-public/blob/master/docs/die-rules.md) |
| Almanac symlink workspace | [`almanac-data` README](https://github.com/almanac-data/almanac-data/blob/main/README.md) |
| `$WILLOW_HOME` vs `~/github` | [`willow-mcp` product-layout](https://github.com/rudi193-cmd/willow-mcp/blob/master/docs/design/product-layout.md) |
| CI branch names / mergeable behind | [`notes/fleet-repo-conventions-2026-08-04.md`](../notes/fleet-repo-conventions-2026-08-04.md) |

---

## Edit log

| Date | Change |
|------|--------|
| 2026-08-10 | Operator pass — runtime dot-dirs per org (`.willow` under `willow-memory/`, etc.); `terpsi-music` under `terpsi-programs/`; home symlinks table. |
| 2026-08-10 | Initial draft — org-folder layout, clone manifest, reset stash, almanac pattern generalized; homestead-affairs + live forge-play / terpsi-programs org shells. |
