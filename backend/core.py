from typing import Dict, List, Any
import asyncio
import json
import os
from datetime import datetime

from backend.services.gmail_engine import run_engine
from backend.services.summarizer import Summarizer
from backend.data.models import ThreadState, ThreadSummary
from backend.infrastructure.credential_store import CredentialStore
from backend.infrastructure.persistence import persistence


def _load_token_data() -> dict:
    """Load OAuth token from CredentialStore (primary) or GMAIL_CREDENTIALS_PATH (fallback).
    Returns empty dict on any failure; run_engine will warn and return []."""
    # PRIMARY: Read from CredentialStore (matches OAuth callback write path)
    try:
        credential_store = CredentialStore(persistence)
        tokens = credential_store.load_credentials("default")
        if tokens:
            print("[OK] [CORE] Loaded Gmail credentials from CredentialStore (default)")
            return tokens
    except Exception as e:
        print(f"[WARN] [CORE] Failed to load from CredentialStore: {e}")

    # FALLBACK: Read from file (legacy path)
    path = os.getenv("GMAIL_CREDENTIALS_PATH", "")
    if not path:
        print("[WARN] [CORE] No credentials available. OAuth flow required.")
        return {}
    try:
        with open(path) as f:
            tokens = json.load(f)
            print(f"[OK] [CORE] Loaded Gmail credentials from file: {path}")
            return tokens
    except Exception as e:
        print(f"[WARN] [CORE] Failed to load Gmail credentials from {path}: {e}")
        return {}


class EmailAssistant:
    def __init__(self):
        self.brain = Summarizer()
        self.threads: Dict[str, ThreadState] = {}
        self._token_data = _load_token_data()

    def process_emails(self):
        """
        Legacy Logic for the API to fetch and summarize emails.
        Now enhanced to include thread context for the platform adapter.
        """
        emails = run_engine(self._token_data)
        if not emails:
            return []
        
        results = []
        for email in emails:
            summary = self.brain.summarize(email)
            t_id = email.get('threadId', email.get('id', 'unknown'))
            
            results.append({
                "thread_id": t_id,
                "subject": email.get('subject', 'No Subject'),
                "summary": summary
            })
        return results

    async def process_all_accounts(self):
        """
        Architectural Adapter: Bridges single-tenant domain logic 
        with the multi-account capable shell.
        
        NOW CALLS process_emails() INTERNALLY per strict contract.
        """
        print("🧠 Brain: Executing Single-Tenant Processing Sequence (Wrapped)...")
        
        # Offload blocking Legacy Domain Logic to thread
        results = await asyncio.to_thread(self.process_emails)
        
        if not results:
            print("📭 Brain: No new threads to analyze.")
            return

        print(f"🧠 Brain: Adapting {len(results)} legacy items to Platform State...")
        
        for item in results:
            # Map Dict -> Domain Model
            summary_model = ThreadSummary(
                thread_id=item["thread_id"],
                overview=item["summary"],
                key_points=[],
                action_items=[],
                confidence_score=0.95
            )
            
            # Update State
            self.threads[item["thread_id"]] = ThreadState(
                thread_id=item["thread_id"],
                history=[], 
                current_summary=summary_model,
                last_updated=datetime.now()
            )
            
        print(f"✅ Brain: Intelligence Sync Complete. {len(self.threads)} threads active.")

def main():
    """Logic for running directly via terminal (python core.py)"""
    print("🚀 INTELLIGENT EMAIL ASSISTANT: Starting Orchestration...\n")
    
    assistant = EmailAssistant()
    results = assistant.process_emails()
    
    if not results:
        print("📭 No emails found or engine failed.")
        return

    print(f"🧠 Brain Initialized. Summarizing {len(results)} emails...\n")
    
    print("✨ AI-Generated Executive Briefing ✨\n")
    print("="*60)
    
    for item in results:
        priority = "Medium"
        if "PRIORITY: High" in item["summary"]: priority = "High"
        elif "PRIORITY: Low" in item["summary"]: priority = "Low"
        
        print(f"[{priority}] {item['subject']}")
        print(f"{item['summary']}")
        print("-" * 60)

    print("\n✅ Phase 3 Complete: Executive Briefing Delivered.")

if __name__ == "__main__":
    main()