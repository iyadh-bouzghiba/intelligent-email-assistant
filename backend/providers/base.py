from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class NormalizedEmail:
    message_id: str
    subject: str
    sender: str
    date: str
    body: str
    thread_id: Optional[str] = None


class EmailProvider(ABC):
    @abstractmethod
    def get_delta_emails(
        self,
        account_id: str,
        cursor: Optional[str],
    ) -> Tuple[List[NormalizedEmail], Optional[str]]:
        raise NotImplementedError

    @abstractmethod
    def get_attachment(
        self,
        account_id: str,
        message_id: str,
        attachment_id: str,
    ) -> Tuple[bytes, str]:
        raise NotImplementedError

    @abstractmethod
    def send_email(
        self,
        account_id: str,
        to: str,
        subject: str,
        body: str,
        thread_id: Optional[str],
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def refresh_token(self, account_id: str) -> None:
        raise NotImplementedError