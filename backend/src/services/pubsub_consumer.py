"""
Service for consuming messages from a Google Cloud Pub/Sub subscription.

This service listens for notifications from Gmail push notifications,
extracts the history ID, and fetches the email delta for the affected user.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from google.cloud import pubsub_v1
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError

from src.api.oauth_manager import OAuthManager
from src.config import Config
from src.data.store import UserDataStore
from src.adapters.gmail import GmailAdapter
from src.adapters.base import StandardEmail

logger = logging.getLogger(__name__)


class PubSubConsumer:
    """
    A robust Pub/Sub consumer that listens for Gmail notifications.
    """

    def __init__(self, oauth_manager: OAuthManager, user_datastore: UserDataStore):
        """
        Initializes the PubSubConsumer.

        Args:
            oauth_manager: An instance of OAuthManager to get user credentials.
            user_datastore: An instance of UserDataStore to manage user state.
        """
        self.oauth_manager = oauth_manager
        self.user_datastore = user_datastore
        self.subscriber = pubsub_v1.SubscriberClient()
        self.subscription_path = self.subscriber.subscription_path(
            Config.GCP_PROJECT_ID, Config.PUBSUB_SUBSCRIPTION_ID
        )
        self._executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="PubSubWorker")
        self.streaming_pull_future = None
        # In a real app, you would have a more sophisticated way to pass new emails
        # to the processing engine, e.g., a message queue like RabbitMQ or Redis.
        self.new_email_callback: Callable[[StandardEmail], None] = self._default_email_handler

    def _default_email_handler(self, email: StandardEmail):
        """A simple placeholder for handling new emails."""
        logger.info(f"Received new email: {email.subject} from {email.sender} for user {email.recipient}")
        # Here, you would enqueue the email for processing by the engine/decision_router
        pass

    def _get_gmail_service(self, user_email: str) -> Resource:
        """Builds an authenticated Gmail API service resource for a user."""
        # This assumes OAuthManager can retrieve and refresh credentials
        creds_dict = self.oauth_manager.get_credentials(user_email)
        if not creds_dict:
            raise ValueError(f"Could not retrieve credentials for user {user_email}")
        
        credentials = Credentials(**creds_dict)
        return build('gmail', 'v1', credentials=credentials)

    def _process_history_delta(self, user_email: str, new_history_id: str):
        """
        Fetches new emails since the last known history ID.
        """
        last_history_id = self.user_datastore.get_last_history_id(user_email)
        if not last_history_id:
            logger.warning(f"No last_history_id found for {user_email}. Skipping delta fetch to avoid full mailbox scan.")
            self.user_datastore.set_last_history_id(user_email, new_history_id)
            return

        logger.info(f"Fetching delta for {user_email} from historyId {last_history_id} to {new_history_id}")
        
        try:
            gmail_service = self._get_gmail_service(user_email)
            history_response = gmail_service.users().history().list(
                userId=user_email,
                startHistoryId=last_history_id,
                historyTypes=['messageAdded']
            ).execute()

            messages_added = history_response.get('history', [])
            message_ids = [
                msg['id']
                for item in messages_added
                for msg in item.get('messages', [])
            ]

            if not message_ids:
                logger.info(f"No new messages found for {user_email} in this history update.")
            else:
                logger.info(f"Found {len(message_ids)} new messages for {user_email}. Fetching details.")
                # Using the adapter for robust, standardized fetching
                adapter = GmailAdapter(gmail_service=gmail_service)
                for msg_id in message_ids:
                    email_data = adapter.get_email(msg_id)
                    if email_data:
                        # Pass the standardized email to the callback
                        self.new_email_callback(email_data)

        except HttpError as e:
            logger.error(f"Gmail API error while fetching history for {user_email}: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred during history processing for {user_email}: {e}", exc_info=True)
        finally:
            # Always update to the latest history ID to prevent reprocessing errors
            self.user_datastore.set_last_history_id(user_email, new_history_id)
            logger.debug(f"Updated last_history_id to {new_history_id} for {user_email}")

    def _callback(self, message: pubsub_v1.subscriber.message.Message):
        """The callback function executed for each received Pub/Sub message."""
        try:
            data = json.loads(message.data)
            user_email = data.get("emailAddress")
            history_id = data.get("historyId")

            if not user_email or not history_id:
                logger.error(f"Received malformed Pub/Sub message: {data}")
                message.ack()
                return

            logger.info(f"Received notification for {user_email} with historyId: {history_id}")
            self._process_history_delta(user_email, history_id)

        except json.JSONDecodeError:
            logger.error(f"Failed to decode Pub/Sub message data: {message.data}")
        except Exception as e:
            logger.error(f"Error in Pub/Sub callback: {e}", exc_info=True)
        finally:
            message.ack()

    def start(self):
        """Starts the Pub/Sub subscriber in a background thread."""
        if self.streaming_pull_future and self.streaming_pull_future.running():
            logger.warning("Subscriber is already running.")
            return

        logger.info(f"Starting Pub/Sub consumer for subscription: {self.subscription_path}")
        self.streaming_pull_future = self.subscriber.subscribe(
            self.subscription_path,
            callback=self._callback,
            flow_control=pubsub_v1.types.FlowControl(max_messages=10),
            scheduler=pubsub_v1.subscriber.scheduler.ThreadScheduler(self._executor)
        )
        logger.info("Pub/Sub consumer started successfully.")

    def stop(self):
        """Stops the Pub/Sub subscriber gracefully."""
        if self.streaming_pull_future:
            logger.info("Stopping Pub/Sub consumer...")
            self.streaming_pull_future.cancel()  # Trigger the shutdown
            self.streaming_pull_future.result(timeout=30)  # Wait for shutdown to complete
            self._executor.shutdown(wait=True)
            self.subscriber.close()
            logger.info("Pub/Sub consumer stopped.")

