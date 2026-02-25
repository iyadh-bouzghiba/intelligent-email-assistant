# Phase 1 Deployment Checklist

Quick reference for deploying zero-budget production optimizations.

---

## Pre-Deployment Verification

### 1. Verify Environment Variables ✅

```bash
# Required
export MISTRAL_API_KEY="your_mistral_api_key"

# Optional (recommended defaults)
export AI_MODEL="open-mistral-nemo"
export AI_MAX_CHARS="4000"
export AI_MAX_ATTEMPTS="5"
export STRIP_REPLY_CHAINS="true"
```

**Verification**:
```bash
python -c "import os; print('MISTRAL_API_KEY:', 'SET' if os.getenv('MISTRAL_API_KEY') else 'MISSING')"
```

---

### 2. Install Dependencies ✅

```bash
# Navigate to backend
cd backend

# Install beautifulsoup4 for HTML parsing
pip install beautifulsoup4

# Verify installation
python -c "from bs4 import BeautifulSoup; print('BeautifulSoup4: OK')"
python -c "from services.email_preprocessor import EmailPreprocessor; print('Preprocessor: OK')"
python -c "from services.token_counter import TokenCounter; print('Token Counter: OK')"
```

---

### 3. Run Phase 1 Tests ✅

```bash
# Test email preprocessor
python -m services.email_preprocessor

# Expected output:
# Original: 370 chars
# Cleaned: 76 chars
# Reduction: 79.5%

# Test token counter
python -m services.token_counter

# Expected output:
# Test 1: Short email - Should bypass: True
# Test 2: Medium email - Within limits: True (OK)
# Test 3: Very long email - Within limits: True (OK)

# Test full pipeline
python test_phase1_pipeline.py

# Expected output:
# [STATS] Total reduction: 76.4%
# [READY] MISTRAL API CALL CONFIGURATION
# [COST] Free tier protection: [ACTIVE]
```

---

## Deployment Steps

### Step 1: Backup Current System

```bash
# Create backup branch
git checkout -b backup-pre-phase1
git add .
git commit -m "Backup before Phase 1 deployment"

# Switch back to main branch
git checkout main
```

---

### Step 2: Restart AI Worker

```bash
# Stop current AI worker (if running)
pkill -f ai_summarizer_worker

# Start Phase 1 enhanced worker
cd backend
nohup python -m infrastructure.ai_summarizer_worker > logs/ai_worker.log 2>&1 &

# Verify worker started
tail -f logs/ai_worker.log

# Expected logs:
# [AI-WORKER] Worker started with batch_size=5
# [AI-WORKER] Claimed X jobs
# [AI-WORKER] Preprocessing saved X% tokens
# [AI-WORKER] Mistral call succeeded (model=open-mistral-nemo)
```

---

### Step 3: Monitor Initial Processing

```bash
# Watch worker logs for 5 minutes
tail -f logs/ai_worker.log | grep -E "(WORKER|Preprocessing|Mistral)"

# Look for:
# ✅ "Preprocessing saved XX% tokens" (should be 40-76%)
# ✅ "Mistral call succeeded (model=open-mistral-nemo)"
# ✅ No "EXCEEDS LIMIT" errors
# ✅ No "429" rate limit errors (or successful retries)
```

---

### Step 4: Database Validation

```sql
-- Check recent AI summaries
SELECT
    account_id,
    gmail_message_id,
    model,
    LENGTH(summary_text) as summary_length,
    created_at
FROM email_ai_summaries
WHERE created_at > NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC
LIMIT 10;

-- Expected:
-- model = 'open-mistral-nemo'
-- summary_length < 200 chars (Phase 1 limit)

-- Check job success rate
SELECT
    status,
    COUNT(*) as count
FROM ai_jobs
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY status;

-- Expected:
-- succeeded: high count
-- queued: low count
-- running: 0-3 (concurrency limit)
-- failed/dead: minimal
```

---

### Step 5: Frontend Validation

```bash
# Open frontend and sync emails
cd ../frontend
npm run dev

# Manual verification:
# 1. Click sync button
# 2. Wait 10-30 seconds for summaries to appear
# 3. Verify summaries are concise (< 200 chars)
# 4. Check that action items are present (if applicable)
# 5. Verify urgency badges (low/medium/high)
```

---

## Monitoring & Validation

### Key Metrics to Monitor

#### 1. Token Reduction Rate
```bash
# Check worker logs for preprocessing stats
grep "Preprocessing saved" logs/ai_worker.log | tail -20

# Expected: 40-76% reduction
```

#### 2. API Success Rate
```bash
# Check for Mistral API errors
grep -i "mistral.*failed" logs/ai_worker.log

# Should be minimal or zero
```

#### 3. Rate Limit Handling
```bash
# Check for 429 retries
grep -i "429.*retry" logs/ai_worker.log

# Expected: Retries should succeed after backoff
```

#### 4. Concurrency Control
```bash
# Check database for running jobs
psql -c "SELECT COUNT(*) FROM ai_jobs WHERE status='running';"

# Expected: 0-3 (never exceeds semaphore limit)
```

---

## Rollback Plan (If Needed)

### Quick Rollback

```bash
# 1. Stop Phase 1 worker
pkill -f ai_summarizer_worker

# 2. Restore backup files
git checkout backup-pre-phase1

# 3. Restart old worker
cd backend
nohup python -m infrastructure.ai_summarizer_worker > logs/ai_worker.log 2>&1 &

# 4. Verify old worker running
tail -f logs/ai_worker.log
```

---

## Success Indicators ✅

After 24 hours, verify:

✅ **Token Reduction**: Worker logs show 40-76% preprocessing savings
✅ **API Success**: Mistral API calls succeeding without 429 errors
✅ **Summaries Generated**: email_ai_summaries table growing
✅ **Frontend Display**: Summaries appearing in email cards
✅ **No Crashes**: Worker process stable (uptime > 24h)
✅ **Free Tier Compliance**: No API billing alerts

---

## Troubleshooting

### Issue: Worker not preprocessing

**Symptom**: Logs don't show "Preprocessing saved X% tokens"

**Solution**:
```bash
# Verify imports
python -c "from services.email_preprocessor import EmailPreprocessor; print('OK')"

# Restart worker
pkill -f ai_summarizer_worker
python -m infrastructure.ai_summarizer_worker
```

---

### Issue: 429 Rate Limit Errors

**Symptom**: Worker logs show "Rate limit hit (429)"

**Expected Behavior**: Worker should retry after 10s → 30s → 60s

**Verification**:
```bash
grep "429.*retry" logs/ai_worker.log

# Should show retry attempts with increasing delays
```

**Action**: Monitor for successful retries. If persistent, reduce concurrency:
```python
# In ai_summarizer_worker.py
MAX_CONCURRENT_REQUESTS = 2  # Reduce from 3
```

---

### Issue: Summaries too long

**Symptom**: Summaries exceed 200 chars

**Verification**:
```sql
SELECT gmail_message_id, LENGTH(summary_text)
FROM email_ai_summaries
WHERE LENGTH(summary_text) > 200
LIMIT 5;
```

**Root Cause**: Mistral not respecting max_tokens parameter

**Solution**: Already handled in Phase 1 with hard truncation:
```python
summary_json["overview"] = str(summary_json["overview"])[:200]
```

---

### Issue: Worker crashes

**Symptom**: Worker process exits unexpectedly

**Diagnosis**:
```bash
# Check last 100 lines of log
tail -100 logs/ai_worker.log

# Check for Python errors
grep -i "traceback\|error\|exception" logs/ai_worker.log | tail -20
```

**Common Causes**:
1. Missing dependencies (beautifulsoup4)
2. Database connection issues
3. Mistral API key invalid

**Solution**: Verify environment and restart worker

---

## Post-Deployment (48 Hours Later)

### Performance Audit

```sql
-- Token savings analysis
SELECT
    COUNT(*) as total_summaries,
    AVG(LENGTH(summary_text)) as avg_summary_length,
    MIN(created_at) as first_summary,
    MAX(created_at) as last_summary
FROM email_ai_summaries
WHERE created_at > NOW() - INTERVAL '48 hours';

-- Job success rate
SELECT
    status,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as percentage
FROM ai_jobs
WHERE created_at > NOW() - INTERVAL '48 hours'
GROUP BY status;

-- Expected:
-- succeeded: > 95%
-- queued: < 3%
-- failed/dead: < 2%
```

---

## Next Steps After Successful Deployment

Once Phase 1 is stable for 48 hours:

1. ✅ **Document Learnings**: Update MEMORY.md with observed patterns
2. ✅ **Optimize Limits**: Adjust token limits based on real-world data
3. ✅ **Plan Phase 2**: Consider advanced categorization, thread summaries
4. ✅ **Scale Testing**: Test with multiple accounts simultaneously

---

**Deployment Owner**: [Your Name]
**Deployment Date**: [Date]
**Phase 1 Status**: ✅ READY FOR PRODUCTION
