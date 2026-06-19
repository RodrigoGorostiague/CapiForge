PRAGMA foreign_keys = ON;

CREATE TABLE nodes (
  node_id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  invitation_fingerprint TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL CHECK (status IN ('pending','active','revoked')),
  last_seen_at TEXT
);

CREATE TABLE project_owners (
  project_id TEXT PRIMARY KEY,
  owner_node_id TEXT NOT NULL REFERENCES nodes(node_id),
  assigned_by_human_actor_id TEXT NOT NULL,
  assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE claim_leases (
  claim_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  node_id TEXT NOT NULL REFERENCES nodes(node_id),
  agent_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  plan TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active','renewed','released','expired')),
  lease_started_at TEXT NOT NULL,
  lease_expires_at TEXT NOT NULL
);

CREATE UNIQUE INDEX idx_claim_leases_one_active
ON claim_leases(project_id, task_id)
WHERE status IN ('active','renewed');

CREATE TABLE mutation_routes (
  route_id TEXT PRIMARY KEY,
  source_node_id TEXT NOT NULL REFERENCES nodes(node_id),
  destination_project_id TEXT NOT NULL,
  destination_owner_node_id TEXT NOT NULL REFERENCES nodes(node_id),
  request_kind TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('proposed','routed','accepted','rejected')),
  justification_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sync_announcements (
  announcement_id TEXT PRIMARY KEY,
  node_id TEXT NOT NULL REFERENCES nodes(node_id),
  project_id TEXT,
  sync_status TEXT NOT NULL CHECK (sync_status IN ('healthy','degraded','offline')),
  summary_json TEXT NOT NULL,
  announced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE notice_approvals (
  approval_id TEXT PRIMARY KEY,
  source_project_id TEXT NOT NULL,
  target_project_id TEXT NOT NULL,
  notice_recorded_at TEXT NOT NULL,
  approved_by_human_actor_id TEXT NOT NULL,
  approval_status TEXT NOT NULL CHECK (approval_status IN ('approved','revoked')),
  routed_to_owner_node_id TEXT NOT NULL REFERENCES nodes(node_id)
);

CREATE TABLE enrollment_events (
  event_id TEXT PRIMARY KEY,
  node_id TEXT NOT NULL REFERENCES nodes(node_id),
  event_type TEXT NOT NULL CHECK (event_type IN ('invited','enrolled','revoked')),
  actor_human_id TEXT,
  recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_claim_leases_lookup ON claim_leases(project_id, task_id, status, lease_expires_at);
CREATE INDEX idx_mutation_routes_lookup ON mutation_routes(destination_project_id, status, created_at);
CREATE INDEX idx_sync_announcements_lookup ON sync_announcements(node_id, announced_at);
