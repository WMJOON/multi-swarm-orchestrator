-- =============================================================
-- Agent Audit Log — Migration v1.3.0 → v1.4.0
-- Adds: node_snapshots table, indexes, FTS5, triggers, lineage view
-- Idempotent: all CREATE statements use IF NOT EXISTS
-- =============================================================

PRAGMA foreign_keys = ON;

-- 1. node_snapshots table
-- -------------------------------------------------------------

CREATE TABLE IF NOT EXISTS node_snapshots (
    id TEXT PRIMARY KEY
       CHECK (id LIKE 'SNAP-%' AND length(trim(id)) > 5),
    run_id TEXT NOT NULL
       CHECK (length(trim(run_id)) > 0),
    node_id TEXT NOT NULL
       CHECK (length(trim(node_id)) > 0),
    node_type TEXT NOT NULL
       CHECK (node_type IN ('commit', 'branch', 'merge')),
    parent_refs TEXT NOT NULL DEFAULT '[]',          -- JSON array of parent node_ids
    tree_hash_type TEXT NOT NULL DEFAULT 'sha256'
       CHECK (tree_hash_type IN ('sha256')),
    tree_hash_ref TEXT,                              -- nullable for root nodes
    agent_role TEXT NOT NULL DEFAULT 'execution'
       CHECK (agent_role IN (
           'provisioning', 'execution', 'handoff',
           'branching', 'critic_judge', 'sentinel'
       )),
    phase INTEGER NOT NULL DEFAULT 2
       CHECK (phase BETWEEN 1 AND 4),
    input_artifact_uri TEXT,
    output_artifact_uri TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
       CHECK (status IN (
           'pending', 'active', 'committed', 'merged',
           'rolled_back', 'failed'
       )),
    merge_policy TEXT,                               -- JSON object, for merge nodes only
    fallback_target TEXT,                            -- absolute SHA ref for rollback
    metadata TEXT DEFAULT '{}',                      -- JSON object
    related_audit_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (related_audit_id) REFERENCES audit_logs(id) ON DELETE SET NULL
);

-- 2. Indexes
-- -------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_snapshots_run_id ON node_snapshots(run_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_node_id ON node_snapshots(node_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_node_type ON node_snapshots(node_type);
CREATE INDEX IF NOT EXISTS idx_snapshots_tree_hash_ref ON node_snapshots(tree_hash_ref);
CREATE INDEX IF NOT EXISTS idx_snapshots_status ON node_snapshots(status);
CREATE INDEX IF NOT EXISTS idx_snapshots_phase ON node_snapshots(phase);

-- 3. FTS5
-- -------------------------------------------------------------

CREATE VIRTUAL TABLE IF NOT EXISTS node_snapshots_fts USING fts5(
    id, node_id, node_type, status,
    content='node_snapshots',
    content_rowid='rowid'
);

-- 4. Triggers — FTS sync
-- -------------------------------------------------------------

CREATE TRIGGER IF NOT EXISTS node_snapshots_ai AFTER INSERT ON node_snapshots BEGIN
    INSERT INTO node_snapshots_fts(rowid, id, node_id, node_type, status)
    VALUES (NEW.rowid, NEW.id, NEW.node_id, NEW.node_type, NEW.status);
END;

CREATE TRIGGER IF NOT EXISTS node_snapshots_ad AFTER DELETE ON node_snapshots BEGIN
    INSERT INTO node_snapshots_fts(node_snapshots_fts, rowid, id, node_id, node_type, status)
    VALUES ('delete', OLD.rowid, OLD.id, OLD.node_id, OLD.node_type, OLD.status);
END;

CREATE TRIGGER IF NOT EXISTS node_snapshots_au AFTER UPDATE ON node_snapshots BEGIN
    INSERT INTO node_snapshots_fts(node_snapshots_fts, rowid, id, node_id, node_type, status)
    VALUES ('delete', OLD.rowid, OLD.id, OLD.node_id, OLD.node_type, OLD.status);
    INSERT INTO node_snapshots_fts(rowid, id, node_id, node_type, status)
    VALUES (NEW.rowid, NEW.id, NEW.node_id, NEW.node_type, NEW.status);
END;

-- 5. Trigger — updated_at auto-update
-- -------------------------------------------------------------

CREATE TRIGGER IF NOT EXISTS node_snapshots_update_timestamp AFTER UPDATE ON node_snapshots BEGIN
    UPDATE node_snapshots SET updated_at = CURRENT_TIMESTAMP
    WHERE id = NEW.id AND NEW.updated_at = OLD.updated_at;
END;

-- 6. View — Snapshot Lineage
-- -------------------------------------------------------------

CREATE VIEW IF NOT EXISTS v_snapshot_lineage AS
SELECT
    s.id AS snapshot_id,
    s.run_id,
    s.node_id,
    s.node_type,
    s.parent_refs,
    s.tree_hash_ref,
    s.agent_role,
    s.phase,
    s.status,
    s.created_at,
    a.task_name AS related_task_name,
    a.status AS related_audit_status
FROM node_snapshots s
LEFT JOIN audit_logs a ON s.related_audit_id = a.id
ORDER BY s.created_at ASC;

-- =============================================================
-- Done. Migration v1.3.0 → v1.4.0 complete.
-- =============================================================
