## Exploration: real node bootstrap and minimal CLI

### Current State
The V1 runtime already has real domain and coordination modules (`runtime/node/*`, `runtime/coordinator/*`), stable SQLite schemas (`storage/*.sql`), deterministic MCP surface contracts (`contracts/mcp-surface.md`), and integration/e2e tests that prove owner routing, claims, entrypoint indexes, and coordinator-backed mutation flow. But bootstrap is still fragmented: `NodeStore.from_schema()` defaults to in-memory SQLite for tests, persistent file setup is duplicated in `tests/e2e/multi_node_runtime_test.py` and `scripts/demo_v1_runtime.py`, and the only executable CLI-like entrypoint today is the demo script.

There is no reusable runtime bootstrap layer that opens a node from disk, initializes its schema, binds coordinator dependencies, and exposes a stable operator-facing command surface. So "real node bootstrap" in this codebase should mean replacing script-only assembly with a first-class runtime bootstrap path for a persistent local node. A "minimal CLI" should then expose only the smallest commands needed to create and inspect that bootstrapped node without inventing broader workflow automation.

### Affected Areas
- `scripts/demo_v1_runtime.py` — currently contains the only real persistent bootstrap flow and duplicates connection/setup logic that should move into reusable runtime bootstrap code.
- `runtime/node/store/__init__.py` — currently offers only in-memory schema bootstrap via `from_schema()`, so persistent node opening/initialization boundaries likely start here or beside it.
- `runtime/node/mcp/__init__.py` — defines the operational surface that a real bootstrapped node instance would need to expose after assembly.
- `runtime/coordinator/mcp/__init__.py` — relevant if V1.1 decides bootstrap must optionally attach coordinator-backed claims/routing from day one.
- `storage/node-schema.sql` and `storage/coordinator-schema.sql` — define the durable state a bootstrap layer must initialize deterministically.
- `tests/e2e/multi_node_runtime_test.py` — already proves file-backed SQLite runtime behavior and is the best reference for a credible bootstrap target.
- `contracts/mcp-surface.md` and `openspec/specs/mcp-cli-surface/spec.md` — define the CLI/MCP contract expectations, so new CLI scope must stay narrow and deterministic.
- `README.md` — documents current bootstrap assumptions and would need alignment once bootstrap becomes a product surface instead of a demo detail.

### Approaches
1. **Extract bootstrap only** — move file-backed store/coordinator assembly into reusable helpers, but keep the user-facing entrypoint as the existing demo script.
   - Pros: Lowest implementation cost, removes duplication fast, improves testability.
   - Cons: Not a credible V1.1 product slice because operators still do not get a real supported CLI surface.
   - Effort: Low

2. **Owner-local node bootstrap + read/status CLI** — add a reusable persistent node bootstrap layer and a tiny CLI that can initialize a node workspace/project and inspect entrypoint/status locally, while leaving multi-node enrollment and routed flows script/test driven.
   - Pros: Smallest credible product slice, matches current local-first architecture, avoids overcommitting to unstable coordinator UX, converts bootstrap into a real supported path.
   - Cons: Does not yet cover full LAN enrollment or claim/routing workflows from the CLI.
   - Effort: Medium

3. **Full multi-node bootstrap CLI** — bootstrap owner node, worker node, coordinator, enrollment, and initial demo operations through one integrated CLI.
   - Pros: Most impressive end-to-end story, aligns with the broader V1 topology immediately.
   - Cons: Too large for a safe V1.1 slice, mixes infrastructure setup with workflow automation, likely exceeds the 400-line review budget quickly.
   - Effort: High

### Recommendation
Recommend **Approach 2: owner-local node bootstrap + read/status CLI**.

The repository already proves the runtime model, but the gap is PRODUCTIZATION, not domain design. The smallest credible V1.1 slice is to formalize a persistent single-node bootstrap path and expose a deterministic CLI around that node. That means one local node can be initialized from disk, seeded with workspace/project ownership metadata, and queried through a tiny supported command surface. This gives the project a real runtime starting point without prematurely packaging coordinator enrollment, lease orchestration, or routed cross-node flows.

The most likely V1.1 command scope is:
- `capiforge node init` — create/open a node home, initialize SQLite schema, and seed one workspace/project owned by the local node.
- `capiforge node status` — report filesystem/db paths, local node identity, and known workspace/project summary.
- `capiforge project entrypoint` (or equivalent read command) — prove the bootstrapped node can return deterministic traversal data through the real runtime surface.

That slice is small, testable, and honest: it turns today's script-driven bootstrap into a supported runtime capability while deferring higher-risk multi-node automation.

### Risks
- "Real bootstrap" is ambiguous unless proposal/spec explicitly say whether coordinator enrollment is in or out for V1.1.
- If CLI scope expands into claims, routing, or enrollment now, the change likely blows past the 400-line review budget and should be chained.
- The current demo script mixes bootstrap, data seeding, and workflow walkthrough; extracting the right reusable boundary without copying that design mistake requires discipline.
- Existing specs define CLI behavior at the contract level, but there is not yet a concrete packaging/module convention for an installed executable.

### Ready for Proposal
Yes — but the orchestrator should tell the user that V1.1 should be scoped explicitly to **persistent single-node bootstrap plus minimal read-only/operator CLI**, and should defer coordinator automation unless they want a larger chained change.
