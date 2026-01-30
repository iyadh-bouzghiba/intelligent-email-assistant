import json
import os
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
from backend.src.data.models import ThreadState

class PersistenceManager:
    """
    Manages local persistence of application state (Tokens, Watch State, Threads).
    Supports Multi-Tenant Partitioning (Phase 1: Default Tenant Shim).
    """

    def __init__(self, tenant_id: str = "default"):
        self.tenant_id = tenant_id
        
        # Cloud-Safe Path Resolution
        # backend/src/data/store.py -> backend/data
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent
        self.base_dir = project_root / "data"
        
        # Legacy Path (Backward Compatibility)
        self.legacy_path = self.base_dir / "store.json"
        
        # New Partitioned Path: /data/tenants/{tenant_id}/store.json
        self.tenant_dir = self.base_dir / "tenants" / tenant_id
        self.storage_path = self.tenant_dir / "store.json"
        
        self._ensure_storage_dir()

    def _ensure_storage_dir(self):
        """Ensures the tenant-specific directory exists."""
        if not os.path.exists(self.tenant_dir):
            os.makedirs(self.tenant_dir, exist_ok=True)

    def load(self) -> Dict[str, Any]:
        """
        Loads state with Migration Logic:
        1. Try loading from Tenant Partition.
        2. If missing, Fallback to Legacy Store.
        3. Return empty state if neither exists.
        """
        # 1. Try Tenant Store (Primary)
        if os.path.exists(self.storage_path):
            return self._load_from_file(self.storage_path)
        
        # 2. Fallback to Legacy Store (Migration)
        if os.path.exists(self.legacy_path):
            print(f"📦 [Tenant:{self.tenant_id}] Migrating data from legacy store...")
            data = self._load_from_file(self.legacy_path)
            # Auto-save to new format immediately to complete lazy migration
            self.save(
                tokens=data.get("tokens", {}),
                watch_state=data.get("watch_state", {}),
                threads=data.get("threads", {})  # Only pass dicts here, logic handles deserialization issues
            )
            return data

        # 3. New Tenant, No Legacy Data
        return {
            "tokens": {},
            "watch_state": {},
            "threads": {}
        }

    def _load_from_file(self, path: str) -> Dict[str, Any]:
        """Helper to read and validate a JSON store."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            
            # Structuring
            valid_state = {
                "tokens": raw_data.get("tokens", {}),
                "watch_state": raw_data.get("watch_state", {}),
                "threads": {}
            }

            # Re-hydrate Pydantic models (Robustness)
            raw_threads = raw_data.get("threads", {})
            for tid, t_data in raw_threads.items():
                try:
                    # We store them as dicts in memory in store.py usually? 
                    # Wait, store.py 'load' contract returns Dict[str, Any]
                    # But service.py expects 'threads' to be objects? 
                    # Let's check previous implementation. 
                    # Previous implementation re-hydrated to ThreadState objects.
                    valid_state["threads"][tid] = ThreadState.model_validate(t_data)
                except Exception as e:
                    print(f"[WARN] Failed to load thread {tid}: {e}")

            return valid_state
        except Exception as e:
            print(f"[ERROR] Failed to load store from {path}: {e}")
            return {"tokens": {}, "watch_state": {}, "threads": {}}

    def save(self, tokens: Dict, watch_state: Dict, threads: Dict[str, Any]):
        """
        Saves state to the Tenant Partition.
        """
        try:
            # Serialize threads
            serialized_threads = {}
            for tid, thread_obj in threads.items():
                if hasattr(thread_obj, 'model_dump'):
                    serialized_threads[tid] = thread_obj.model_dump(mode='json')
                else:
                    serialized_threads[tid] = thread_obj # Already dict

            data = {
                "tokens": tokens,
                "watch_state": watch_state,
                "threads": serialized_threads
            }

            # Atomic write to Tenant Partition
            temp_path = f"{self.storage_path}.tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            shutil.move(temp_path, self.storage_path)

        except Exception as e:
            print(f"[ERROR] Failed to save tenant store: {e}")


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
