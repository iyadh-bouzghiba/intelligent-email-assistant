CLASSIFICATION_PROMPT = """
Analyze the following email and categorize its intent and priority.

Email Content:
Subject: {subject}
Body: {body}

Categorize the intent into one of: request, follow_up, escalation, scheduling, fyi, support, sales, other.
Assign a priority level: urgent, high, medium, low.
Provide a brief reasoning for your choice.
"""

SUMMARIZATION_PROMPT = """
Summarize the following email thread. Focus on key discussions, decisions made, action items, and any mentioned deadlines.

Thread History:
{history}

Summary Requirements:
- Concise but high-fidelity
- List action items separately
- Identify deadlines if any
"""

DRAFTING_PROMPT = """
Generate a professional and context-aware reply to the latest email in this thread.

Thread Summary/Context:
{summary}

Latest Email:
From: {sender}
Subject: {subject}
Body: {body}

Tone Requirements: Professional, helpful, and concise. Maintain continuity with the previous conversation.
"""

API_SUMMARIZATION_PROMPT = """
[SYSTEM] summarize email context with high precision. Remove fluff.
[CONTEXT] {body}
[TASK] 
1. Think step-by-step about the thread evolution.
2. Identify the latest valid decisions vs deprecated ones.
3. Extract:
    - Overview (1-2 sentences)
    - Key Points (bulleted)
    - Action Items (task-oriented)
    - Confidence (0.0-1.0)
[OUTPUT] Valid JSON only. Ensure reasoning is reflected in the extraction.
"""
