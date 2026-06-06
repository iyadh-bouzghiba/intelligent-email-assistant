"""
USER-INTELLIGENCE-STATE-01 Step 4 — Deterministic unit tests for
account_intelligence_profiles store methods and API endpoints.

No live Supabase, network, or real secrets.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from backend.infrastructure.supabase_store import (
    SupabaseStore,
    _DEFAULT_NOTIFICATION_PREFERENCES,
    _build_default_intelligence_profile,
)

TEST_JWT_SECRET = "test-secret-for-intelligence-profile-tests-32bytes"
TEST_UID = "00000000-0000-4000-8000-000000000001"


# ---------------------------------------------------------------------------
# Fake Supabase chain (mirrors test_control_plane_store_contracts style)
# ---------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, data=None):
        self.data = data


class _FakeChain:
    def __init__(self, data=None, raise_on_execute=False):
        self._data = data
        self._raise_on_execute = raise_on_execute
        self.table_name = None
        self.upsert_payload = None
        self.on_conflict_value = None
        self.eq_filters = []
        self.execute_called = False

    def select(self, *args, **kwargs):
        return self

    def eq(self, col, val):
        self.eq_filters.append((col, val))
        return self

    def limit(self, n):
        return self

    def upsert(self, payload, on_conflict=None):
        self.upsert_payload = payload
        self.on_conflict_value = on_conflict
        return self

    def execute(self):
        self.execute_called = True
        if self._raise_on_execute:
            raise RuntimeError("simulated DB error")
        return _FakeResult(data=self._data)


class _FakeClient:
    def __init__(self, chain):
        self._chain = chain

    def table(self, name):
        self._chain.table_name = name
        return self._chain


def _make_store(chain):
    with (
        patch(
            "backend.infrastructure.supabase_store.create_client",
            return_value=_FakeClient(chain),
        ),
        patch.dict(
            os.environ,
            {"SUPABASE_URL": "https://fake.supabase.co", "SUPABASE_SERVICE_KEY": "fake-key"},
        ),
    ):
        return SupabaseStore()


# ---------------------------------------------------------------------------
# A — _build_default_intelligence_profile helper
# ---------------------------------------------------------------------------

class TestBuildDefaultProfile(unittest.TestCase):
    def test_structure(self):
        p = _build_default_intelligence_profile("user@example.com")
        self.assertEqual(p["account_id"], "user@example.com")
        self.assertEqual(p["observed_categories"], {})
        self.assertEqual(p["category_corrections"], [])
        self.assertEqual(p["confidence_calibration"], [])
        self.assertEqual(p["action_item_completion"], [])
        self.assertIsNone(p["last_sync_at"])

    def test_notification_preferences_are_conservative(self):
        p = _build_default_intelligence_profile("x")
        np = p["notification_preferences"]
        self.assertFalse(np["urgency_escalation_enabled"])
        self.assertEqual(np["urgency_threshold"], "high")
        self.assertFalse(np["action_item_deadline_notifications_enabled"])
        self.assertEqual(np["action_item_deadline_hours"], 24)
        self.assertFalse(np["thread_silence_notifications_enabled"])
        self.assertEqual(np["thread_silence_hours"], 72)

    def test_returns_independent_copy(self):
        p1 = _build_default_intelligence_profile("a")
        p2 = _build_default_intelligence_profile("b")
        p1["notification_preferences"]["urgency_threshold"] = "low"
        self.assertEqual(p2["notification_preferences"]["urgency_threshold"], "high")


# ---------------------------------------------------------------------------
# B — get_account_intelligence_profile
# ---------------------------------------------------------------------------

class TestGetAccountIntelligenceProfile(unittest.TestCase):

    def test_returns_default_when_no_row(self):
        chain = _FakeChain(data=[])
        store = _make_store(chain)
        profile = store.get_account_intelligence_profile("user@example.com")
        self.assertEqual(profile["account_id"], "user@example.com")
        self.assertEqual(profile["observed_categories"], {})
        self.assertEqual(profile["category_corrections"], [])
        self.assertFalse(profile["notification_preferences"]["urgency_escalation_enabled"])

    def test_merges_row_with_defaults_for_null_fields(self):
        row = {
            "account_id": "user@example.com",
            "observed_categories": {"Meeting": 3},
            "category_corrections": None,
            "confidence_calibration": None,
            "action_item_completion": None,
            "notification_preferences": None,
            "last_sync_at": "2026-06-03T10:00:00Z",
            "created_at": "2026-06-01T00:00:00Z",
            "updated_at": "2026-06-03T10:00:00Z",
        }
        chain = _FakeChain(data=[row])
        store = _make_store(chain)
        profile = store.get_account_intelligence_profile("user@example.com")
        self.assertEqual(profile["observed_categories"], {"Meeting": 3})
        self.assertEqual(profile["category_corrections"], [])
        self.assertEqual(profile["confidence_calibration"], [])
        self.assertEqual(profile["action_item_completion"], [])
        self.assertFalse(profile["notification_preferences"]["urgency_escalation_enabled"])

    def test_returns_row_data_when_all_fields_present(self):
        np = {"urgency_escalation_enabled": True, "urgency_threshold": "medium"}
        row = {
            "account_id": "user@example.com",
            "observed_categories": {"Finance": 5},
            "category_corrections": [{"cat": "old", "corrected": "new"}],
            "confidence_calibration": [{"score": 0.9}],
            "action_item_completion": [{"id": "abc"}],
            "notification_preferences": np,
            "last_sync_at": "2026-06-03T10:00:00Z",
            "created_at": "2026-06-01T00:00:00Z",
            "updated_at": "2026-06-03T10:00:00Z",
        }
        chain = _FakeChain(data=[row])
        store = _make_store(chain)
        profile = store.get_account_intelligence_profile("user@example.com")
        self.assertEqual(profile["observed_categories"], {"Finance": 5})
        self.assertTrue(profile["notification_preferences"]["urgency_escalation_enabled"])

    def test_raises_on_db_error(self):
        chain = _FakeChain(raise_on_execute=True)
        store = _make_store(chain)
        with self.assertRaises(Exception):
            store.get_account_intelligence_profile("user@example.com")

    def test_merges_partial_notification_preferences_with_defaults(self):
        row = {
            "account_id": "user@example.com",
            "observed_categories": {},
            "category_corrections": [],
            "confidence_calibration": [],
            "action_item_completion": [],
            "notification_preferences": {"urgency_escalation_enabled": True},
            "last_sync_at": None,
            "created_at": None,
            "updated_at": None,
        }
        chain = _FakeChain(data=[row])
        store = _make_store(chain)
        profile = store.get_account_intelligence_profile("user@example.com")
        np = profile["notification_preferences"]
        self.assertTrue(np["urgency_escalation_enabled"])
        self.assertEqual(np["urgency_threshold"], "high")
        self.assertFalse(np["action_item_deadline_notifications_enabled"])
        self.assertEqual(np["action_item_deadline_hours"], 24)
        self.assertFalse(np["thread_silence_notifications_enabled"])
        self.assertEqual(np["thread_silence_hours"], 72)

    def test_replaces_malformed_field_types_with_defaults(self):
        row = {
            "account_id": "user@example.com",
            "observed_categories": ["wrong", "type"],
            "category_corrections": {"wrong": "type"},
            "confidence_calibration": "bad",
            "action_item_completion": 42,
            "notification_preferences": ["also", "wrong"],
            "last_sync_at": None,
            "created_at": None,
            "updated_at": None,
        }
        chain = _FakeChain(data=[row])
        store = _make_store(chain)
        profile = store.get_account_intelligence_profile("user@example.com")
        self.assertEqual(profile["observed_categories"], {})
        self.assertEqual(profile["category_corrections"], [])
        self.assertEqual(profile["confidence_calibration"], [])
        self.assertEqual(profile["action_item_completion"], [])
        np = profile["notification_preferences"]
        self.assertFalse(np["urgency_escalation_enabled"])
        self.assertEqual(np["urgency_threshold"], "high")


# ---------------------------------------------------------------------------
# C — upsert_account_intelligence_profile
# ---------------------------------------------------------------------------

class TestUpsertAccountIntelligenceProfile(unittest.TestCase):

    def _make_store_with_upsert_chain(self, upsert_data=None):
        chain = _FakeChain(data=upsert_data or [])
        store = _make_store(chain)
        return store, chain

    def test_strips_unknown_fields(self):
        store, chain = self._make_store_with_upsert_chain()
        updates = {
            "observed_categories": {"Meeting": 1},
            "unknown_field": "should_be_stripped",
            "injected_key": "bad_value",
        }
        with patch.object(store, "get_account_intelligence_profile", return_value={"account_id": "user@example.com"}):
            store.upsert_account_intelligence_profile("user@example.com", updates)
        self.assertIsNotNone(chain.upsert_payload)
        self.assertNotIn("unknown_field", chain.upsert_payload)
        self.assertNotIn("injected_key", chain.upsert_payload)

    def test_uses_path_account_id_not_body(self):
        store, chain = self._make_store_with_upsert_chain()
        updates = {
            "observed_categories": {"Meeting": 1},
            "account_id": "attacker@evil.com",
        }
        with patch.object(store, "get_account_intelligence_profile", return_value={"account_id": "user@example.com"}):
            store.upsert_account_intelligence_profile("user@example.com", updates)
        self.assertEqual(chain.upsert_payload["account_id"], "user@example.com")

    def test_sets_updated_at(self):
        store, chain = self._make_store_with_upsert_chain()
        with patch.object(store, "get_account_intelligence_profile", return_value={}):
            store.upsert_account_intelligence_profile("user@example.com", {})
        self.assertIn("updated_at", chain.upsert_payload)
        self.assertIsNotNone(chain.upsert_payload["updated_at"])

    def test_uses_on_conflict_account_id(self):
        store, chain = self._make_store_with_upsert_chain()
        with patch.object(store, "get_account_intelligence_profile", return_value={}):
            store.upsert_account_intelligence_profile("user@example.com", {})
        self.assertEqual(chain.on_conflict_value, "account_id")

    def test_raises_on_db_error(self):
        chain = _FakeChain(raise_on_execute=True)
        store = _make_store(chain)
        with self.assertRaises(Exception):
            store.upsert_account_intelligence_profile("user@example.com", {})

    def test_skips_none_for_non_null_jsonb_fields(self):
        store, chain = self._make_store_with_upsert_chain()
        updates = {
            "observed_categories": None,
            "category_corrections": None,
            "confidence_calibration": None,
            "action_item_completion": None,
        }
        with patch.object(store, "get_account_intelligence_profile", return_value={}):
            store.upsert_account_intelligence_profile("user@example.com", updates)
        self.assertNotIn("observed_categories", chain.upsert_payload)
        self.assertNotIn("category_corrections", chain.upsert_payload)
        self.assertNotIn("confidence_calibration", chain.upsert_payload)
        self.assertNotIn("action_item_completion", chain.upsert_payload)

    def test_merges_partial_notification_preferences_writes_full_object(self):
        store, chain = self._make_store_with_upsert_chain()
        current_profile = _build_default_intelligence_profile("user@example.com")
        final_profile = {**current_profile}
        with patch.object(
            store,
            "get_account_intelligence_profile",
            side_effect=[current_profile, final_profile],
        ):
            store.upsert_account_intelligence_profile(
                "user@example.com",
                {"notification_preferences": {"urgency_escalation_enabled": True}},
            )
        written_np = chain.upsert_payload.get("notification_preferences")
        self.assertIsNotNone(written_np)
        self.assertTrue(written_np["urgency_escalation_enabled"])
        self.assertEqual(written_np["urgency_threshold"], "high")
        self.assertIn("action_item_deadline_hours", written_np)
        self.assertIn("thread_silence_hours", written_np)

    def test_skips_none_and_non_dict_notification_preferences(self):
        store, chain = self._make_store_with_upsert_chain()
        with patch.object(store, "get_account_intelligence_profile", return_value={}):
            store.upsert_account_intelligence_profile(
                "user@example.com", {"notification_preferences": None}
            )
        self.assertNotIn("notification_preferences", chain.upsert_payload)
        with patch.object(store, "get_account_intelligence_profile", return_value={}):
            store.upsert_account_intelligence_profile(
                "user@example.com", {"notification_preferences": ["bad"]}
            )
        self.assertNotIn("notification_preferences", chain.upsert_payload)

    def test_returns_get_result_after_upsert(self):
        store, chain = self._make_store_with_upsert_chain()
        expected = {"account_id": "user@example.com", "observed_categories": {"X": 1}}
        with patch.object(store, "get_account_intelligence_profile", return_value=expected) as mock_get:
            result = store.upsert_account_intelligence_profile("user@example.com", {})
        self.assertEqual(result, expected)
        mock_get.assert_called_once_with("user@example.com")


# ---------------------------------------------------------------------------
# D — API endpoints (GET + POST /api/accounts/{account_id}/intelligence-profile)
# ---------------------------------------------------------------------------

class TestIntelligenceProfileAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("JWT_SECRET", TEST_JWT_SECRET)
        from backend import auth_guard as ag
        ag._JWT_SECRET = None
        from backend.api import service
        cls.service = service
        cls.ag = ag
        from fastapi.testclient import TestClient
        cls.client = TestClient(service.app)

    def setUp(self):
        self.ag._JWT_SECRET = None

    def tearDown(self):
        self.ag._JWT_SECRET = None

    def _cookie(self, subject="user@example.com"):
        with patch.dict(os.environ, {"JWT_SECRET": TEST_JWT_SECRET}, clear=False):
            self.ag._JWT_SECRET = None
            token = self.ag.create_access_token(subject=subject, uid=TEST_UID)
        return {"iea_session": token}

    def _default_profile(self, account_id="user@example.com"):
        return {
            "account_id": account_id,
            "observed_categories": {},
            "category_corrections": [],
            "confidence_calibration": [],
            "action_item_completion": [],
            "notification_preferences": dict(_DEFAULT_NOTIFICATION_PREFERENCES),
            "last_sync_at": None,
            "created_at": None,
            "updated_at": None,
        }

    def _mock_store(self, profile):
        mock_store = MagicMock()
        mock_store.check_membership.return_value = True
        mock_store.get_account_intelligence_profile.return_value = profile
        mock_store.upsert_account_intelligence_profile.return_value = profile
        return mock_store

    def test_get_returns_profile(self):
        profile = self._default_profile()
        with patch.object(self.service, "safe_get_store", return_value=self._mock_store(profile)):
            response = self.client.get(
                "/api/accounts/user%40example.com/intelligence-profile",
                cookies=self._cookie("user@example.com"),
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["account_id"], "user@example.com")
        self.assertIn("observed_categories", data)

    def test_get_rejects_non_subject_account_id_from_path(self):
        mock_store = MagicMock()
        mock_store.check_membership.return_value = False
        with patch.object(self.service, "safe_get_store", return_value=mock_store):
            response = self.client.get(
                "/api/accounts/other%40example.com/intelligence-profile",
                cookies=self._cookie("user@example.com"),
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json().get("detail"),
            "Access denied: account does not belong to the authenticated session.",
        )
        mock_store.get_account_intelligence_profile.assert_not_called()

    def test_get_503_when_store_unavailable(self):
        with patch.object(self.service, "safe_get_store", return_value=None):
            response = self.client.get(
                "/api/accounts/user%40example.com/intelligence-profile",
                cookies=self._cookie("user@example.com"),
            )
        self.assertEqual(response.status_code, 503)

    def test_post_partial_update_returns_profile(self):
        profile = {**self._default_profile(), "observed_categories": {"Meeting": 1}}
        with patch.object(self.service, "safe_get_store", return_value=self._mock_store(profile)):
            response = self.client.post(
                "/api/accounts/user%40example.com/intelligence-profile",
                json={"observed_categories": {"Meeting": 1}},
                cookies=self._cookie("user@example.com"),
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["observed_categories"], {"Meeting": 1})

    def test_post_503_when_store_unavailable(self):
        with patch.object(self.service, "safe_get_store", return_value=None):
            response = self.client.post(
                "/api/accounts/user%40example.com/intelligence-profile",
                json={},
                cookies=self._cookie("user@example.com"),
            )
        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
