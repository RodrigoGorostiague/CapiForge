PRAGMA foreign_keys = ON;
PRAGMA user_version = 1;

CREATE TABLE workspaces (
  workspace_id TEXT PRIMARY KEY,
  canonical_link TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL
);

CREATE TABLE projects (
  project_id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
  owner_node_id TEXT NOT NULL,
  canonical_link TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL
);

CREATE TABLE project_entrypoints (
  project_id TEXT PRIMARY KEY REFERENCES projects(project_id) ON DELETE CASCADE,
  owner_node_id TEXT NOT NULL,
  summary_json TEXT NOT NULL,
  ready_index_ref TEXT,
  blocked_index_ref TEXT,
  done_index_ref TEXT,
  critical_index_ref TEXT,
  expired_claim_index_ref TEXT
);

CREATE TABLE audits (
  audit_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  state TEXT NOT NULL CHECK (state IN ('draft','published','closed','superseded')),
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  addendum_of_audit_id TEXT REFERENCES audits(audit_id)
);

CREATE TRIGGER audits_closed_immutable
BEFORE UPDATE ON audits
FOR EACH ROW WHEN OLD.state = 'closed'
BEGIN
  SELECT RAISE(ABORT, 'closed audits are immutable');
END;

CREATE TABLE tasks (
  task_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  origin_audit_id TEXT NOT NULL REFERENCES audits(audit_id),
  state TEXT NOT NULL CHECK (state IN ('proposed','ready','claimed','in_progress','blocked','done','cancelled')),
  priority TEXT NOT NULL CHECK (priority IN ('low','medium','high','critical')),
  effort TEXT NOT NULL CHECK (effort IN ('low','medium','high')),
  risk TEXT NOT NULL CHECK (risk IN ('low','medium','high')),
  type TEXT NOT NULL CHECK (type IN ('fix','feature','audit_followup','doc','refactor','ops')),
  description TEXT NOT NULL,
  justification_json TEXT NOT NULL,
  execution_context_json TEXT NOT NULL,
  active_claim_session_id TEXT,
  lifecycle_key TEXT,
  blocked_reason TEXT,
  blocked_evidence TEXT,
  blocked_next_step TEXT,
  done_result TEXT,
  done_artifacts TEXT,
  done_references TEXT,
  done_expected_impact TEXT,
  CHECK (state != 'blocked' OR (blocked_reason IS NOT NULL AND blocked_evidence IS NOT NULL AND blocked_next_step IS NOT NULL)),
  CHECK (state != 'done' OR (done_result IS NOT NULL AND done_artifacts IS NOT NULL AND done_references IS NOT NULL AND done_expected_impact IS NOT NULL)),
  CHECK (state NOT IN ('claimed','in_progress') OR active_claim_session_id IS NOT NULL)
);

CREATE TABLE task_relations (
  task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
  related_task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
  relation_type TEXT NOT NULL CHECK (relation_type IN ('depends_on','blocks','relates_to','duplicates')),
  PRIMARY KEY (task_id, related_task_id, relation_type)
);

CREATE TABLE task_mutations (
  mutation_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
  actor_node_id TEXT NOT NULL,
  actor_agent_id TEXT NOT NULL,
  actor_session_id TEXT NOT NULL,
  justification_json TEXT NOT NULL,
  authority_mode TEXT NOT NULL CHECK (authority_mode IN ('canonical','proposal','human_override')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER canonical_mutations_require_owner
BEFORE INSERT ON task_mutations
FOR EACH ROW
WHEN NEW.authority_mode = 'canonical' AND NEW.actor_node_id != (
  SELECT p.owner_node_id
  FROM tasks t
  JOIN projects p ON p.project_id = t.project_id
  WHERE t.task_id = NEW.task_id
)
BEGIN
  SELECT RAISE(ABORT, 'canonical writes require owner node');
END;

CREATE TABLE claims_local_cache (
  task_id TEXT PRIMARY KEY REFERENCES tasks(task_id) ON DELETE CASCADE,
  claim_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active','renewed','released','expired')),
  lease_expires_at TEXT NOT NULL,
  holder_node_id TEXT NOT NULL,
  holder_agent_id TEXT NOT NULL,
  holder_session_id TEXT NOT NULL,
  plan TEXT NOT NULL
);

CREATE TABLE nodes (
  node_id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  invitation_fingerprint TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL CHECK (status IN ('pending','active','revoked')),
  last_seen_at TEXT
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

CREATE INDEX idx_claim_leases_lookup ON claim_leases(project_id, task_id, status, lease_expires_at);

CREATE UNIQUE INDEX idx_tasks_project_lifecycle_key
ON tasks(project_id, lifecycle_key)
WHERE lifecycle_key IS NOT NULL;

CREATE TABLE artifact_refs (
  artifact_ref_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  task_id TEXT REFERENCES tasks(task_id) ON DELETE SET NULL,
  audit_id TEXT REFERENCES audits(audit_id) ON DELETE SET NULL,
  canonical_link TEXT NOT NULL,
  summary TEXT NOT NULL
);

CREATE TABLE local_documents (
  document_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  task_id TEXT REFERENCES tasks(task_id) ON DELETE SET NULL,
  storage_path TEXT NOT NULL,
  retention_scope TEXT NOT NULL DEFAULT 'local_only' CHECK (retention_scope = 'local_only')
);

CREATE TABLE project_links (
  source_project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  target_project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  approved_by_human_actor_id TEXT NOT NULL,
  PRIMARY KEY (source_project_id, target_project_id)
);

CREATE TABLE cross_project_approvals (
  approval_id TEXT PRIMARY KEY,
  source_project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  target_project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  notice_recorded_at TEXT NOT NULL,
  approved_by_human_actor_id TEXT NOT NULL,
  approval_status TEXT NOT NULL CHECK (approval_status IN ('approved','revoked'))
);

CREATE TABLE index_queue (
  queue_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  reason TEXT NOT NULL,
  queued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tasks_project_state_priority ON tasks(project_id, state, priority);
CREATE INDEX idx_projects_workspace ON projects(workspace_id);
