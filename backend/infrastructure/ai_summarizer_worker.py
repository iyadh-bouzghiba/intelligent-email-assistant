"""
AI Email Summarization Worker

Worker-only Mistral pipeline for email summarization using queue-based architecture.
Consumes jobs from ai_jobs table via RPC and writes to email_ai_summaries.

CRITICAL: This module must NEVER be called from API request handlers.

ZERO-BUDGET OPTIMIZATIONS (Phase 1):
- Email preprocessing (HTML strip, signatures, reply chains)
- Token counting and smart truncation (4000 token limit)
- Concurrency semaphore (max 3 concurrent Mistral calls)
- 429 rate limit retry with exponential backoff
- Model: open-mistral-nemo (cost-optimized)
"""

import hashlib
import json
import logging
import os
import re
import time
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from backend.infrastructure.supabase_store import SupabaseStore
from backend.engine.nlp_engine import MistralEngine
from backend.services.email_preprocessor import EmailPreprocessor
from backend.services.token_counter import TokenCounter, TokenLimits

logger = logging.getLogger(__name__)

# Constants
JOB_TYPE = "email_summarize_v1"
PROMPT_VERSION = "summ_v1_optimized"  # Updated for Phase 1 optimizations
AI_MAX_CHARS = int(os.getenv("AI_MAX_CHARS", "4000"))
AI_MAX_ATTEMPTS = int(os.getenv("AI_MAX_ATTEMPTS", "5"))

# ZERO-BUDGET CONFIGURATION
# Model: open-mistral-nemo (cost-optimized for free tier)
MISTRAL_MODEL = os.getenv("AI_MODEL", "open-mistral-nemo")
MISTRAL_TEMPERATURE = 0.2  # Fixed for consistency
MISTRAL_MAX_OUTPUT_TOKENS = 300  # Fixed for structured summary

# Concurrency control (prevent free-tier rate limit crashes)
MAX_CONCURRENT_REQUESTS = 3  # Safe limit for free tier

# Rate limit retry configuration
RATE_LIMIT_RETRY_DELAYS = [10, 30, 60]  # Seconds: 10s → 30s → 60s


class AISummarizerWorker:
    """
    Standalone worker for AI email summarization with zero-budget optimizations.

    Workflow (Phase 1 Enhanced):
    1. Claim jobs via ai_claim_jobs RPC
    2. Fetch email data (subject, sender, date, body)
    3. **NEW: Preprocess email (HTML, signatures, reply chains)**
    4. **NEW: Count tokens and smart truncate if needed**
    5. Mask PII
    6. Check cache via input_hash
    7. **NEW: Semaphore-controlled Mistral call with 429 retry**
    8. Write to email_ai_summaries
    9. Update job status with backoff
    """

    # Class-level semaphore for concurrency control (shared across instances)
    _api_semaphore = threading.Semaphore(MAX_CONCURRENT_REQUESTS)

    def __init__(self, store: SupabaseStore, mistral_engine: MistralEngine):
        self.store = store
        self.mistral = mistral_engine

        # ZERO-BUDGET COMPONENTS
        self.preprocessor = EmailPreprocessor(
            strip_html=True,
            remove_signatures=True,
            remove_reply_chains=os.getenv("STRIP_REPLY_CHAINS", "true").lower() == "true",
            normalize_whitespace=True
        )
        self.token_counter = TokenCounter()

    def claim_jobs(self, batch_size: int, worker_id: str) -> list[Dict[str, Any]]:
        """
        Claim jobs atomically using ai_claim_jobs RPC.

        Returns list of claimed job rows.
        """
        try:
            response = self.store.client.rpc(
                "ai_claim_jobs",
                {
                    "p_job_type": JOB_TYPE,
                    "p_limit": batch_size,
                    "p_worker_id": worker_id
                }
            ).execute()

            jobs = response.data if response.data else []
            if jobs:
                logger.info(f"[AI-WORKER] Claimed {len(jobs)} jobs")
            return jobs

        except Exception as e:
            err_type = type(e).__name__
            logger.error(f"[AI-WORKER] RPC claim failed (type={err_type})")
            return []

    def _fetch_email_row(self, account_id: str, gmail_message_id: str) -> Optional[Dict[str, Any]]:
        """Fetch email row selecting only necessary columns."""
        try:
            response = self.store.client.table("emails").select(
                "subject,sender,date,body"
            ).eq("account_id", account_id).eq("gmail_message_id", gmail_message_id).execute()

            if response.data and len(response.data) > 0:
                return response.data[0]
            return None

        except Exception as e:
            err_type = type(e).__name__
            logger.error(f"[AI-WORKER] Email fetch failed for {account_id}/{gmail_message_id} (type={err_type})")
            return None

    def _preprocess_and_prepare(self, text: str, subject: str = "") -> tuple[str, dict]:
        """
        PHASE 1 OPTIMIZATION: Preprocess email and prepare for Mistral call.

        Pipeline:
        1. Preprocess (HTML strip, signatures, reply chains) - saves 40-60% tokens
        2. Token count and smart truncate if needed
        3. Mask PII
        4. Validate token limits

        Returns:
            Tuple of (prepared_text, stats_dict)

        Stats includes:
        - preprocessing_reduction_pct
        - token_count_estimated
        - truncated
        - within_limits
        """
        if not text:
            return "", {"token_count_estimated": 0, "within_limits": True}

        stats = {}

        # Step 1: Preprocess (HTML, signatures, reply chains)
        preprocessed_text, prep_stats = self.preprocessor.preprocess(text, subject)
        stats["preprocessing_reduction_pct"] = prep_stats["reduction_pct"]
        stats["html_stripped"] = prep_stats["html_stripped"]
        stats["signature_removed"] = prep_stats["signature_removed"]

        # Step 2: Token counting and smart truncation
        token_count = self.token_counter.estimate_tokens(preprocessed_text)
        stats["token_count_estimated"] = token_count

        within_limits, _, limit_msg = self.token_counter.check_limits(preprocessed_text)
        stats["within_limits"] = within_limits

        if not within_limits:
            # Smart truncate to fit within limits
            preprocessed_text, trunc_stats = self.token_counter.smart_truncate(
                preprocessed_text,
                target_tokens=TokenLimits.SAFE_INPUT_TOKENS
            )
            stats["truncated"] = True
            stats["truncation_reduction_pct"] = trunc_stats["reduction_pct"]
            stats["token_count_estimated"] = trunc_stats["final_tokens"]
            logger.warning(f"[AI-WORKER] Email truncated: {token_count} → {trunc_stats['final_tokens']} tokens")
        else:
            stats["truncated"] = False

        # Step 3: Mask PII (after preprocessing to avoid masking signatures)
        prepared_text = self._mask_pii(preprocessed_text)

        return prepared_text, stats

    def _mask_pii(self, text: str) -> str:
        """
        Mask PII for privacy.

        Masks:
        - Email addresses
        - Phone numbers
        - URLs
        """
        if not text:
            return ""

        # Mask emails
        text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', text)

        # Mask phone numbers (basic patterns)
        text = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[PHONE]', text)
        text = re.sub(r'\+\d{1,3}\s?\d{1,14}', '[PHONE]', text)

        # Mask URLs
        text = re.sub(r'https?://[^\s<>"{}|\\^`\[\]]+', '[URL]', text)

        return text

    def _compute_input_hash(self, masked_input: str) -> str:
        """Compute SHA256 hash of masked+truncated input for caching."""
        return hashlib.sha256(masked_input.encode('utf-8')).hexdigest()

    def _check_cache(self, account_id: str, gmail_message_id: str, input_hash: str) -> bool:
        """
        Check if summary already exists with same input_hash.

        Returns True if cached (skip Mistral call).
        """
        try:
            response = self.store.client.table("email_ai_summaries").select(
                "id,input_hash"
            ).eq("account_id", account_id).eq(
                "gmail_message_id", gmail_message_id
            ).eq("prompt_version", PROMPT_VERSION).execute()

            if response.data and len(response.data) > 0:
                cached_hash = response.data[0].get("input_hash")
                if cached_hash == input_hash:
                    logger.info(f"[AI-WORKER] Cache hit for {account_id}/{gmail_message_id}")
                    return True

            return False

        except Exception as e:
            err_type = type(e).__name__
            logger.error(f"[AI-WORKER] Cache check failed (type={err_type})")
            return False

    def _call_mistral(self, email_data: Dict[str, Any], prepared_body: str) -> Optional[Dict[str, Any]]:
        """
        PHASE 1 ENHANCED: Call Mistral for JSON-only summarization with zero-budget protections.

        Features:
        - Semaphore-controlled concurrency (max 3 concurrent requests)
        - 429 rate limit retry with exponential backoff (10s → 30s → 60s)
        - Fixed model parameters for cost consistency
        - Token-optimized prompts

        Returns dict with keys: overview, action_items, urgency
        """
        prompt = f"""Analyze this email and provide a JSON response with exactly these fields:
- overview: concise summary (max 200 chars)
- action_items: array of action items (max 5 items, each max 80 chars)
- urgency: one of "low", "medium", or "high"

Email metadata:
From: {email_data.get('sender', 'Unknown')}
Subject: {email_data.get('subject', 'No subject')}

Email content (preprocessed/masked):
{prepared_body}

Respond ONLY with valid JSON matching this exact structure.
"""

        # Semaphore-controlled execution with 429 retry
        with self._api_semaphore:
            for retry_attempt in range(len(RATE_LIMIT_RETRY_DELAYS) + 1):
                try:
                    # ZERO-BUDGET: Fixed model parameters (no env override)
                    summary_json = self.mistral.generate_json(
                        prompt=prompt,
                        model=MISTRAL_MODEL,
                        max_tokens=MISTRAL_MAX_OUTPUT_TOKENS,
                        temperature=MISTRAL_TEMPERATURE,
                    )

                    # Validate required keys
                    required = {"overview", "action_items", "urgency"}
                    if not required.issubset(summary_json.keys()):
                        raise ValueError(f"Missing required keys. Got: {summary_json.keys()}")

                    # Validate urgency enum
                    if summary_json["urgency"] not in ["low", "medium", "high"]:
                        summary_json["urgency"] = "medium"  # fallback

                    # Validate action_items is array
                    if not isinstance(summary_json["action_items"], list):
                        summary_json["action_items"] = []

                    # Truncate to strict limits (Phase 1 cost control)
                    summary_json["overview"] = str(summary_json["overview"])[:200]
                    summary_json["action_items"] = [
                        str(item)[:80] for item in summary_json["action_items"][:5]
                    ]

                    logger.info(f"[AI-WORKER] Mistral call succeeded (model={MISTRAL_MODEL}, temp={MISTRAL_TEMPERATURE})")
                    return summary_json

                except Exception as e:
                    err_type = type(e).__name__
                    err_msg = str(e)

                    # Check if 429 rate limit error
                    is_rate_limit = "429" in err_msg or "rate" in err_msg.lower()

                    if is_rate_limit and retry_attempt < len(RATE_LIMIT_RETRY_DELAYS):
                        # Retry with exponential backoff
                        delay = RATE_LIMIT_RETRY_DELAYS[retry_attempt]
                        logger.warning(
                            f"[AI-WORKER] Rate limit hit (429), retry {retry_attempt + 1}/{len(RATE_LIMIT_RETRY_DELAYS)} "
                            f"after {delay}s backoff"
                        )
                        time.sleep(delay)
                        continue  # Retry

                    # Non-rate-limit error or max retries reached
                    logger.error(f"[AI-WORKER] Mistral call failed after {retry_attempt + 1} attempts (type={err_type})")
                    return None

        return None

    def _write_summary(
        self,
        account_id: str,
        gmail_message_id: str,
        input_hash: str,
        summary_json: Dict[str, Any],
        model: str
    ):
        """Upsert summary to email_ai_summaries."""
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            self.store.client.table("email_ai_summaries").upsert({
                "account_id": account_id,
                "gmail_message_id": gmail_message_id,
                "prompt_version": PROMPT_VERSION,
                "model": model,
                "input_hash": input_hash,
                "summary_json": summary_json,
                "summary_text": summary_json.get("overview", ""),
                "updated_at": now_iso
            }, on_conflict="account_id,gmail_message_id,prompt_version").execute()

            logger.info(f"[AI-WORKER] Summary written for {account_id}/{gmail_message_id}")

        except Exception as e:
            err_type = type(e).__name__
            logger.error(f"[AI-WORKER] Summary write failed (type={err_type})")
            raise

    def _mark_job_succeeded(self, job_id: str):
        """Mark job as succeeded."""
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            self.store.client.table("ai_jobs").update({
                "status": "succeeded",
                "updated_at": now_iso
            }).eq("id", job_id).execute()

        except Exception as e:
            err_type = type(e).__name__
            logger.error(f"[AI-WORKER] Job success update failed for {job_id} (type={err_type})")

    def _mark_job_failed(self, job_id: str, attempts: int, error_code: str):
        """
        Mark job as failed with exponential backoff.

        If attempts >= AI_MAX_ATTEMPTS, mark as 'dead'.
        """
        try:
            new_attempts = attempts + 1
            now_iso = datetime.now(timezone.utc).isoformat()

            if new_attempts >= AI_MAX_ATTEMPTS:
                # Dead letter
                self.store.client.table("ai_jobs").update({
                    "status": "dead",
                    "attempts": new_attempts,
                    "last_error_code": error_code,
                    "last_error_at": now_iso,
                    "updated_at": now_iso
                }).eq("id", job_id).execute()
                logger.warning(f"[AI-WORKER] Job {job_id} marked dead after {new_attempts} attempts")
            else:
                # Exponential backoff: 2^attempts minutes
                backoff_minutes = 2 ** new_attempts
                run_after_iso = (datetime.now(timezone.utc) + timedelta(minutes=backoff_minutes)).isoformat()
                self.store.client.table("ai_jobs").update({
                    "status": "queued",
                    "attempts": new_attempts,
                    "last_error_code": error_code,
                    "last_error_at": now_iso,
                    "run_after": run_after_iso,
                    "locked_at": None,
                    "locked_by": None,
                    "updated_at": now_iso
                }).eq("id", job_id).execute()
                logger.info(f"[AI-WORKER] Job {job_id} requeued with {backoff_minutes}min backoff")

        except Exception as e:
            err_type = type(e).__name__
            logger.error(f"[AI-WORKER] Job failure update failed for {job_id} (type={err_type})")

    def process_job(self, job: Dict[str, Any]):
        """
        PHASE 1 ENHANCED: Process a single claimed job with zero-budget optimizations.

        Workflow:
        1. Fetch email
        2. Preprocess (HTML, signatures, reply chains) - PHASE 1
        3. Token count + smart truncate - PHASE 1
        4. Mask PII + hash
        5. Check cache
        6. Call Mistral (semaphore + retry) - PHASE 1
        7. Write summary
        8. Update job status
        9. Emit Socket.IO event
        """
        job_id = job["id"]
        account_id = job["account_id"]
        gmail_message_id = job["gmail_message_id"]
        attempts = job.get("attempts", 0)

        logger.info(f"[AI-WORKER] Processing job {job_id} for {account_id}/{gmail_message_id}")

        try:
            # 1. Fetch email
            email_row = self._fetch_email_row(account_id, gmail_message_id)
            if not email_row:
                self._mark_job_failed(job_id, attempts, "EMAIL_NOT_FOUND")
                return

            # 2. Preprocess + prepare (PHASE 1: HTML strip, signatures, token limits, PII masking)
            body = email_row.get("body", "")
            subject = email_row.get("subject", "")
            prepared_body, prep_stats = self._preprocess_and_prepare(body, subject)

            # Log preprocessing stats
            if prep_stats.get("preprocessing_reduction_pct", 0) > 0:
                logger.info(
                    f"[AI-WORKER] Preprocessing saved {prep_stats['preprocessing_reduction_pct']:.1f}% tokens "
                    f"(truncated={prep_stats.get('truncated', False)}, "
                    f"est_tokens={prep_stats['token_count_estimated']})"
                )

            # Skip summarization if content is too short
            if self.token_counter.should_bypass_summarization(prepared_body):
                logger.info(f"[AI-WORKER] Email too short to summarize, using raw body as overview")
                # Create minimal summary
                summary_json = {
                    "overview": body[:200] if body else "Empty email",
                    "action_items": [],
                    "urgency": "low"
                }
                # Write minimal summary and mark succeeded
                input_hash = self._compute_input_hash(prepared_body)
                self._write_summary(account_id, gmail_message_id, input_hash, summary_json, MISTRAL_MODEL)
                self._mark_job_succeeded(job_id)
                return

            # 3. Construct input for hashing
            sender = email_row.get("sender", "")
            hashed_input = f"Subject: {subject}\nFrom: {sender}\n\n{prepared_body}"
            input_hash = self._compute_input_hash(hashed_input)

            # 4. Check cache
            if self._check_cache(account_id, gmail_message_id, input_hash):
                # Cache hit - mark succeeded without calling Mistral
                self._mark_job_succeeded(job_id)
                return

            # 5. Call Mistral (PHASE 1: semaphore + 429 retry)
            summary_json = self._call_mistral(email_row, prepared_body)
            if not summary_json:
                self._mark_job_failed(job_id, attempts, "MISTRAL_FAILED")
                return

            # 6. Write summary
            self._write_summary(account_id, gmail_message_id, input_hash, summary_json, MISTRAL_MODEL)

            # 7. Mark succeeded
            self._mark_job_succeeded(job_id)

            # 8. Emit Socket.IO event for real-time frontend updates
            try:
                from backend.api.service import sio
                import asyncio

                asyncio.run(sio.emit("ai_summary_ready", {
                    "account_id": account_id,
                    "gmail_message_id": gmail_message_id,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }))
                logger.info(f"[AI-WORKER] Socket.IO event emitted for {gmail_message_id[:8]}...")
            except Exception as e:
                # Non-critical - Socket.IO emission failure shouldn't break worker
                logger.warning(f"[AI-WORKER] Socket.IO emit failed: {type(e).__name__}")

        except Exception as e:
            err_type = type(e).__name__
            logger.error(f"[AI-WORKER] Job {job_id} failed (type={err_type})")
            self._mark_job_failed(job_id, attempts, "WORKER_EXCEPTION")

    def process_batch(self, batch_size: int, worker_id: str) -> int:
        """
        Claim and process a batch of jobs.

        Returns number of jobs processed.
        """
        jobs = self.claim_jobs(batch_size, worker_id)

        for job in jobs:
            self.process_job(job)

        return len(jobs)
