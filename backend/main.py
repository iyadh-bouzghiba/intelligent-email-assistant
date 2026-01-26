from services.gmail_engine import run_engine
from services.summarizer import Summarizer

def main():
    print("🚀 INTELLIGENT EMAIL ASSISTANT: Starting Orchestration...\n")
    
    # 1. Fetch Clean Data
    emails = run_engine()
    
    if not emails:
        print("📭 No emails found or engine failed.")
        return

    # 2. Process with AI
    print(f"🧠 Brain Initialized. Summarizing {len(emails)} emails...\n")
    brain = Summarizer()
    
    print("✨ AI-Generated Executive Briefing ✨\n")
    print("="*60)
    
    for i, email in enumerate(emails, 1):
        summary_raw = brain.summarize(email)
        
        # Parse priority for header
        priority = "Medium"
        if "PRIORITY: High" in summary_raw: priority = "High"
        elif "PRIORITY: Low" in summary_raw: priority = "Low"
        
        print(f"[{priority}] {email['subject']}")
        print(f"{summary_raw}")
        print("-" * 60)

    print("\n✅ Phase 3 Complete: Executive Briefing Delivered.")

if __name__ == "__main__":
    main()
