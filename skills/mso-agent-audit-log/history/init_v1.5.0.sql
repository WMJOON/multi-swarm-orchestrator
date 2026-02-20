-- =============================================================
-- Agent Audit Log — SQLite Schema
-- Version: 1.5.0
-- Usage:  sqlite3 workspace/.mso-context/active/<Run ID>/50_audit/agent_log.db < init.sql
-- =============================================================

PRAGMA foreign_keys = ON;
PRAGMA journal_mode=WAL;
PRAGMA recursive_triggers = OFF;

-- 1. Core Tables
-- -------------------------------------------------------------

CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY                         -- 권장: TASK-001, TASK-20260210...
       CHECK (id LIKE 'TASK-%' AND length(trim(id)) > 5),
    date DATE NOT NULL,
    task_name TEXT NOT NULL
       CHECK (length(trim(task_name)) > 0),
    mode TEXT NOT NULL
       CHECK (length(trim(mode)) > 0),
    action TEXT NOT NULL
       CHECK (length(trim(action)) > 0),
    input_path TEXT,
    output_path TEXT,
    script_path TEXT,
    status TEXT NOT NULL DEFAULT 'in_progress'
       CHECK (status IN ('success', 'fail', 'in_progress')),
    notes TEXT,
    context_for_next TEXT,                      -- 완료 작업에서 권장
    continuation_hint TEXT,
    transition_repeated INTEGER NOT NULL DEFAULT 0
       CHECK (transition_repeated IN (0, 1)),
    transition_reuse INTEGER NOT NULL DEFAULT 0
       CHECK (transition_reuse IN (0, 1)),
    transition_decision INTEGER NOT NULL DEFAULT 0
       CHECK (transition_decision IN (0, 1)),
    work_type TEXT CHECK (work_type IS NULL OR work_type IN ('execution','modification','structure','document','skill','error','review')),
    triggered_by TEXT CHECK (triggered_by IS NULL OR triggered_by IN ('user_request','auto','hook')),
    duration_sec REAL,
    files_affected TEXT,    -- JSON array
    sprint TEXT,
    pattern_tag TEXT,
    session_id TEXT,
    intent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY
       CHECK (id LIKE 'DEC-%' AND length(trim(id)) > 4),
    date DATE NOT NULL,
    title TEXT NOT NULL
       CHECK (length(trim(title)) > 0),
    context TEXT,
    decision_content TEXT,
    requested_by TEXT,
    approved_by TEXT,
    related_audit_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (related_audit_id) REFERENCES audit_logs(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id TEXT NOT NULL,
    type TEXT NOT NULL
       CHECK (length(trim(type)) > 0),
    ref_path TEXT NOT NULL,
    description TEXT,
    FOREIGN KEY (decision_id) REFERENCES decisions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS impacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id TEXT NOT NULL,
    domain TEXT NOT NULL
       CHECK (length(trim(domain)) > 0),
    description TEXT,
    reversibility TEXT
       CHECK (reversibility IS NULL OR reversibility IN ('High', 'Medium', 'Low')),
    FOREIGN KEY (decision_id) REFERENCES decisions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_tags (
    decision_id TEXT NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (decision_id, tag_id),
    FOREIGN KEY (decision_id) REFERENCES decisions(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS document_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    file_path TEXT NOT NULL,
    reference_type TEXT NOT NULL DEFAULT 'mention'
       CHECK (reference_type IN ('mention', 'read', 'edit', 'create')),
    context TEXT,
    related_task_id TEXT,
    referenced_by TEXT NOT NULL DEFAULT 'agent'
       CHECK (referenced_by IN ('user', 'agent')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (related_task_id) REFERENCES audit_logs(id) ON DELETE SET NULL
);

-- 2. Indexes
-- -------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_audit_logs_date ON audit_logs(date);
CREATE INDEX IF NOT EXISTS idx_audit_logs_mode ON audit_logs(mode);
CREATE INDEX IF NOT EXISTS idx_audit_logs_status ON audit_logs(status);
CREATE INDEX IF NOT EXISTS idx_decisions_date ON decisions(date);
CREATE INDEX IF NOT EXISTS idx_decisions_audit ON decisions(related_audit_id);
CREATE INDEX IF NOT EXISTS idx_evidence_decision ON evidence(decision_id);
CREATE INDEX IF NOT EXISTS idx_impacts_decision ON impacts(decision_id);
CREATE INDEX IF NOT EXISTS idx_impacts_domain ON impacts(domain);
CREATE INDEX IF NOT EXISTS idx_doc_refs_path ON document_references(file_path);
CREATE INDEX IF NOT EXISTS idx_doc_refs_session ON document_references(session_id);
CREATE INDEX IF NOT EXISTS idx_doc_refs_created ON document_references(created_at);
CREATE INDEX IF NOT EXISTS idx_doc_refs_related_task ON document_references(related_task_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_work_type ON audit_logs(work_type);
CREATE INDEX IF NOT EXISTS idx_audit_logs_session_id ON audit_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_sprint ON audit_logs(sprint);
CREATE INDEX IF NOT EXISTS idx_audit_logs_pattern_tag ON audit_logs(pattern_tag);

-- 3. Full-Text Search (FTS5)
-- -------------------------------------------------------------

CREATE VIRTUAL TABLE IF NOT EXISTS audit_logs_fts USING fts5(
    id, task_name, action, notes, work_type, intent,
    content='audit_logs',
    content_rowid='rowid'
);

CREATE VIRTUAL TABLE IF NOT EXISTS decisions_fts USING fts5(
    id, title, context, decision_content,
    content='decisions',
    content_rowid='rowid'
);

-- 4. Triggers — FTS sync
-- -------------------------------------------------------------

CREATE TRIGGER IF NOT EXISTS audit_logs_ai AFTER INSERT ON audit_logs BEGIN
    INSERT INTO audit_logs_fts(rowid, id, task_name, action, notes, work_type, intent)
    VALUES (NEW.rowid, NEW.id, NEW.task_name, NEW.action, NEW.notes, NEW.work_type, NEW.intent);
END;

CREATE TRIGGER IF NOT EXISTS audit_logs_ad AFTER DELETE ON audit_logs BEGIN
    INSERT INTO audit_logs_fts(audit_logs_fts, rowid, id, task_name, action, notes, work_type, intent)
    VALUES ('delete', OLD.rowid, OLD.id, OLD.task_name, OLD.action, OLD.notes, OLD.work_type, OLD.intent);
END;

CREATE TRIGGER IF NOT EXISTS audit_logs_au AFTER UPDATE ON audit_logs BEGIN
    INSERT INTO audit_logs_fts(audit_logs_fts, rowid, id, task_name, action, notes, work_type, intent)
    VALUES ('delete', OLD.rowid, OLD.id, OLD.task_name, OLD.action, OLD.notes, OLD.work_type, OLD.intent);
    INSERT INTO audit_logs_fts(rowid, id, task_name, action, notes, work_type, intent)
    VALUES (NEW.rowid, NEW.id, NEW.task_name, NEW.action, NEW.notes, NEW.work_type, NEW.intent);
END;

CREATE TRIGGER IF NOT EXISTS decisions_ai AFTER INSERT ON decisions BEGIN
    INSERT INTO decisions_fts(rowid, id, title, context, decision_content)
    VALUES (NEW.rowid, NEW.id, NEW.title, NEW.context, NEW.decision_content);
END;

CREATE TRIGGER IF NOT EXISTS decisions_ad AFTER DELETE ON decisions BEGIN
    INSERT INTO decisions_fts(decisions_fts, rowid, id, title, context, decision_content)
    VALUES ('delete', OLD.rowid, OLD.id, OLD.title, OLD.context, OLD.decision_content);
END;

CREATE TRIGGER IF NOT EXISTS decisions_au AFTER UPDATE ON decisions BEGIN
    INSERT INTO decisions_fts(decisions_fts, rowid, id, title, context, decision_content)
    VALUES ('delete', OLD.rowid, OLD.id, OLD.title, OLD.context, OLD.decision_content);
    INSERT INTO decisions_fts(rowid, id, title, context, decision_content)
    VALUES (NEW.rowid, NEW.id, NEW.title, NEW.context, NEW.decision_content);
END;

-- 5. Triggers — updated_at auto-update
-- -------------------------------------------------------------

CREATE TRIGGER IF NOT EXISTS audit_logs_update_timestamp AFTER UPDATE ON audit_logs BEGIN
    UPDATE audit_logs SET updated_at = CURRENT_TIMESTAMP
    WHERE id = NEW.id AND NEW.updated_at = OLD.updated_at;
END;

CREATE TRIGGER IF NOT EXISTS decisions_update_timestamp AFTER UPDATE ON decisions BEGIN
    UPDATE decisions SET updated_at = CURRENT_TIMESTAMP
    WHERE id = NEW.id AND NEW.updated_at = OLD.updated_at;
END;

-- 6. Views — Document Reference Analytics
-- -------------------------------------------------------------

CREATE VIEW IF NOT EXISTS v_user_document_frequency AS
SELECT
    file_path,
    COUNT(*) as reference_count,
    MAX(created_at) as last_referenced,
    GROUP_CONCAT(DISTINCT reference_type) as reference_types
FROM document_references
WHERE referenced_by = 'user'
GROUP BY file_path
ORDER BY reference_count DESC;

CREATE VIEW IF NOT EXISTS v_agent_document_frequency AS
SELECT
    file_path,
    COUNT(*) as reference_count,
    MAX(created_at) as last_referenced,
    GROUP_CONCAT(DISTINCT reference_type) as reference_types
FROM document_references
WHERE referenced_by = 'agent'
GROUP BY file_path
ORDER BY reference_count DESC;

CREATE VIEW IF NOT EXISTS v_document_frequency AS
SELECT
    file_path,
    referenced_by,
    COUNT(*) as reference_count,
    MAX(created_at) as last_referenced
FROM document_references
GROUP BY file_path, referenced_by
ORDER BY reference_count DESC;

CREATE VIEW IF NOT EXISTS v_recent_user_documents AS
SELECT file_path, reference_type, context, created_at
FROM document_references
WHERE referenced_by = 'user'
ORDER BY created_at DESC
LIMIT 20;

CREATE VIEW IF NOT EXISTS v_open_followups AS
SELECT id, date, task_name, mode, continuation_hint
FROM audit_logs
WHERE status = 'success'
  AND continuation_hint IS NOT NULL
  AND length(trim(continuation_hint)) > 0
ORDER BY date DESC, id DESC;

-- =============================================================
-- Done. Verify with:  .tables  /  .schema
-- =============================================================

-- 7. Feedback Automation (v1.3.0)
-- -------------------------------------------------------------

CREATE TABLE IF NOT EXISTS user_feedback (
    id TEXT PRIMARY KEY
       CHECK (id LIKE 'FB-%' AND length(trim(id)) > 3),
    date DATE NOT NULL,
    user_id TEXT,
    feedback_text TEXT NOT NULL
       CHECK (length(trim(feedback_text)) > 0),
    source_ref_path TEXT,
    impact_domain TEXT NOT NULL DEFAULT 'workflow'
       CHECK (length(trim(impact_domain)) > 0),
    impact_summary TEXT,
    reversibility TEXT
       CHECK (reversibility IS NULL OR reversibility IN ('High', 'Medium', 'Low')),
    related_audit_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (related_audit_id) REFERENCES audit_logs(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_user_feedback_date ON user_feedback(date);
CREATE INDEX IF NOT EXISTS idx_user_feedback_audit ON user_feedback(related_audit_id);

CREATE TRIGGER IF NOT EXISTS user_feedback_ai AFTER INSERT ON user_feedback BEGIN
    INSERT INTO decisions (
        id, date, title, context, decision_content,
        requested_by, approved_by, related_audit_id
    ) VALUES (
        'DEC-' || NEW.id,
        NEW.date,
        '[AUTO] user feedback decision: ' || NEW.id,
        'auto-generated from user_feedback',
        NEW.feedback_text,
        COALESCE(NEW.user_id, 'user'),
        'auto-feedback-rule',
        NEW.related_audit_id
    );

    INSERT INTO evidence (decision_id, type, ref_path, description)
    VALUES (
        'DEC-' || NEW.id,
        'user_feedback',
        COALESCE(NEW.source_ref_path, 'feedback:' || NEW.id),
        NEW.feedback_text
    );

    INSERT INTO impacts (decision_id, domain, description, reversibility)
    VALUES (
        'DEC-' || NEW.id,
        NEW.impact_domain,
        COALESCE(NEW.impact_summary, NEW.feedback_text),
        COALESCE(NEW.reversibility, 'Medium')
    );
END;

CREATE TRIGGER IF NOT EXISTS user_feedback_update_timestamp AFTER UPDATE ON user_feedback BEGIN
    UPDATE user_feedback SET updated_at = CURRENT_TIMESTAMP
    WHERE id = NEW.id AND NEW.updated_at = OLD.updated_at;
END;

-- 8. Node Snapshots — Git-metaphor State Model (v1.4.0)
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
    parent_refs TEXT NOT NULL DEFAULT '[]',
    tree_hash_type TEXT NOT NULL DEFAULT 'sha256'
       CHECK (tree_hash_type IN ('sha256')),
    tree_hash_ref TEXT,
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
    merge_policy TEXT,
    fallback_target TEXT,
    metadata TEXT DEFAULT '{}',
    related_audit_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (related_audit_id) REFERENCES audit_logs(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_run_id ON node_snapshots(run_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_node_id ON node_snapshots(node_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_node_type ON node_snapshots(node_type);
CREATE INDEX IF NOT EXISTS idx_snapshots_tree_hash_ref ON node_snapshots(tree_hash_ref);
CREATE INDEX IF NOT EXISTS idx_snapshots_status ON node_snapshots(status);
CREATE INDEX IF NOT EXISTS idx_snapshots_phase ON node_snapshots(phase);

CREATE VIRTUAL TABLE IF NOT EXISTS node_snapshots_fts USING fts5(
    id, node_id, node_type, status,
    content='node_snapshots',
    content_rowid='rowid'
);

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

CREATE TRIGGER IF NOT EXISTS node_snapshots_update_timestamp AFTER UPDATE ON node_snapshots BEGIN
    UPDATE node_snapshots SET updated_at = CURRENT_TIMESTAMP
    WHERE id = NEW.id AND NEW.updated_at = OLD.updated_at;
END;

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

-- 9. Suggestion History (v1.5.0)
-- -------------------------------------------------------------

CREATE TABLE IF NOT EXISTS suggestion_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    suggestion_type TEXT NOT NULL
       CHECK (suggestion_type IN ('pattern_tag','merge','policy_change','improvement')),
    source_work_type TEXT,
    source_files TEXT,       -- JSON array
    suggestion_text TEXT NOT NULL,
    accepted INTEGER DEFAULT 0
       CHECK (accepted IN (0, 1)),
    rejected_weight REAL DEFAULT 0.0,
    related_audit_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (related_audit_id) REFERENCES audit_logs(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_suggestion_history_type ON suggestion_history(suggestion_type);
CREATE INDEX IF NOT EXISTS idx_suggestion_history_accepted ON suggestion_history(accepted);

-- 10. Analysis Views (v1.5.0)
-- -------------------------------------------------------------

CREATE VIEW IF NOT EXISTS v_work_type_distribution AS
SELECT
    work_type,
    COUNT(*) AS cnt,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM audit_logs), 1) AS pct,
    SUM(CASE WHEN status = 'fail' THEN 1 ELSE 0 END) AS fail_cnt,
    ROUND(AVG(duration_sec), 2) AS avg_duration_sec
FROM audit_logs
WHERE work_type IS NOT NULL
GROUP BY work_type
ORDER BY cnt DESC;

CREATE VIEW IF NOT EXISTS v_pattern_candidates AS
SELECT
    work_type,
    files_affected,
    COUNT(*) AS occurrence,
    GROUP_CONCAT(DISTINCT id) AS audit_ids
FROM audit_logs
WHERE work_type IS NOT NULL AND files_affected IS NOT NULL
GROUP BY work_type, files_affected
HAVING COUNT(*) >= 3
ORDER BY occurrence DESC;

CREATE VIEW IF NOT EXISTS v_file_hotspots AS
SELECT
    files_affected,
    COUNT(*) AS total_refs,
    SUM(CASE WHEN status = 'fail' THEN 1 ELSE 0 END) AS fail_refs,
    GROUP_CONCAT(DISTINCT work_type) AS work_types
FROM audit_logs
WHERE files_affected IS NOT NULL
GROUP BY files_affected
ORDER BY fail_refs DESC, total_refs DESC;
