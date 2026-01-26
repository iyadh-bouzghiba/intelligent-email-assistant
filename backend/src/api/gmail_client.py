from typing import Dict, Any, List, Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class GmailClient:
    """
    Thin Gmail API wrapper.
    Responsible ONLY for Gmail API interactions.
    """

    def __init__(self, token_data: Dict[str, Any]):
        """
        token_data must contain:
        - access_token
        - refresh_token
        - token_uri
        - client_id
        - client_secret
        - scopes
        """

        if not token_data:
            raise ValueError("Missing OAuth token data")

        self.credentials = Credentials(
            token=token_data.get("access_token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=token_data.get("scopes"),
        )

        self.service = build(
            "gmail",
            "v1",
            credentials=self.credentials,
            cache_discovery=False,
        )

    # ------------------------------------------------------------------
    # WATCH (Push Notifications)
    # ------------------------------------------------------------------

    def start_watch(
        self,
        topic_name: str,
        label_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Registers a Gmail watch on the user's mailbox.
        Returns: { historyId, expiration, emailAddress }
        """

        if not topic_name:
            raise ValueError("Pub/Sub topic name is required")

        body = {
            "topicName": topic_name,
            "labelIds": label_ids or ["INBOX"],
            "labelFilterAction": "include",
        }

        try:
            response = (
                self.service.users()
                .watch(userId="me", body=body)
                .execute()
            )
            return response

        except HttpError as e:
            raise RuntimeError(
                f"Gmail watch failed: {e.error_details if hasattr(e, 'error_details') else str(e)}"
            )

    # ------------------------------------------------------------------
    # HISTORY (Used in Choice B)
    # ------------------------------------------------------------------

    def list_history(
        self,
        start_history_id: str,
        history_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch mailbox history since a given historyId.
        Used when Pub/Sub sends a notification.
        """

        if not start_history_id:
            raise ValueError("start_history_id is required")

        history_types = history_types or ["messageAdded"]

        try:
            response = (
                self.service.users()
                .history()
                .list(
                    userId="me",
                    startHistoryId=start_history_id,
                    historyTypes=history_types,
                )
                .execute()
            )

            return response.get("history", [])

        except HttpError as e:
            # 404 means historyId is too old → full resync needed
            if e.resp.status == 404:
                return []

            raise RuntimeError(
                f"Gmail history fetch failed: {e.error_details if hasattr(e, 'error_details') else str(e)}"
            )

    # ------------------------------------------------------------------
    # MESSAGE FETCH (Future use)
    # ------------------------------------------------------------------

    def get_message(self, message_id: str) -> Dict[str, Any]:
        """
        Fetch a full Gmail message by ID.
        """

        if not message_id:
            raise ValueError("message_id is required")

        try:
            return (
                self.service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )

        except HttpError as e:
            raise RuntimeError(
                f"Gmail message fetch failed: {e.error_details if hasattr(e, 'error_details') else str(e)}"
            )
