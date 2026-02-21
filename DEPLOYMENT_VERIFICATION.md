# 🚀 DEPLOYMENT VERIFICATION GUIDE
## Intelligent Email Assistant - AI Worker Integration

**Status:** ✅ PRODUCTION-READY
**Date:** 2026-02-16
**Changes:** AI Summarization Worker Integration (Final Hardening PR)

---

## 📦 CHANGES SUMMARY

### Files Modified

1. **backend/infrastructure/worker_entry.py**
   - Added `start_ai_worker()` function
   - Integrated AI worker spawn in `main()`
   - AI worker runs as daemon thread alongside email sync worker

2. **render.yaml**
   - Added `AI_SUMM_ENABLED=true` environment variable
   - Added AI worker configuration (model, tokens, temperature, etc.)
   - Enhanced deployment documentation with worker architecture notes

3. **DEPLOYMENT_VERIFICATION.md** (this file)
   - Created comprehensive verification guide

---

## ✅ PRE-DEPLOYMENT CHECKLIST

### 1. Render Dashboard - Environment Variables

Verify these environment variables are set in Render Dashboard:

**CRITICAL (Required for AI Worker):**
- [ ] `MISTRAL_API_KEY` - From Mistral AI dashboard
- [ ] `SUPABASE_URL` - From Supabase project settings
- [ ] `SUPABASE_SERVICE_KEY` - From Supabase project settings
- [ ] `FERNET_KEY` - Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

**Worker Configuration (Auto-set via render.yaml):**
- [ ] `AI_SUMM_ENABLED=true` (enables AI worker)
- [ ] `WORKER_MODE=true` (enables email sync worker)
- [ ] `AI_MODEL=mistral-small-latest`
- [ ] `AI_MAX_TOKENS=800`
- [ ] `AI_TEMPERATURE=0.3`
- [ ] `AI_MAX_CHARS=4000`
- [ ] `AI_MAX_ATTEMPTS=5`
- [ ] `AI_JOBS_BATCH=5`
- [ ] `AI_IDLE_SLEEP=5`

### 2. Supabase - Database Schema

Verify these tables exist (run `backend/sql/setup_schema.sql` if not):

**Required Tables:**
- [ ] `ai_jobs` (job queue)
- [ ] `email_ai_summaries` (cached summaries)
- [ ] `emails` (email source data)
- [ ] `credentials` (OAuth tokens)
- [ ] `schema_version` (must be v3)

**Required Indexes:**
- [ ] `ai_jobs_poll_idx ON (status, run_after, created_at)`
- [ ] `ai_jobs_uq ON (job_type, account_id, gmail_message_id)`
- [ ] `email_ai_summaries_uq ON (account_id, gmail_message_id, prompt_version)`

**Required RPC Function:**
- [ ] `ai_claim_jobs(p_job_type, p_limit, p_worker_id)` with `FOR UPDATE SKIP LOCKED`

### 3. Code Integrity

Verify these changes are present in your codebase:

**worker_entry.py:**
```python
# Line ~176-185: New function
def start_ai_worker():
    """AI Summarization Worker - Processes ai_jobs queue using Mistral."""
    print("[AI-WORKER] Starting AI Summarization Worker Loop...")
    try:
        from backend.infrastructure.ai_summarizer_entry import main as ai_worker_main
        ai_worker_main()
    except Exception as e:
        print(f"[FATAL] [AI-WORKER] Failed to start: {e}")
```

**worker_entry.py main():**
```python
# Line ~195-196: Environment check
worker_mode = os.getenv("WORKER_MODE", "false").lower() == "true"
ai_summ_enabled = os.getenv("AI_SUMM_ENABLED", "false").lower() == "true"

# Line ~210-216: AI worker spawn
if ai_summ_enabled:
    print("[START] [BOOT] AI Summarization enabled - spawning AI worker")
    ai_thread = threading.Thread(target=start_ai_worker, daemon=True)
    ai_thread.start()
    print("[OK] [BOOT] AI Worker thread spawned successfully")
```

---

## 🧪 POST-DEPLOYMENT TESTING

### Test 1: Worker Startup Verification

**Expected Logs on Render:**
```
[START] [BOOT] Running in Hybrid Mode (API + Background Worker)
[START] [BOOT] AI Summarization enabled - spawning AI worker
[OK] [BOOT] AI Worker thread spawned successfully
[AI-WORKER] Starting worker: <hostname>-<pid>
[AI-WORKER] Config: BATCH=5, IDLE_SLEEP=5s
[AI-WORKER] Entering main loop
[NET] [BOOT] API server listening on 0.0.0.0:8888
```

**Action:** Check Render logs within 1 minute of deployment.

**Success Criteria:**
- ✅ No `[FATAL]` errors
- ✅ AI worker starts successfully
- ✅ No missing environment variable errors

---

### Test 2: AI Job Processing

**Step 1: Insert Test Job**

Run this in Supabase SQL Editor:

```sql
INSERT INTO public.ai_jobs (
    job_type,
    account_id,
    gmail_message_id,
    status,
    attempts,
    run_after,
    created_at,
    updated_at
) VALUES (
    'email_summarize_v1',
    'test@example.com',
    'test-message-123',
    'queued',
    0,
    NOW(),
    NOW(),
    NOW()
)
ON CONFLICT (job_type, account_id, gmail_message_id) DO NOTHING;
```

**Step 2: Verify Processing**

Wait 10 seconds, then check:

```sql
-- Check job status (should be 'running' or 'succeeded')
SELECT id, status, attempts, locked_by, updated_at
FROM public.ai_jobs
WHERE gmail_message_id = 'test-message-123'
ORDER BY created_at DESC
LIMIT 1;
```

**Expected Results:**
- Status changes: `queued` → `running` → `succeeded`
- `locked_by` contains worker ID (hostname-pid)
- `attempts` = 0 (if successful on first try)

**Step 3: Verify Summary Creation**

```sql
-- Check if summary was written (will fail if test email doesn't exist)
SELECT account_id, gmail_message_id, prompt_version, model,
       created_at, updated_at
FROM public.email_ai_summaries
WHERE gmail_message_id = 'test-message-123';
```

**Note:** This will fail with `EMAIL_NOT_FOUND` error code since test email doesn't exist in `emails` table. This is expected and validates error handling.

**Expected in Logs:**
```
[AI-WORKER] Processing job <job-id> for test@example.com/test-message-123
[AI-WORKER] Job <job-id> failed (type=...)
[AI-WORKER] Job <job-id> requeued with 2min backoff
```

---

### Test 3: Real Email Summarization

**Prerequisites:**
- At least one email exists in `emails` table
- Email has valid `account_id` and `gmail_message_id`

**Step 1: Find Real Email**

```sql
SELECT account_id, gmail_message_id, subject
FROM public.emails
ORDER BY created_at DESC
LIMIT 1;
```

**Step 2: Enqueue Real Job**

```sql
INSERT INTO public.ai_jobs (
    job_type,
    account_id,
    gmail_message_id,
    status,
    run_after
) VALUES (
    'email_summarize_v1',
    '<account_id_from_step1>',
    '<gmail_message_id_from_step1>',
    'queued',
    NOW()
)
ON CONFLICT DO NOTHING;
```

**Step 3: Wait and Verify**

Wait 30 seconds (includes Mistral API call time), then:

```sql
-- Check summary created
SELECT
    summary_json->>'overview' as overview,
    summary_json->>'urgency' as urgency,
    summary_json->'action_items' as action_items,
    model,
    created_at
FROM public.email_ai_summaries
WHERE gmail_message_id = '<gmail_message_id_from_step1>';
```

**Success Criteria:**
- ✅ Summary exists
- ✅ `overview` is populated (max 800 chars)
- ✅ `urgency` is one of: low, medium, high
- ✅ `action_items` is a JSON array
- ✅ `model` = mistral-small-latest

---

### Test 4: Retry Mechanism

**Step 1: Trigger Failure**

Set invalid Mistral API key temporarily in Render:

```
AI_SUMM_ENABLED=true
MISTRAL_API_KEY=invalid-key-for-testing
```

**Step 2: Enqueue Job**

Insert job as in Test 3.

**Step 3: Observe Retry Behavior**

Check job status every 2 minutes:

```sql
SELECT status, attempts, last_error_code,
       run_after, updated_at
FROM public.ai_jobs
WHERE gmail_message_id = '<test_message_id>'
ORDER BY updated_at DESC;
```

**Expected Retry Schedule:**
- Attempt 1: immediate → fails → requeue for +2min
- Attempt 2: after 2min → fails → requeue for +4min
- Attempt 3: after 4min → fails → requeue for +8min
- Attempt 4: after 8min → fails → requeue for +16min
- Attempt 5: after 16min → fails → **status='dead'**

**Success Criteria:**
- ✅ Job retries with exponential backoff
- ✅ After 5 failures, status becomes 'dead'
- ✅ `last_error_code` = "MISTRAL_FAILED"

**Step 4: Restore Valid Key**

Set correct `MISTRAL_API_KEY` in Render and redeploy.

---

## 🔍 MONITORING QUERIES

### Active Jobs

```sql
SELECT
    status,
    COUNT(*) as count,
    MIN(created_at) as oldest,
    MAX(created_at) as newest
FROM public.ai_jobs
GROUP BY status
ORDER BY status;
```

**Healthy State:**
- `queued`: 0-10 (depends on email volume)
- `running`: 0-5 (worker batch size)
- `succeeded`: growing over time
- `dead`: 0 (investigate if > 0)

### Recent Summaries

```sql
SELECT
    account_id,
    COUNT(*) as summaries_created,
    MAX(created_at) as last_summary
FROM public.email_ai_summaries
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY account_id;
```

### Failed Jobs (Dead Letter Queue)

```sql
SELECT
    id,
    account_id,
    gmail_message_id,
    attempts,
    last_error_code,
    last_error_at,
    created_at
FROM public.ai_jobs
WHERE status = 'dead'
ORDER BY updated_at DESC
LIMIT 10;
```

**Action if dead jobs found:**
1. Check `last_error_code` for root cause
2. Verify MISTRAL_API_KEY is valid
3. Check email exists in `emails` table
4. Review Render logs for exceptions

---

## 🚨 TROUBLESHOOTING

### Issue: AI Worker Not Starting

**Symptoms:**
- No `[AI-WORKER]` logs in Render
- Jobs stay in `queued` status forever

**Diagnosis:**
1. Check Render logs for startup errors
2. Verify `AI_SUMM_ENABLED=true` in Render Dashboard

**Fix:**
```bash
# In Render Dashboard → Environment
AI_SUMM_ENABLED=true
# Then: Manual Deploy → Clear build cache
```

---

### Issue: All Jobs Fail with MISTRAL_FAILED

**Symptoms:**
- All jobs go to `dead` status
- `last_error_code` = "MISTRAL_FAILED"

**Diagnosis:**
1. Verify `MISTRAL_API_KEY` in Render Dashboard
2. Check Mistral AI dashboard for API quota

**Fix:**
```bash
# In Render Dashboard → Environment
MISTRAL_API_KEY=<valid_key_from_mistral_dashboard>
# Redeploy
```

---

### Issue: Worker Crashes Repeatedly

**Symptoms:**
- `[FATAL] [AI-WORKER]` in logs
- Worker restarts every few seconds

**Diagnosis:**
Check logs for specific error:

```
[FATAL] [AI-WORKER] Failed to start: <error message>
```

**Common Causes:**
1. Missing `SUPABASE_SERVICE_KEY`
2. Invalid `FERNET_KEY`
3. Supabase connection error

**Fix:**
Verify all required env vars are set (see Pre-Deployment Checklist).

---

### Issue: Jobs Processed but No Summaries

**Symptoms:**
- Jobs go to `succeeded` status
- No rows in `email_ai_summaries`

**Diagnosis:**
```sql
SELECT id, status, attempts, last_error_code
FROM public.ai_jobs
WHERE status = 'succeeded'
AND gmail_message_id NOT IN (
    SELECT gmail_message_id FROM email_ai_summaries
)
LIMIT 5;
```

**Common Causes:**
1. Email doesn't exist in `emails` table (EMAIL_NOT_FOUND)
2. Summary write failed (check Render logs)

**Fix:**
Review Render logs for `[AI-WORKER]` error messages during job processing.

---

## 📊 SUCCESS METRICS

After 1 hour of operation, verify:

- [ ] **Worker Uptime**: AI worker logs show continuous operation
- [ ] **Job Processing**: > 0 jobs moved to `succeeded` status
- [ ] **Summary Creation**: > 0 rows in `email_ai_summaries`
- [ ] **Error Rate**: < 5% of jobs in `dead` status
- [ ] **No Crashes**: No `[FATAL]` errors in last hour

---

## 🎯 PRODUCTION READINESS SIGN-OFF

**System Status:** 🟢 PRODUCTION-READY

**Hardening Completed:**
- ✅ Concurrency safety (SKIP LOCKED)
- ✅ Required queue indexes
- ✅ Idempotency constraints
- ✅ Retry cap enforcement (5 attempts → dead)
- ✅ Worker integration and deployment
- ✅ Graceful shutdown handling
- ✅ Structured logging
- ✅ Environment validation

**Next Phase:** Observability & Metrics (Phase 4)

---

**Deployment Approved By:** [Your Name]
**Date:** 2026-02-16
**Version:** v1.0.0-ai-worker-integration
