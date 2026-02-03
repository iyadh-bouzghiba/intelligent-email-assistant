import os
import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from backend.infrastructure.supabase_store import SupabaseStore

class ControlPlane:
    _instance = None
    _policy_cache = {}
    _last_fetch = 0
    _cache_ttl = 60 # Seconds

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ControlPlane, cls).__new__(cls)
            cls._instance.store = SupabaseStore()
        return cls._instance

    def _get_policy(self) -> Dict[str, Any]:
        """Loads policy from cache or Supabase with fail-open logic."""
        now = time.time()
        if now - self._last_fetch < self._cache_ttl and self._policy_cache:
            return self._policy_cache

        try:
            # Fetch global_policy from system_config table
            response = self.store.client.table("system_config") \
                .select("value") \
                .eq("key", "global_policy") \
                .single() \
                .execute()
            
            if response.data:
                self._policy_cache = response.data.get("value", {})
                self._last_fetch = now
                return self._policy_cache
        except Exception as e:
            print(f"[WARN] ControlPlane fetch error: {e}")
            # Fail open: returning last known cache or empty dict
        
        return self._policy_cache or {
            "worker_enabled": True,
            "max_emails_per_cycle": 50,
            "tenant_quota_enabled": False
        }

    def is_worker_enabled(self) -> bool:
        return self._get_policy().get("worker_enabled", True)

    def max_emails_per_cycle(self) -> int:
        return self._get_policy().get("max_emails_per_cycle", 50)

    def get_supported_schema_version(self) -> str:
        """Heuristic check for schema versioning."""
        return "v3"

    def verify_schema(self) -> bool:
        """Validates that the database schema matches the expected version."""
        try:
            response = self.store.client.table("schema_version") \
                .select("version") \
                .order("applied_at", desc=True) \
                .limit(1) \
                .execute()
            
            if response.data:
                db_version = response.data[0].get("version")
                return db_version == self.get_supported_schema_version()
        except Exception as e:
            print(f"[WARN] Schema verification failed: {e}")
        
        return False

    def log_audit(self, action: str, resource: str, metadata: Optional[Dict[str, Any]] = None, tenant_id: str = "primary"):
        """Compliance logging utility."""
        try:
            self.store.client.table("audit_log").insert({
                "tenant_id": tenant_id,
                "action": action,
                "resource": resource,
                "metadata": metadata or {},
                "timestamp": datetime.utcnow().isoformat()
            }).execute()
        except Exception as e:
            print(f"[WARN] Audit logging failure: {e}")
