import re
import html
from bs4 import BeautifulSoup
from typing import Optional

class EmailPreprocessor:
    @staticmethod
    def clean_html(html_content: str) -> str:
        """Removes HTML tags and normalizes whitespace."""
        if not html_content:
            return ""
        soup = BeautifulSoup(html_content, "html.parser")
        # Remove script and style elements
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()
        
        text = soup.get_text(separator=" ")
        return EmailPreprocessor.clean_text(text)

    @staticmethod
    def clean_text(text: str) -> str:
        """Normalizes whitespace and removes redundant characters."""
        # Unescape HTML entities
        text = html.unescape(text)
        # Remove URLs (optional, depending on use case)
        # text = re.sub(r'http\S+', '', text)
        # Remove multiple newlines and spaces
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    @staticmethod
    def mask_pii(text: str) -> str:
        """
        Simple regex-based PII masking for demo purposes.
        In production, use Presidio or dedicated NER models.
        """
        # Mask emails
        text = re.sub(r'[\w\.-]+@[\w\.-]+', '[EMAIL]', text)
        # Mask phone numbers (generic)
        text = re.sub(r'\+?\d{1,4}?[-.\s]?\(?\d{1,3}?\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}', '[PHONE]', text)
        return text

    @staticmethod
    def remove_noise(text: str) -> str:
        """Removes quoted replies, signatures, and common disclaimers."""
        # Remove quoted lines starting with >
        text = re.sub(r'^\s*>.*$', '', text, flags=re.MULTILINE)
        
        # Remove common signature separators
        sig_markers = [r'--', r'Best regards', r'Sincerely', r'Thanks,', r'Sent from my iPhone']
        for marker in sig_markers:
            parts = re.split(marker, text, flags=re.IGNORECASE)
            if len(parts) > 1:
                text = parts[0]
                break
        
        # Remove common disclaimers (shortened example)
        disclaimer_patterns = [
            r'This email and any files transmitted.*',
            r'The information contained in this message is privileged.*'
        ]
        for pattern in disclaimer_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
            
        return text.strip()

    def process(self, content_body: str, is_html: bool = False) -> str:
        if is_html:
            cleaned = self.clean_html(content_body)
        else:
            cleaned = self.clean_text(content_body)
        
        no_noise = self.remove_noise(cleaned)
        return self.mask_pii(no_noise)
