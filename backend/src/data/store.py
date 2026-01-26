import json
import os
import shutil
from typing import Dict, Any, Optional
from src.data.models import ThreadState

class PersistenceManager:
    """
    Manages local persistence of application state (Tokens, Watch State, Threads).
    Saves to a JSON file to ensure data survives server restarts.
    """

    def __init__(self, storage_path: str = "data/store.json"):
        self.storage_path = storage_path
        self._ensure_storage_dir()

    def _ensure_storage_dir(self):
        dirname = os.path.dirname(self.storage_path)
        if dirname and not os.path.exists(dirname):
            os.makedirs(dirname, exist_ok=True)

    def load(self) -> Dict[str, Any]:
        """
        Loads the entire state from the JSON store.
        Returns a dict with 'tokens', 'watch_state', and 'threads'.
        """
        if not os.path.exists(self.storage_path):
            return {
                "tokens": {},
                "watch_state": {},
                "threads": {}
            }

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            
            # integrity checks
            valid_state = {
                "tokens": raw_data.get("tokens", {}),
                "watch_state": raw_data.get("watch_state", {}),
                "threads": {}
            }

            # Re-hydrate Pydantic models for threads
            raw_threads = raw_data.get("threads", {})
            for tid, t_data in raw_threads.items():
                try:
                    # Assuming ThreadState can be validated from the dict
                    valid_state["threads"][tid] = ThreadState.model_validate(t_data)
                except Exception as e:
                    print(f"[WARN] Failed to load thread {tid}: {e}")

            return valid_state

        except Exception as e:
            print(f"[ERROR] Failed to load persistence file: {e}")
            return {"tokens": {}, "watch_state": {}, "threads": {}}

    def save(self, tokens: Dict, watch_state: Dict, threads: Dict[str, ThreadState]):
        """
        Saves the current state to the JSON store.
        """
        try:
            # Serialize threads
            serialized_threads = {}
            for tid, thread_obj in threads.items():
                # model_dump(mode='json') ensures datetime etc are serialized
                serialized_threads[tid] = thread_obj.model_dump(mode='json')

            data = {
                "tokens": tokens,
                "watch_state": watch_state,
                "threads": serialized_threads
            }

            # Atomic write (write to temp then rename)
            temp_path = f"{self.storage_path}.tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            shutil.move(temp_path, self.storage_path)

        except Exception as e:
            print(f"[ERROR] Failed to save persistence file: {e}")


class UserDataStore:
    """
    A high-level store for managing user-specific state,
    such as the last processed Gmail history ID.
    This class acts as a layer on top of the PersistenceManager.
    """

    def __init__(self, persistence_manager: PersistenceManager):
        self._pm = persistence_manager
        self._state = self._pm.load()

    def _save_state(self):
        """Saves the entire application state via the persistence manager."""
        self._pm.save(
            tokens=self._state.get("tokens", {}),
            watch_state=self._state.get("watch_state", {}),
            threads=self._state.get("threads", {})
        )

    def get_last_history_id(self, user_email: str) -> Optional[str]:
        """
        Retrieves the last known history ID for a given user.

        Args:
            user_email: The email address of the user.

        Returns:
            The last history ID as a string, or None if not found.
        """
        return self._state.get("watch_state", {}).get(user_email, {}).get("last_history_id")

    def set_last_history_id(self, user_email: str, history_id: str):
        """
        Updates the last known history ID for a given user.

        Args:
            user_email: The email address of the user.
            history_id: The new history ID to store.
        """
        if "watch_state" not in self._state:
            self._state["watch_state"] = {}
        if user_email not in self._state["watch_state"]:
            self._state["watch_state"][user_email] = {}

        self._state["watch_state"][user_email]["last_history_id"] = history_id
        self._save_state()
