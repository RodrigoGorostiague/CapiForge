## Exploration: shared-local-first MCP knowledge layer

### Current State
The repository is still in bootstrap state: there is no application source, no detected stack, and no test harness. The only authoritative project artifact is `openspec/config.yaml`, which already sets the direction: local-first, secure, extensible, MCP-friendly, and explicit about trust boundaries and machine-sync behavior. This means the exploration is primarily a product and system architecture exercise, not a code integration exercise.

The real problem is not “replace Notion” by itself. The problem is repeated knowledge bootstrapping across machines and agents: each new opencode environment must rediscover structure, verify context, rebuild indexes, and reconnect tooling state. The proposed system therefore needs to act as a shared knowledge substrate for opencode, gentle-ai, and engram, while preserving local ownership, offline usability, and strong machine trust controls.

### Affected Areas
- `openspec/config.yaml` — authoritative bootstrap constraints for security, local-first tradeoffs, and MCP sharing expectations.
- `openspec/changes/shared-local-first-mcp-knowledge-layer/exploration.md` — exploration artifact for the named change.
- `openspec/specs/` — future source-of-truth specs will likely need domains for storage, sync, auth/trust, MCP API, and indexing/discovery.
- `.atl/skill-registry.md` — confirms there are no additional project-specific implementation skills or stack conventions to constrain the design.

### Approaches
1. **Single-user replicated knowledge repo** — Each machine keeps a local embedded store and syncs through a replicated append-only change log backed by user-controlled storage (for example Git, Syncthing-style folder replication, or pluggable file transport).
   - Pros: Strong local-first posture, simple offline behavior, user owns data path, cheap to self-host, deterministic event history is agent-friendly.
   - Cons: Conflict resolution and machine trust are harder, multi-writer consistency needs careful design, weak fit for real-time shared locks or coordination.
   - Effort: Medium

2. **Local-first node plus shared coordinator** — Each machine runs a local daemon with embedded storage, but machines optionally sync through a lightweight self-hosted coordinator that exchanges signed deltas, machine identities, and discovery metadata without becoming the primary source of truth.
   - Pros: Best balance for this problem, keeps local autonomy, simplifies discovery and multi-machine sharing, central service can stay thin and replaceable, cleaner MCP integration surface.
   - Cons: More moving parts than pure replication, requires explicit trust/bootstrap ceremony, coordinator availability affects convenience even if not ownership.
   - Effort: Medium-High

3. **Shared server-first knowledge service with local cache** — A central self-hosted service stores canonical knowledge and exposes MCP/API; each machine keeps a cache for speed and offline reads.
   - Pros: Simplest query model, easiest cross-machine consistency, straightforward ACLs, easiest for agents to discover a single endpoint.
   - Cons: Violates the spirit of local-first, creates a stronger failure/attack target, encourages hidden server dependence, turns offline into degraded mode.
   - Effort: Low-Medium

### Recommendation
Recommend **Approach 2: local-first nodes plus a thin shared coordinator**.

It best matches the actual product problem: repeated machine and agent bootstrapping, not just storage. A pure replicated repo is elegant but pushes too much complexity into conflict handling and discovery. A server-first model is operationally easier but weakens ownership and offline guarantees. The thin-coordinator model preserves local durability as the source of truth on every machine, while adding the minimum shared surface needed for signed delta exchange, machine registration, index discovery, and MCP endpoint consistency.

The likely bounded domains are:
- **Local Knowledge Store** — canonical local persistence, schema/versioning, snapshots, deterministic IDs.
- **Sync Engine** — signed delta log, replay, merge policy, checkpoints, conflict surfacing.
- **Trust & Identity** — machine identity, key management, enrollment, capability grants, revocation.
- **Index & Discovery** — agent-readable catalogs, namespaces, document/entity indexes, deterministic lookup rules.
- **MCP Gateway** — stable tool surface for read/query/write/sync/status operations.
- **Extension Runtime** — pluggable adapters for new sources, projections, embeddings, or transports.

Agent-first expectations should be explicit from the start:
- Storage should prefer append-only records plus materialized views, with stable IDs and explicit schema versions.
- APIs should be deterministic and narrow: `get`, `put`, `query`, `list_namespaces`, `list_indexes`, `sync_status`, `apply_delta`, `resolve_conflict`.
- Discovery should expose a machine-readable manifest describing schemas, namespaces, available indexes, permissions, and sync health.
- Versioning should separate transport schema, storage schema, and MCP contract version.
- MCP integration should assume agents need predictable pagination, bounded responses, explicit error classes, and audit-friendly mutation metadata.

Minimum viable first slice:
- Single-user, multi-machine sync.
- Local embedded store on every machine.
- Thin coordinator for enrollment + signed delta exchange only.
- Read-heavy MCP tools first, limited write paths second.
- Deterministic namespace/index manifest.
- Manual conflict surfacing before automatic merge sophistication.

### Risks
- Trust boundary mistakes could let one compromised machine poison shared knowledge across the fleet.
- If schemas, IDs, and manifests are not deterministic early, agent accessibility will degrade into brittle prompt conventions.
- Overbuilding search/embeddings before core sync and trust will create a flashy but unsafe system.
- Local-first language can become fake if the coordinator silently becomes required for normal operation.

### Ready for Proposal
Yes — the problem is sufficiently framed. The orchestrator should tell the user that the next proposal should define product scope around a local-first knowledge substrate with explicit domains for storage, sync, trust, discovery, and MCP access, and should keep the first slice to signed multi-machine sync plus deterministic agent-facing read APIs.
