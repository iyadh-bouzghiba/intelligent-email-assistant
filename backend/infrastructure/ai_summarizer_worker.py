"""
AI Email Summarization Worker

Worker-only Mistral pipeline for email summarization using queue-based architecture.
Consumes jobs from ai_jobs table via RPC and writes to email_ai_summaries.

CRITICAL: This module must NEVER be called from API request handlers.
"""

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from backend.infrastructure.supabase_store import SupabaseStore
from backend.engine.nlp_engine import MistralEngine

logger = logging.getLogger(__name__)

# Constants
JOB_TYPE = "email_summarize_v1"
PROMPT_VERSION = "summ_v1"
AI_MAX_CHARS = int(os.getenv("AI_MAX_CHARS", "4000"))
AI_MAX_ATTEMPTS = int(os.getenv("AI_MAX_ATTEMPTS", "5"))


class AISummarizerWorker:
    """
    Standalone worker for AI email summarization.

    Workflow:
    1. Claim jobs via ai_claim_jobs RPC
    2. Fetch email data (subject, sender, date, body)
    3. Mask PII and truncate
    4. Check cache via input_hash
    5. Call Mistral if not cached
    6. Write to email_ai_summaries
    7. Update job status with backoff
    """

    def __init__(self, store: SupabaseStore, mistral_engine: MistralEngine):
        self.store = store
        self.mistral = mistral_engine

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

    def _mask_and_truncate(self, text: str) -> str:
        """
        Mask PII and truncate content.

        Masks:
        - Email addresses
        - Phone numbers (basic patterns)
        - URLs

        Truncates to AI_MAX_CHARS.
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

        # Truncate
        return text[:AI_MAX_CHARS]

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

    def _call_mistral(self, email_data: Dict[str, Any], masked_body: str) -> Optional[Dict[str, Any]]:
        """
        Call Mistral for JSON-only summarization.

        Returns dict with keys: overview, action_items, urgency
        """
        prompt = f"""Analyze this email and provide a JSON response with exactly these fields:
- overview: concise summary (max 800 chars)
- action_items: array of action items (max 8 items, each max 140 chars)
- urgency: one of "low", "medium", or "high"

Email metadata:
From: {email_data.get('sender', 'Unknown')}
Subject: {email_data.get('subject', 'No subject')}

Email content (masked/truncated):
{masked_body}

Respond ONLY with valid JSON matching this exact structure.
"""

        try:
            # Force JSON output
            summary_json = self.mistral.generate_json(
                prompt=prompt,
                model=os.getenv("AI_MODEL", "mistral-small-latest"),
                max_tokens=int(os.getenv("AI_MAX_TOKENS", "800")),
                temperature=float(os.getenv("AI_TEMPERATURE", "0.3")),
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

            # Truncate overview and action items
            summary_json["overview"] = str(summary_json["overview"])[:800]
            summary_json["action_items"] = [
                str(item)[:140] for item in summary_json["action_items"][:8]
            ]

            return summary_json

        except Exception as e:
            err_type = type(e).__name__
            logger.error(f"[AI-WORKER] Mistral call failed (type={err_type})")
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
        Process a single claimed job.

        Workflow:
        1. Fetch email
        2. Mask + truncate + hash
        3. Check cache
        4. Call Mistral if needed
        5. Write summary
        6. Update job status
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

            # 2. Mask + truncate
            body = email_row.get("body", "")
            masked_body = self._mask_and_truncate(body)

            # Construct input for hashing
            subject = email_row.get("subject", "")
            sender = email_row.get("sender", "")
            masked_input = f"Subject: {subject}\nFrom: {sender}\n\n{masked_body}"
            input_hash = self._compute_input_hash(masked_input)

            # 3. Check cache
            if self._check_cache(account_id, gmail_message_id, input_hash):
                # Cache hit - mark succeeded without calling Mistral
                self._mark_job_succeeded(job_id)
                return

            # 4. Call Mistral
            summary_json = self._call_mistral(email_row, masked_body)
            if not summary_json:
                self._mark_job_failed(job_id, attempts, "MISTRAL_FAILED")
                return

            # 5. Write summary
            model = self.mistral.model if hasattr(self.mistral, 'model') else "mistral-small-latest"
            self._write_summary(account_id, gmail_message_id, input_hash, summary_json, model)

            # 6. Mark succeeded
            self._mark_job_succeeded(job_id)

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
