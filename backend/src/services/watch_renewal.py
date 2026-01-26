import logging
import datetime
from typing import List

from src.data.store import PersistenceManager
from src.auth.credential_store import CredentialStore
from src.auth.token_manager import TokenManager
from src.integrations.gmail import GmailClient
from src.config import Config

logger = logging.getLogger(__name__)

class WatchRenewalService:
    """
    Handles the periodic renewal of Gmail watches.
    Watches expire every 7 days; this service should be run daily via Cloud Scheduler.
    """

    def __init__(self):
        self.persistence = PersistenceManager()
        self.credential_store = CredentialStore(self.persistence)
        self.token_manager = TokenManager(self.credential_store)

    def renew_all_watches(self):
        """
        Iterates through all persisted watch states and renews them.
        """
        state = self.persistence.load()
        watch_state = state.get("watch_state", {})
        
        logger.info(f"Starting watch renewal for {len(watch_state)} users...")

        for user_id, watch_info in watch_state.items():
            try:
                self._renew_user_watch(user_id, watch_info)
            except Exception as e:
                logger.error(f"Failed to renew watch for user {user_id}: {e}")

    def _renew_user_watch(self, user_id: str, watch_info: dict):
        # 1. Validate Auth
        creds = self.token_manager.get_valid_credentials(user_id)
        if not creds:
            logger.warning(f"Skipping renewal for {user_id}: usage credentials invalid.")
            return

        # 2. Get Client
        # TokenManager updates store, so we can fetch dict
        tokens = self.credential_store.get_credentials(user_id)
        client = GmailClient(tokens)

        # 3. Renew (Start Watch again)
        topic_name = watch_info.get("topic")
        if not topic_name:
             # Fallback or Skip
             logger.warning(f"No topic found for {user_id}, skipping.")
             return

        logger.info(f"Renewing watch for {user_id} on {topic_name}")
        response = client.start_watch(topic_name=topic_name)
        
        # 4. Update State
        watch_info["history_id"] = response.get("historyId")
        watch_info["expiration"] = response.get("expiration")
        watch_info["renewed_at"] = datetime.datetime.utcnow().isoformat()
        
        # Save happens via PersistenceManager if we modify the dict in-place and save
        # But we need to explicitly save the full state
        full_state = self.persistence.load()
        full_state["watch_state"][user_id] = watch_info
        self.persistence.save(
            tokens=full_state.get("tokens"),
            watch_state=full_state["watch_state"],
            threads=full_state.get("threads")
        )
        logger.info(f"Successfully renewed watch for {user_id}. Expires: {response.get('expiration')}")

if __name__ == "__main__":
    # Entry point for Cloud Scheduler
    service = WatchRenewalService()
    service.renew_all_watches()
