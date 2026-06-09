from unittest.mock import patch, MagicMock
import threading

from backend.infrastructure.supabase_store import (
    get_store_instance,
    reset_store_instance,
    SupabaseStore,
)
from backend.api.service import safe_get_store


def test_get_store_instance_returns_supabase_store():
    reset_store_instance()
    try:
        with patch.object(SupabaseStore, "__init__", return_value=None):
            result = get_store_instance()

        assert isinstance(result, SupabaseStore)
    finally:
        reset_store_instance()


def test_get_store_instance_returns_same_object():
    reset_store_instance()
    try:
        with patch.object(SupabaseStore, "__init__", return_value=None):
            first = get_store_instance()
            second = get_store_instance()

        assert first is second
    finally:
        reset_store_instance()


def test_get_store_instance_thread_safe():
    reset_store_instance()
    results = []
    errors = []

    def worker():
        try:
            results.append(get_store_instance())
        except Exception as exc:
            errors.append(exc)

    try:
        with patch.object(SupabaseStore, "__init__", return_value=None):
            threads = [threading.Thread(target=worker) for _ in range(10)]

            for thread in threads:
                thread.start()

            for thread in threads:
                thread.join()

        assert errors == []
        assert len(results) == 10
        assert len({id(result) for result in results}) == 1
    finally:
        reset_store_instance()


def test_reset_store_instance_clears_singleton():
    reset_store_instance()
    try:
        with patch.object(SupabaseStore, "__init__", return_value=None):
            first = get_store_instance()
            reset_store_instance()
            second = get_store_instance()

        assert first is not second
    finally:
        reset_store_instance()


def test_safe_get_store_uses_get_store_instance():
    mock_store = MagicMock()

    with patch("backend.api.service.get_store_instance", return_value=mock_store) as mock_get_store:
        result = safe_get_store()

    mock_get_store.assert_called_once_with()
    assert result is mock_store


def test_safe_get_store_returns_none_on_failure():
    with patch("backend.api.service.get_store_instance", side_effect=RuntimeError("no env")):
        result = safe_get_store()

    assert result is None