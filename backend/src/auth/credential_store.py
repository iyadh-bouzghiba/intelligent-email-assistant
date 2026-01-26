from typing import Dict, Any, Optional
from src.data.store import PersistenceManager

class CredentialStore:
    """
    Interface for storing and retrieving user credentials securely.
    Wraps the raw PersistenceManager to provide specific credential access methods.
    """
    
    def __init__(self, persistence_manager: PersistenceManager):
        self._pm = persistence_manager

    def save_credentials(self, user_id: str, credentials: Dict[str, Any]):
        """
        Saves credentials for a specific user.
        Args:
            user_id: The unique identifier for the user.
            credentials: A dictionary containing OAuth credentials (token, refresh_token, etc.)
        """
        # Load current state
        state = self._pm.load()
        tokens = state.get("tokens", {})
        
        # Update tokens
        tokens[user_id] = credentials
        
        # Save back
        self._pm.save(
            tokens=tokens,
            watch_state=state.get("watch_state", {}),
            threads=state.get("threads", {})
        )

    def get_credentials(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves credentials for a specific user.
        Args:
            user_id: The unique identifier for the user.
        Returns:
            Dict containing credentials or None if not found.
        """
        state = self._pm.load()
        return state.get("tokens", {}).get(user_id)

    def delete_credentials(self, user_id: str):
        """
        Removes credentials for a user (e.g. on logout).
        """
        state = self._pm.load()
        tokens = state.get("tokens", {})
        
        if user_id in tokens:
            del tokens[user_id]
            self._pm.save(
                tokens=tokens,
                watch_state=state.get("watch_state", {}),
                threads=state.get("threads", {})
            )
