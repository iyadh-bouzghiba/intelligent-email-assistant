-- ============================================================================
-- DATABASE VERIFICATION QUERIES - AI Worker Health Check
-- Execute these in Supabase SQL Editor
-- ============================================================================

-- Query 1: Check Job Status Distribution (Last Hour)
-- Expected: All jobs should be 'succeeded', none stuck in 'running'
SELECT
    status,
    COUNT(*) as count,
    MIN(created_at) as oldest_job,
    MAX(created_at) as newest_job
FROM ai_jobs
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY status
ORDER BY count DESC;

-- Expected Result:
-- status     | count | oldest_job          | newest_job
-- -----------+-------+---------------------+---------------------
-- succeeded  | 30    | 2026-02-25 19:48:00 | 2026-02-25 19:50:00
-- queued     | 0     | NULL                | NULL
-- running    | 0     | NULL                | NULL  ← CRITICAL: Must be 0!

-- ============================================================================

-- Query 2: Check for Stuck Jobs (CRITICAL)
-- Jobs that have been 'running' for > 5 minutes indicate infinite loop
SELECT
    id,
    account_id,
    gmail_message_id,
    status,
    attempts,
    created_at,
    updated_at,
    EXTRACT(EPOCH FROM (NOW() - updated_at)) / 60 as minutes_stuck
FROM ai_jobs
WHERE status = 'running'
  AND updated_at < NOW() - INTERVAL '5 minutes'
ORDER BY updated_at ASC
LIMIT 10;

-- Expected Result: (empty) - No stuck jobs
-- If jobs found here, infinite loop is still occurring!

-- ============================================================================

-- Query 3: Job Success Rate (Last 24 Hours)
SELECT
    COUNT(*) FILTER (WHERE status = 'succeeded') as succeeded_jobs,
    COUNT(*) FILTER (WHERE status = 'failed') as failed_jobs,
    COUNT(*) FILTER (WHERE status = 'dead') as dead_jobs,
    COUNT(*) FILTER (WHERE status = 'running') as running_jobs,
    COUNT(*) FILTER (WHERE status = 'queued') as queued_jobs,
    COUNT(*) as total_jobs,
    ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'succeeded') / COUNT(*), 2) as success_rate_pct
FROM ai_jobs
WHERE created_at > NOW() - INTERVAL '24 hours';

-- Expected: success_rate_pct > 95%

-- ============================================================================

-- Query 4: Summary Generation Rate (Last Hour)
SELECT
    COUNT(*) as total_summaries,
    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 hour') as last_hour,
    COUNT(DISTINCT account_id) as unique_accounts,
    COUNT(DISTINCT gmail_message_id) as unique_emails
FROM email_ai_summaries;

-- Expected: last_hour > 0 (summaries being generated)

-- ============================================================================

-- Query 5: Check for Duplicate Jobs (Should be 0)
-- Unique constraint should prevent duplicates, but verify
SELECT
    account_id,
    gmail_message_id,
    job_type,
    COUNT(*) as duplicate_count
FROM ai_jobs
WHERE created_at > NOW() - INTERVAL '24 hours'
  AND status IN ('queued', 'running')
GROUP BY account_id, gmail_message_id, job_type
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC;

-- Expected Result: (empty) - No duplicates

-- ============================================================================

-- Query 6: Verify Cache Hit Rate
-- High cache hit rate (>90%) indicates summaries are reused efficiently
SELECT
    COUNT(*) FILTER (WHERE summary_json IS NOT NULL) as summaries_exist,
    COUNT(*) as total_emails,
    ROUND(100.0 * COUNT(*) FILTER (WHERE summary_json IS NOT NULL) / COUNT(*), 2) as cache_rate_pct
FROM (
    SELECT
        e.gmail_message_id,
        s.summary_json
    FROM emails e
    LEFT JOIN email_ai_summaries s
        ON e.gmail_message_id = s.gmail_message_id
        AND e.account_id = s.account_id
    WHERE e.created_at > NOW() - INTERVAL '24 hours'
) subquery;

-- Expected: cache_rate_pct > 80%

-- ============================================================================

-- Query 7: Account Isolation Verification
-- Ensure summaries are properly isolated by account
SELECT
    account_id,
    COUNT(*) as summary_count,
    MAX(created_at) as latest_summary
FROM email_ai_summaries
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY account_id
ORDER BY summary_count DESC;

-- Expected: Each account has its own summaries, no cross-contamination

-- ============================================================================

-- Query 8: Check Email-Summary Consistency
-- Emails should have corresponding summaries (or none, not partial)
SELECT
    e.account_id,
    COUNT(DISTINCT e.gmail_message_id) as total_emails,
    COUNT(DISTINCT s.gmail_message_id) as emails_with_summaries,
    COUNT(DISTINCT e.gmail_message_id) - COUNT(DISTINCT s.gmail_message_id) as emails_without_summaries
FROM emails e
LEFT JOIN email_ai_summaries s
    ON e.gmail_message_id = s.gmail_message_id
    AND e.account_id = s.account_id
WHERE e.created_at > NOW() - INTERVAL '24 hours'
GROUP BY e.account_id
ORDER BY e.account_id;

-- Expected: emails_without_summaries should be small (only newest emails)

-- ============================================================================
-- INSTRUCTIONS FOR USER:
--
-- 1. Open Supabase Dashboard → SQL Editor
-- 2. Copy each query above (one at a time)
-- 3. Execute and verify results match expected values
-- 4. Report back with results for critical queries (1, 2, 3)
--
-- CRITICAL CHECKS:
-- - Query 2 MUST return empty (no stuck jobs)
-- - Query 3 success_rate_pct MUST be > 95%
-- - Query 1 'running' count MUST be 0
-- ============================================================================
