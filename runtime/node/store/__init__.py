from __future__ import annotations

import secrets
import sqlite3
from pathlib import Path

from runtime.shared.errors import SurfaceError

UNSET = object()
from runtime.paths import asset_path, schema_path

DEFAULT_NODE_SCHEMA_PATH = schema_path("node-schema.sql")
OWNER_LOCAL_SCHEMA_VERSION = 2

PROJECT_PAGES_CANONICAL_INDEX = "idx_project_pages_canonical_type"
PROJECT_PAGES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS project_pages (
  page_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  page_type TEXT NOT NULL CHECK (page_type IN ('purpose', 'architecture', 'custom')),
  title TEXT NOT NULL,
  content TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_project_pages_canonical_type
ON project_pages(project_id, page_type)
WHERE page_type IN ('purpose', 'architecture');
"""
TASKS_LIFECYCLE_KEY_INDEX = "idx_tasks_project_lifecycle_key"
TASKS_LIFECYCLE_KEY_INDEX_SQL = (
    "CREATE UNIQUE INDEX idx_tasks_project_lifecycle_key "
    "ON tasks(project_id, lifecycle_key) "
    "WHERE lifecycle_key IS NOT NULL"
)


def _resolve_schema_path(schema_path: str | Path | None = None) -> Path:
    if schema_path is None:
        return DEFAULT_NODE_SCHEMA_PATH
    path = Path(schema_path)
    return path if path.is_absolute() else Path.cwd() / path


def connect_node_store(db_path: str | Path, schema_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    initialize_schema = not path.exists() or path.stat().st_size == 0
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        if initialize_schema:
            connection.executescript(_resolve_schema_path(schema_path).read_text())
        else:
            _migrate_owner_local_schema(connection)
        return connection
    except Exception:
        connection.close()
        raise


def _normalize_sql(sql: str | None) -> str:
    return " ".join((sql or "").strip().lower().split())


def _pragma_user_version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def _table_columns(connection: sqlite3.Connection, table_name: str) -> dict[str, dict]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1]: {"cid": row[0], "type": row[2], "notnull": row[3], "default": row[4], "pk": row[5]} for row in rows}


def _index_sql(connection: sqlite3.Connection, index_name: str) -> str | None:
    row = connection.execute("SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?", (index_name,)).fetchone()
    if not row:
        return None
    return row[0]


def _raise_schema_compatibility_error(message: str) -> None:
    raise SurfaceError("LOCAL_SCHEMA_COMPATIBILITY_ERROR", message)


def _migrate_owner_local_schema(connection: sqlite3.Connection) -> None:
    current_version = _pragma_user_version(connection)
    if current_version > OWNER_LOCAL_SCHEMA_VERSION:
        _raise_schema_compatibility_error(
            f"owner-local node schema user_version {current_version} is newer than supported version {OWNER_LOCAL_SCHEMA_VERSION}"
        )

    tasks_columns = _table_columns(connection, "tasks")
    if not tasks_columns:
        _raise_schema_compatibility_error("owner-local node schema is missing the tasks table")
    required_columns = {"task_id", "project_id"}
    missing_required_columns = sorted(required_columns.difference(tasks_columns))
    if missing_required_columns:
        _raise_schema_compatibility_error(
            f"owner-local tasks schema is unsupported; missing required columns: {', '.join(missing_required_columns)}"
        )

    expected_index_sql = _normalize_sql(TASKS_LIFECYCLE_KEY_INDEX_SQL)
    existing_index_sql = _normalize_sql(_index_sql(connection, TASKS_LIFECYCLE_KEY_INDEX))
    lifecycle_key_missing = "lifecycle_key" not in tasks_columns
    index_needs_repair = existing_index_sql != expected_index_sql

    project_pages_missing = not _table_columns(connection, "project_pages")

    if (
        not lifecycle_key_missing
        and not index_needs_repair
        and not project_pages_missing
        and current_version == OWNER_LOCAL_SCHEMA_VERSION
    ):
        return

    try:
        connection.execute("BEGIN")
        if lifecycle_key_missing:
            connection.execute("ALTER TABLE tasks ADD COLUMN lifecycle_key TEXT")
        if index_needs_repair:
            if existing_index_sql:
                connection.execute(f"DROP INDEX {TASKS_LIFECYCLE_KEY_INDEX}")
            connection.execute(TASKS_LIFECYCLE_KEY_INDEX_SQL)
        if project_pages_missing:
            connection.executescript(PROJECT_PAGES_TABLE_SQL)
        connection.execute(f"PRAGMA user_version = {OWNER_LOCAL_SCHEMA_VERSION}")
        connection.commit()
    except sqlite3.DatabaseError as exc:
        connection.rollback()
        _raise_schema_compatibility_error(f"owner-local node schema upgrade failed: {exc}")


class NodeStore:
    def __init__(self, connection: sqlite3.Connection):
        self.db = connection
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")

    @classmethod
    def from_schema(cls, schema_path: str | Path = DEFAULT_NODE_SCHEMA_PATH) -> "NodeStore":
        db = sqlite3.connect(":memory:")
        db.executescript(_resolve_schema_path(schema_path).read_text())
        return cls(db)

    @classmethod
    def from_file(cls, db_path: str | Path, schema_path: str | Path | None = None) -> "NodeStore":
        return cls(connect_node_store(db_path, schema_path))

    def close(self) -> None:
        self.db.close()

    def ensure_local_claim_support(self) -> None:
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS nodes (
              node_id TEXT PRIMARY KEY,
              display_name TEXT NOT NULL,
              invitation_fingerprint TEXT NOT NULL UNIQUE,
              status TEXT NOT NULL CHECK (status IN ('pending','active','revoked')),
              last_seen_at TEXT
            );

            CREATE TABLE IF NOT EXISTS claim_leases (
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

            CREATE UNIQUE INDEX IF NOT EXISTS idx_claim_leases_one_active
            ON claim_leases(project_id, task_id)
            WHERE status IN ('active','renewed');

            CREATE INDEX IF NOT EXISTS idx_claim_leases_lookup
            ON claim_leases(project_id, task_id, status, lease_expires_at);
            """
        )

    def ensure_local_node_actor(self, *, node_id: str, display_name: str = "Adopted local node") -> str:
        self.ensure_local_claim_support()
        row = self.db.execute("SELECT invitation_fingerprint FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
        if row:
            self.db.execute("UPDATE nodes SET status = 'active', display_name = ? WHERE node_id = ?", (display_name, node_id))
            return row["invitation_fingerprint"]
        invitation_fingerprint = secrets.token_hex(16)
        self.db.execute(
            "INSERT INTO nodes (node_id, display_name, invitation_fingerprint, status, last_seen_at) VALUES (?,?,?,?,NULL)",
            (node_id, display_name, invitation_fingerprint, "active"),
        )
        return invitation_fingerprint

    def create_workspace(self, workspace_id: str, canonical_link: str, name: str) -> None:
        self.db.execute("INSERT INTO workspaces VALUES (?,?,?)", (workspace_id, canonical_link, name))

    def upsert_project(self, project_id: str, workspace_id: str, owner_node_id: str, canonical_link: str, name: str) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO projects VALUES (?,?,?,?,?)",
            (project_id, workspace_id, owner_node_id, canonical_link, name),
        )

    def create_audit(self, audit_id: str, project_id: str, state: str, title: str, content: str) -> None:
        self.db.execute("INSERT INTO audits VALUES (?,?,?,?,?,NULL)", (audit_id, project_id, state, title, content))

    def create_task(self, task_id: str, project_id: str, origin_audit_id: str, state: str, priority: str, effort: str, risk: str, task_type: str, description: str, justification_json: str = "{}", execution_context_json: str = "{}", active_claim_session_id: str | None = None, lifecycle_key: str | None = None, blocked_reason: str | None = None, blocked_evidence: str | None = None, blocked_next_step: str | None = None, done_result: str | None = None, done_artifacts: str | None = None, done_references: str | None = None, done_expected_impact: str | None = None) -> None:
        self.db.execute(
            "INSERT INTO tasks (task_id, project_id, origin_audit_id, state, priority, effort, risk, type, description, justification_json, execution_context_json, active_claim_session_id, lifecycle_key, blocked_reason, blocked_evidence, blocked_next_step, done_result, done_artifacts, done_references, done_expected_impact) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                task_id,
                project_id,
                origin_audit_id,
                state,
                priority,
                effort,
                risk,
                task_type,
                description,
                justification_json,
                execution_context_json,
                active_claim_session_id,
                lifecycle_key,
                blocked_reason,
                blocked_evidence,
                blocked_next_step,
                done_result,
                done_artifacts,
                done_references,
                done_expected_impact,
            ),
        )

    def get_task_by_lifecycle_key(self, project_id: str, lifecycle_key: str) -> dict | None:
        row = self.db.execute(
            "SELECT * FROM tasks WHERE project_id = ? AND lifecycle_key = ?",
            (project_id, lifecycle_key),
        ).fetchone()
        return dict(row) if row else None

    def record_task_mutation(self, mutation_id: str, task_id: str, actor_node_id: str, actor_agent_id: str, actor_session_id: str, justification_json: str, authority_mode: str) -> None:
        self.db.execute(
            "INSERT INTO task_mutations (mutation_id,task_id,actor_node_id,actor_agent_id,actor_session_id,justification_json,authority_mode) VALUES (?,?,?,?,?,?,?)",
            (mutation_id, task_id, actor_node_id, actor_agent_id, actor_session_id, justification_json, authority_mode),
        )

    def cache_claim(self, task_id: str, claim_id: str, status: str, lease_expires_at: str, holder_node_id: str, holder_agent_id: str, holder_session_id: str, plan: str) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO claims_local_cache VALUES (?,?,?,?,?,?,?,?)",
            (task_id, claim_id, status, lease_expires_at, holder_node_id, holder_agent_id, holder_session_id, plan),
        )

    def get_cached_claim(self, task_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM claims_local_cache WHERE task_id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def clear_cached_claim(self, task_id: str) -> None:
        self.db.execute("DELETE FROM claims_local_cache WHERE task_id = ?", (task_id,))

    def add_artifact_ref(self, artifact_ref_id: str, project_id: str, canonical_link: str, summary: str, task_id: str | None = None, audit_id: str | None = None) -> None:
        self.db.execute("INSERT INTO artifact_refs VALUES (?,?,?,?,?,?)", (artifact_ref_id, project_id, task_id, audit_id, canonical_link, summary))

    def add_local_document(self, document_id: str, project_id: str, storage_path: str, task_id: str | None = None) -> None:
        self.db.execute("INSERT INTO local_documents VALUES (?,?,?,?, 'local_only')", (document_id, project_id, task_id, storage_path))

    def approve_project_link(self, source_project_id: str, target_project_id: str, approved_by_human_actor_id: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO project_links VALUES (?,?,?)", (source_project_id, target_project_id, approved_by_human_actor_id))

    def record_cross_project_approval(self, approval_id: str, source_project_id: str, target_project_id: str, notice_recorded_at: str, approved_by_human_actor_id: str, approval_status: str = "approved") -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO cross_project_approvals VALUES (?,?,?,?,?,?)",
            (approval_id, source_project_id, target_project_id, notice_recorded_at, approved_by_human_actor_id, approval_status),
        )

    def get_project(self, project_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,)).fetchone()
        return dict(row) if row else None

    def get_workspace(self, workspace_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM workspaces WHERE workspace_id = ?", (workspace_id,)).fetchone()
        return dict(row) if row else None

    def list_workspaces(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT workspace_id, canonical_link, name FROM workspaces ORDER BY workspace_id"
        ).fetchall()
        return [dict(row) for row in rows]

    def list_workspace_projects(self, workspace_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT project_id, owner_node_id, canonical_link, name FROM projects WHERE workspace_id = ? ORDER BY project_id",
            (workspace_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_project_entrypoint(self, project_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM project_entrypoints WHERE project_id = ?", (project_id,)).fetchone()
        return dict(row) if row else None

    def get_task_mutation(self, mutation_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT tm.*, t.project_id FROM task_mutations tm JOIN tasks t ON t.task_id = tm.task_id WHERE tm.mutation_id = ?",
            (mutation_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_task(self, task_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def get_audit(self, audit_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM audits WHERE audit_id = ?", (audit_id,)).fetchone()
        return dict(row) if row else None

    def get_audit_for_project(self, project_id: str, audit_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT * FROM audits WHERE project_id = ? AND audit_id = ?",
            (project_id, audit_id),
        ).fetchone()
        return dict(row) if row else None

    def owner_node_id(self, project_id: str) -> str:
        row = self.get_project(project_id)
        if not row:
            raise ValueError(f"unknown project: {project_id}")
        return row["owner_node_id"]

    def has_project_access(self, node_id: str, project_id: str) -> bool:
        if self.db.execute("SELECT 1 FROM projects WHERE project_id = ? AND owner_node_id = ?", (project_id, node_id)).fetchone():
            return True
        row = self.db.execute(
            "SELECT 1 FROM project_links pl "
            "JOIN projects source ON source.project_id = pl.source_project_id "
            "JOIN projects target ON target.project_id = pl.target_project_id "
            "WHERE ((source.owner_node_id = ? AND target.project_id = ?) "
            "OR (target.owner_node_id = ? AND source.project_id = ?)) LIMIT 1",
            (node_id, project_id, node_id, project_id),
        ).fetchone()
        return row is not None

    def task_belongs_to_project(self, task_id: str, project_id: str) -> bool:
        row = self.db.execute("SELECT 1 FROM tasks WHERE task_id = ? AND project_id = ?", (task_id, project_id)).fetchone()
        return row is not None

    def list_linked_projects(self, project_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT p.project_id, p.canonical_link, p.name FROM project_links pl JOIN projects p ON p.project_id = pl.target_project_id WHERE pl.source_project_id = ? ORDER BY p.project_id",
            (project_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_active_audits(self, project_id: str) -> list[dict]:
        rows = self.db.execute("SELECT audit_id, state, title FROM audits WHERE project_id = ? AND state IN ('draft','published') ORDER BY audit_id", (project_id,)).fetchall()
        return [dict(row) for row in rows]

    def list_project_audits(self, project_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT audit_id, state, title, content FROM audits WHERE project_id = ? ORDER BY audit_id",
            (project_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_project_tasks(self, project_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT task_id, description, state, priority, effort, risk, type, origin_audit_id, "
            "lifecycle_key, blocked_reason, blocked_next_step "
            "FROM tasks WHERE project_id = ? "
            "ORDER BY CASE priority WHEN 'critical' THEN 4 WHEN 'high' THEN 3 WHEN 'medium' THEN 2 ELSE 1 END DESC, task_id",
            (project_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_local_documents(self, project_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT document_id, storage_path FROM local_documents WHERE project_id = ? ORDER BY document_id",
            (project_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_project_pages(self, project_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT page_id, project_id, page_type, title, content, updated_at "
            "FROM project_pages WHERE project_id = ? "
            "ORDER BY CASE page_type WHEN 'purpose' THEN 1 WHEN 'architecture' THEN 2 ELSE 3 END, title",
            (project_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_project_page(self, project_id: str, page_type: str) -> dict | None:
        row = self.db.execute(
            "SELECT page_id, project_id, page_type, title, content, updated_at "
            "FROM project_pages WHERE project_id = ? AND page_type = ?",
            (project_id, page_type),
        ).fetchone()
        return dict(row) if row else None

    def upsert_project_page(
        self,
        *,
        page_id: str,
        project_id: str,
        page_type: str,
        title: str,
        content: str,
        updated_at: str,
    ) -> dict:
        existing = self.get_project_page(project_id, page_type) if page_type in {"purpose", "architecture"} else None
        resolved_page_id = existing["page_id"] if existing else page_id
        self.db.execute(
            """
            INSERT INTO project_pages (page_id, project_id, page_type, title, content, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(page_id) DO UPDATE SET
              title = excluded.title,
              content = excluded.content,
              updated_at = excluded.updated_at
            """,
            (resolved_page_id, project_id, page_type, title, content, updated_at),
        )
        row = self.db.execute("SELECT * FROM project_pages WHERE page_id = ?", (resolved_page_id,)).fetchone()
        return dict(row)

    def list_tasks_for_index(self, project_id: str, index_name: str, as_of: str) -> list[dict]:
        filters = {
            "ready": "t.state = 'ready'",
            "blocked": "t.state = 'blocked'",
            "done": "t.state = 'done'",
            "critical": "t.priority = 'critical' AND t.state NOT IN ('done','cancelled')",
            "expired_claim": "c.task_id IS NOT NULL AND (c.status = 'expired' OR (c.status IN ('active','renewed') AND c.lease_expires_at <= ?))",
        }
        where = filters[index_name]
        params = (project_id, as_of) if index_name == "expired_claim" else (project_id,)
        rows = self.db.execute(
            f"SELECT t.task_id, t.state, t.priority FROM tasks t LEFT JOIN claims_local_cache c ON c.task_id = t.task_id WHERE t.project_id = ? AND {where} ORDER BY CASE t.priority WHEN 'critical' THEN 4 WHEN 'high' THEN 3 WHEN 'medium' THEN 2 ELSE 1 END DESC, t.task_id",
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def is_cross_project_action_allowed(self, source_project_id: str, target_project_id: str) -> bool:
        approved = self.db.execute(
            "SELECT 1 FROM cross_project_approvals WHERE source_project_id = ? AND target_project_id = ? AND approval_status = 'approved'",
            (source_project_id, target_project_id),
        ).fetchone()
        linked = self.db.execute(
            "SELECT 1 FROM project_links a JOIN project_links b ON a.source_project_id = b.target_project_id AND a.target_project_id = b.source_project_id WHERE a.source_project_id = ? AND a.target_project_id = ?",
            (source_project_id, target_project_id),
        ).fetchone()
        return bool(approved and linked)

    def upsert_project_entrypoint(self, project_id: str, owner_node_id: str, summary_json: str, refs: dict[str, str]) -> None:
        self.db.execute(
            "INSERT INTO project_entrypoints VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET owner_node_id=excluded.owner_node_id, summary_json=excluded.summary_json, ready_index_ref=excluded.ready_index_ref, blocked_index_ref=excluded.blocked_index_ref, done_index_ref=excluded.done_index_ref, critical_index_ref=excluded.critical_index_ref, expired_claim_index_ref=excluded.expired_claim_index_ref",
            (project_id, owner_node_id, summary_json, refs["ready"], refs["blocked"], refs["done"], refs["critical"], refs["expired_claim"]),
        )

    def update_task_state(
        self,
        task_id: str,
        *,
        state: str,
        active_claim_session_id: str | None | object = UNSET,
        blocked_reason: str | None | object = UNSET,
        blocked_evidence: str | None | object = UNSET,
        blocked_next_step: str | None | object = UNSET,
        done_result: str | None | object = UNSET,
        done_artifacts: str | None | object = UNSET,
        done_references: str | None | object = UNSET,
        done_expected_impact: str | None | object = UNSET,
    ) -> None:
        current = self.get_task(task_id)
        if not current:
            raise ValueError(f"unknown task: {task_id}")

        def value_or_current(value: str | None | object, field: str):
            return current[field] if value is UNSET else value

        self.db.execute(
            "UPDATE tasks SET state = ?, active_claim_session_id = ?, blocked_reason = ?, blocked_evidence = ?, blocked_next_step = ?, done_result = ?, done_artifacts = ?, done_references = ?, done_expected_impact = ? WHERE task_id = ?",
            (
                state,
                value_or_current(active_claim_session_id, "active_claim_session_id"),
                value_or_current(blocked_reason, "blocked_reason"),
                value_or_current(blocked_evidence, "blocked_evidence"),
                value_or_current(blocked_next_step, "blocked_next_step"),
                value_or_current(done_result, "done_result"),
                value_or_current(done_artifacts, "done_artifacts"),
                value_or_current(done_references, "done_references"),
                value_or_current(done_expected_impact, "done_expected_impact"),
                task_id,
            ),
        )

    def update_task_attribute(
        self,
        task_id: str,
        *,
        priority: str | None = None,
        effort: str | None = None,
        risk: str | None = None,
        task_type: str | None = None,
    ) -> None:
        if not self.get_task(task_id):
            raise ValueError(f"unknown task: {task_id}")
        columns: list[str] = []
        values: list[str] = []
        if priority is not None:
            columns.append("priority = ?")
            values.append(priority)
        if effort is not None:
            columns.append("effort = ?")
            values.append(effort)
        if risk is not None:
            columns.append("risk = ?")
            values.append(risk)
        if task_type is not None:
            columns.append("type = ?")
            values.append(task_type)
        if not columns:
            return
        values.append(task_id)
        self.db.execute(f"UPDATE tasks SET {', '.join(columns)} WHERE task_id = ?", values)

    def sync_task_with_claim(self, task_id: str, *, claim_status: str | None) -> None:
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"unknown task: {task_id}")
        if task["state"] not in {"claimed", "in_progress"}:
            return
        if claim_status in {"active", "renewed"}:
            return
        self.update_task_state(task_id, state="ready", active_claim_session_id=None)

    def export_sync_payload(self, project_id: str, *, as_of: str) -> dict:
        project = self.get_project(project_id)
        if not project:
            raise ValueError(f"unknown project: {project_id}")
        task_rows = self.db.execute(
            "SELECT task_id, state, priority, effort, risk, type, origin_audit_id FROM tasks WHERE project_id = ? ORDER BY task_id",
            (project_id,),
        ).fetchall()
        artifact_rows = self.db.execute(
            "SELECT artifact_ref_id, task_id, audit_id, canonical_link, summary FROM artifact_refs WHERE project_id = ? ORDER BY artifact_ref_id",
            (project_id,),
        ).fetchall()
        return {
            "project_id": project_id,
            "owner_node_id": project["owner_node_id"],
            "as_of": as_of,
            "tasks": [dict(row) for row in task_rows],
            "artifact_refs": [dict(row) for row in artifact_rows],
        }

    def update_audit_content(self, audit_id: str, content: str) -> None:
        self.db.execute("UPDATE audits SET content = ? WHERE audit_id = ?", (content, audit_id))

    def update_audit_state(self, audit_id: str, state: str) -> None:
        self.db.execute("UPDATE audits SET state = ? WHERE audit_id = ?", (state, audit_id))
