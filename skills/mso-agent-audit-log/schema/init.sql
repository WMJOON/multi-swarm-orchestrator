-- =============================================================
-- Agent Audit Log — SQLite Schema
-- Version: 1.3.0
-- Usage:  sqlite3 02.test/v0.0.1/agent_log.db < init.sql
-- =============================================================

PRAGMA foreign_keys = ON;
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

-- 3. Full-Text Search (FTS5)
-- -------------------------------------------------------------

CREATE VIRTUAL TABLE IF NOT EXISTS audit_logs_fts USING fts5(
    id, task_name, action, notes,
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
    INSERT INTO audit_logs_fts(rowid, id, task_name, action, notes)
    VALUES (NEW.rowid, NEW.id, NEW.task_name, NEW.action, NEW.notes);
END;

CREATE TRIGGER IF NOT EXISTS audit_logs_ad AFTER DELETE ON audit_logs BEGIN
    INSERT INTO audit_logs_fts(audit_logs_fts, rowid, id, task_name, action, notes)
    VALUES ('delete', OLD.rowid, OLD.id, OLD.task_name, OLD.action, OLD.notes);
END;

CREATE TRIGGER IF NOT EXISTS audit_logs_au AFTER UPDATE ON audit_logs BEGIN
    INSERT INTO audit_logs_fts(audit_logs_fts, rowid, id, task_name, action, notes)
    VALUES ('delete', OLD.rowid, OLD.id, OLD.task_name, OLD.action, OLD.notes);
    INSERT INTO audit_logs_fts(rowid, id, task_name, action, notes)
    VALUES (NEW.rowid, NEW.id, NEW.task_name, NEW.action, NEW.notes);
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
