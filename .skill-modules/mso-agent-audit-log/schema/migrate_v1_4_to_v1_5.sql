-- =============================================================
-- Migration: v1.4.0 -> v1.5.0
-- Adds work tracking columns, suggestion_history, analysis views
-- =============================================================

-- 1. New columns on audit_logs
-- -------------------------------------------------------------

ALTER TABLE audit_logs ADD COLUMN work_type TEXT CHECK (work_type IS NULL OR work_type IN ('execution','modification','structure','document','skill','error','review'));
ALTER TABLE audit_logs ADD COLUMN triggered_by TEXT CHECK (triggered_by IS NULL OR triggered_by IN ('user_request','auto','hook'));
ALTER TABLE audit_logs ADD COLUMN duration_sec REAL;
ALTER TABLE audit_logs ADD COLUMN files_affected TEXT;
ALTER TABLE audit_logs ADD COLUMN sprint TEXT;
ALTER TABLE audit_logs ADD COLUMN pattern_tag TEXT;
ALTER TABLE audit_logs ADD COLUMN session_id TEXT;
ALTER TABLE audit_logs ADD COLUMN intent TEXT;

-- 2. New indexes
-- -------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_audit_logs_work_type ON audit_logs(work_type);
CREATE INDEX IF NOT EXISTS idx_audit_logs_session_id ON audit_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_sprint ON audit_logs(sprint);
CREATE INDEX IF NOT EXISTS idx_audit_logs_pattern_tag ON audit_logs(pattern_tag);

-- 3. Suggestion history table
-- -------------------------------------------------------------

CREATE TABLE IF NOT EXISTS suggestion_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    suggestion_type TEXT NOT NULL
       CHECK (suggestion_type IN ('pattern_tag','merge','policy_change','improvement')),
    source_work_type TEXT,
    source_files TEXT,
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

-- 4. FTS5 rebuild (drop + create with new columns)
-- -------------------------------------------------------------

DROP TABLE IF EXISTS audit_logs_fts;

CREATE VIRTUAL TABLE IF NOT EXISTS audit_logs_fts USING fts5(
    id, task_name, action, notes, work_type, intent,
    content='audit_logs',
    content_rowid='rowid'
);

-- Re-populate FTS from existing data
INSERT INTO audit_logs_fts(rowid, id, task_name, action, notes, work_type, intent)
SELECT rowid, id, task_name, action, notes, work_type, intent FROM audit_logs;

-- Recreate triggers
DROP TRIGGER IF EXISTS audit_logs_ai;
DROP TRIGGER IF EXISTS audit_logs_ad;
DROP TRIGGER IF EXISTS audit_logs_au;

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

-- 5. Analysis views
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
