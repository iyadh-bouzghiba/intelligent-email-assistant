"""
Handles the lifecycle of a Gmail watch subscription.

This module is responsible for initiating and stopping push notifications from the
Gmail API to a specified Google Cloud Pub/Sub topic. A watch is user-specific
and has a limited lifespan (currently 7 days), requiring periodic renewal.
"""
import logging
from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError

from src.config import Config

logger = logging.getLogger(__name__)


class GmailWatchManager:
    """Manages the Gmail API watch subscription for a user."""

    def __init__(self, gmail_service: Resource):
        """
        Initializes the GmailWatchManager.

        Args:
            gmail_service: An authenticated Gmail API service resource instance.
        """
        self.gmail_service = gmail_service
        self.topic_name = f"projects/{Config.GCP_PROJECT_ID}/topics/{Config.PUBSUB_TOPIC_ID}"

    def start_watch(self, user_email: str) -> dict:
        """
        Initiates the watch on the user's mailbox.

        This sets up a push notification subscription to the configured Pub/Sub topic
        for 'unread' and 'inbox' label changes.

        Args:
            user_email: The email address of the user to watch.

        Returns:
            A dictionary containing the historyId and expiration of the watch.
        
        Raises:
            HttpError: If the API call to start the watch fails.
        """
        request = {
            'labelIds': ['INBOX', 'UNREAD'],
            'topicName': self.topic_name
        }
        try:
            response = self.gmail_service.users().watch(userId=user_email, body=request).execute()
            logger.info(f"Successfully started Gmail watch for {user_email} on topic {self.topic_name}.")
            logger.debug(f"Watch response for {user_email}: {response}")
            # The response contains 'historyId' and 'expiration'
            return response
        except HttpError as error:
            logger.error(f"Failed to start Gmail watch for {user_email}: {error}")
            raise

    def stop_watch(self, user_email: str) -> None:
        """
        Stops the watch on the user's mailbox.

        This cancels the push notification subscription.

        Args:
            user_email: The email address of the user to stop watching.
        
        Raises:
            HttpError: If the API call to stop the watch fails.
        """
        try:
            self.gmail_service.users().stop(userId=user_email).execute()
            logger.info(f"Successfully stopped Gmail watch for {user_email}.")
        except HttpError as error:
            # An error can occur if the watch doesn't exist, which is often safe to ignore.
            logger.warning(f"Could not stop Gmail watch for {user_email}, it might have already expired or been stopped: {error}")
            # Depending on strictness, you might not want to raise here.
            # For robustness, we allow this to fail without halting execution.
            pass

