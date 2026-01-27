from services.gmail_engine import run_engine
from services.summarizer import Summarizer

class EmailAssistant:
    def __init__(self):
        self.brain = Summarizer()

    def process_emails(self):
        """Logic for the API to fetch and summarize emails"""
        emails = run_engine()
        if not emails:
            return []
        
        results = []
        for email in emails:
            summary = self.brain.summarize(email)
            results.append({
                "subject": email.get('subject', 'No Subject'),
                "summary": summary
            })
        return results

def main():
    """Logic for running directly via terminal (python core.py)"""
    print("🚀 INTELLIGENT EMAIL ASSISTANT: Starting Orchestration...\n")
    
    assistant = EmailAssistant()
    emails = run_engine()
    
    if not emails:
        print("📭 No emails found or engine failed.")
        return

    print(f"🧠 Brain Initialized. Summarizing {len(emails)} emails...\n")
    
    print("✨ AI-Generated Executive Briefing ✨\n")
    print("="*60)
    
    for email in emails:
        summary_raw = assistant.brain.summarize(email)
        
        priority = "Medium"
        if "PRIORITY: High" in summary_raw: priority = "High"
        elif "PRIORITY: Low" in summary_raw: priority = "Low"
        
        print(f"[{priority}] {email['subject']}")
        print(f"{summary_raw}")
        print("-" * 60)

    print("\n✅ Phase 3 Complete: Executive Briefing Delivered.")

if __name__ == "__main__":
    main()