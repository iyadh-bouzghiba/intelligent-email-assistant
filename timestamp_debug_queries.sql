-- ============================================================================
-- TIMESTAMP DEBUG QUERIES - Find Root Cause of Mismatch
-- Execute these in Supabase SQL Editor
-- ============================================================================

-- Query 1: Check timestamps for specific emails mentioned in screenshots
-- Look for "Job Market" and "Complete your profile" emails
SELECT
    subject,
    sender,
    date as stored_timestamp,
    gmail_message_id,
    account_id,
    created_at as row_created_at,
    updated_at as row_updated_at
FROM emails
WHERE subject LIKE '%Job Market%'
   OR subject LIKE '%Complete your profile%'
ORDER BY date DESC
LIMIT 10;

-- Expected: Should show the ACTUAL timestamps stored in database
-- Compare these with Gmail web interface timestamps

-- ============================================================================

-- Query 2: Get last 10 emails with all timestamp data
SELECT
    subject,
    sender,
    date as stored_timestamp,
    gmail_message_id,
    account_id,
    EXTRACT(EPOCH FROM date::timestamp) as epoch_seconds,
    TO_CHAR(date::timestamp AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS UTC') as formatted_utc,
    created_at
FROM emails
ORDER BY date DESC
LIMIT 10;

-- Expected: Shows timestamps in multiple formats for comparison
-- epoch_seconds: Can verify against Gmail API internalDate (divide by 1000)
-- formatted_utc: Human-readable UTC timestamp

-- ============================================================================

-- Query 3: Check for timezone inconsistencies
-- Verify if timestamps are being stored in different timezones
SELECT
    subject,
    date as raw_timestamp,
    date::timestamp AT TIME ZONE 'UTC' as utc_time,
    date::timestamp AT TIME ZONE 'America/New_York' as eastern_time,
    date::timestamp AT TIME ZONE 'Europe/Paris' as paris_time,
    EXTRACT(TIMEZONE FROM date::timestamptz) as timezone_offset
FROM emails
ORDER BY date DESC
LIMIT 5;

-- Expected: All timestamps should be in UTC (timezone_offset = 0)

-- ============================================================================

-- Query 4: Compare database timestamps with row creation times
-- Large differences suggest timestamps are being backfilled incorrectly
SELECT
    subject,
    date as email_timestamp,
    created_at as row_created,
    EXTRACT(EPOCH FROM (created_at - date::timestamp)) / 60 as minutes_difference
FROM emails
WHERE created_at > NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC
LIMIT 10;

-- Expected: minutes_difference should be small (< 5 minutes)
-- If large, emails are being assigned timestamps from the past

-- ============================================================================

-- Query 5: Check for duplicate subjects with different timestamps
-- Helps identify if we're fetching wrong version of email
SELECT
    subject,
    COUNT(*) as count,
    ARRAY_AGG(date ORDER BY date DESC) as all_timestamps,
    ARRAY_AGG(gmail_message_id) as all_message_ids
FROM emails
GROUP BY subject
HAVING COUNT(*) > 1
ORDER BY count DESC
LIMIT 10;

-- Expected: Should be empty or very few (same subject = same timestamp)

-- ============================================================================

-- INSTRUCTIONS:
--
-- 1. Execute Query 1 first to find the problematic emails
-- 2. Compare stored_timestamp with Gmail web interface timestamp
-- 3. Execute Query 2 to see multiple timestamp formats
-- 4. Execute Query 3 to verify timezone consistency
-- 5. Execute Query 4 to check for backfill issues
--
-- WHAT TO LOOK FOR:
-- - If stored_timestamp matches Gmail web: Problem is in frontend display
-- - If stored_timestamp is wrong: Problem is in backend retrieval/storage
-- - If timezone_offset != 0: Database is storing in wrong timezone
-- - If minutes_difference is large: Emails are being backdated
-- ============================================================================
