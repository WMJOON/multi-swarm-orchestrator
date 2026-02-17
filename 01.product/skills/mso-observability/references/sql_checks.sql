-- Basic observability checks
-- Failure cluster by task_name
SELECT task_name, COUNT(*) AS fail_count
FROM audit_logs
WHERE status = 'fail'
GROUP BY task_name
HAVING fail_count >= 2;

-- Retry spike
SELECT COUNT(*) AS total, SUM(transition_repeated) AS retries
FROM audit_logs
WHERE status IS NOT NULL;
