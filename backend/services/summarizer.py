import os
from mistralai import Mistral
from dotenv import load_dotenv

load_dotenv()

class Summarizer:
    def __init__(self):
        api_key = os.getenv("MISTRAL_API_KEY")
        if not api_key:
            raise ValueError("MISTRAL_API_KEY not found in .env")
        self.client = Mistral(api_key=api_key)
        self.model = "mistral-tiny" # Defaulting to tiny for reliability during testing

    def summarize(self, email_data):
        prompt = f"""
        Role: Executive Assistant AI.
        Objective: Analyze the email and extract key intelligence.
        
        SENDER: {email_data['sender']}
        SUBJECT: {email_data['subject']}
        BODY: {email_data['body']} 
        
        Return your analysis using these EXACT labels:
        SUMMARY: [A concise 2-sentence executive summary]
        ACTION: [Specific next step for the user, or "None"]
        PRIORITY: [Low/Medium/High]
        CATEGORY: [Security/Financial/General] - Use 'Security' for logins/alerts, 'Financial' for invoices/receipts, 'General' for all others.
        """

        messages = [
            {"role": "user", "content": prompt},
        ]
        
        try:
            chat_response = self.client.chat.complete(
                model=self.model,
                messages=messages,
            )
            return chat_response.choices[0].message.content
        except Exception as e:
            return f"SUMMARY: Error processing email.\nACTION: Check Mistral API.\nPRIORITY: Medium"

if __name__ == "__main__":
    # Test stub
    test_email = {"sender": "Test", "subject": "Hello", "body": "This is a test email content."}
    s = Summarizer()
    print(s.summarize(test_email))
