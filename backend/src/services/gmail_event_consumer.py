import json
import logging
from concurrent.futures import ThreadPoolExecutor
from google.cloud import pubsub_v1
from typing import Dict, Any

from src.auth.token_manager import TokenManager
from src.auth.credential_store import CredentialStore
from src.integrations.gmail import GmailClient
from src.data.store import PersistenceManager, UserDataStore
from src.main import EmailAssistant
from src.config import Config

logger = logging.getLogger(__name__)

class GmailEventConsumer:
    """
    Consumes Gmail push notifications from Pub/Sub.
    Triggers email fetching and AI processing.
    """
    
    def __init__(self):
        # Dependencies
        self.persistence = PersistenceManager()
        self.credential_store = CredentialStore(self.persistence)
        self.token_manager = TokenManager(self.credential_store)
        self.user_datastore = UserDataStore(self.persistence)
        self.assistant = EmailAssistant() # AI Engine entry point

        # Pub/Sub setup
        self.project_id = Config.GCP_PROJECT_ID
        self.subscription_id = Config.PUBSUB_SUBSCRIPTION_ID
        self.subscriber = pubsub_v1.SubscriberClient()
        self.subscription_path = self.subscriber.subscription_path(self.project_id, self.subscription_id)
        
        self._executor = ThreadPoolExecutor(max_workers=5)
        self.future = None

    def start(self):
        """Starts listening for messages."""
        logger.info(f"Starting Gmail Event Consumer on {self.subscription_path}...")
        try:
            self.future = self.subscriber.subscribe(
                self.subscription_path, 
                callback=self._callback,
                scheduler=pubsub_v1.subscriber.scheduler.ThreadScheduler(self._executor)
            )
        except Exception as e:
            logger.error(f"Failed to start subscriber: {e}")

    def stop(self):
        if self.future:
            self.future.cancel()
            self.subscriber.close()

    def _callback(self, message: pubsub_v1.subscriber.message.Message):
        """Handles incoming Pub/Sub messages."""
        try:
            data = json.loads(message.data)
            user_email = data.get("emailAddress")
            history_id = data.get("historyId")

            if not user_email or not history_id:
                logger.warning("Invalid Pub/Sub message received.")
                message.ack()
                return

            logger.info(f"Processing event for {user_email}, historyId: {history_id}")
            self._process_event(user_email, history_id)
            message.ack()

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            message.ack() # Ack to prevent infinite redelivery, or use Nack if retry desired

    def _process_event(self, user_email: str, new_history_id: str):
        """Syncs mailbox changes."""
        # 1. Get Credentials
        # Note: We need user_id to look up credentials. 
        # Assuming email is the user_id or mapped to it in UserDataStore/CredentialStore.
        # Simple assumption: user_id = "test_user" or lookup by email.
        # For this fix, we'll try looking up by email in tokens if keys are emails?
        # api_app.py used "test_user". 
        # We need a way to map email -> user_id OR store tokens by email.
        # Let's try to find creds for the email directly or fallback to "test_user".
        
        user_id = "test_user" # Hardcoded for Single Tenant / Demo assumption
        
        creds_data = self.credential_store.get_credentials(user_id)
        if not creds_data or creds_data.get('email') != user_email:
             # Try to find user by iterating tokens? (Inefficient but fine for small scale)
             state = self.persistence.load()
             found_user = None
             for uid, token in state.get("tokens", {}).items():
                 if token.get("email") == user_email: # assuming token has email inside
                     user_id = uid
                     break
        
        # Get Valid Creds objects (refresh handled by TokenManager)
        # However TokenManager expects user_id.
        
        # We need the tokenDICT for GmailClient, OR GmailClient accepting Credentials object.
        # Integrations/GmailClient now accepts DICT.
        # TokenManager returns Credentials object.
        # We should probably update GmailClient to accept Credentials object or convert back.
        # Or just use token manager to refresh, then get dict from helper.
        
        # Refresh and validate credentials first
        if not self.token_manager.get_valid_credentials(user_id):
             logger.error(f"No valid credentials found for {user_email}")
             return

        # 2. Sync Logic
        # Retrieve the guaranteed valid credentials as a dictionary for the client
        token_data = self.credential_store.get_credentials(user_id)
        client = GmailClient(token_data)
        
        # Use client to list history
        last_history_id = self.user_datastore.get_last_history_id(user_email)
        
        if last_history_id:
            logger.info(f"Fetching history from {last_history_id}")
            history = client.list_history(last_history_id)
            for record in history:
                for msg_added in record.get('messagesAdded', []):
                    msg_id = msg_added['message']['id']
                    email_data = client.get_message(msg_id)
                    
                    # 3. AI Processing
                    logger.info(f"AI Processing email: {msg_id}")
                    self.assistant.process_incoming_email(email_data)
        else:
            logger.info("No last history ID (first run?), skipping historical sync.")

        # Update cursor
        self.user_datastore.set_last_history_id(user_email, new_history_id)
