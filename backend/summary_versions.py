"""
Shared prompt-version identifiers for the email_ai_summaries table.

email_ai_summaries is a shared table: it holds both email summaries and
document summaries distinguished by prompt_version.  Importing from here
(rather than from the worker) lets the API layer and store filter safely
without pulling in heavy worker dependencies.
"""

EMAIL_SUMMARY_PROMPT_VERSION = "summ_v2_thread_aware"
DOCUMENT_SUMMARY_PROMPT_VERSION = "doc_v1_attachment_text"
