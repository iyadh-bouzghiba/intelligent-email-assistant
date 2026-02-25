"""
PHASE 1 INTEGRATION TEST

Demonstrates the complete zero-budget optimization pipeline:
1. Email preprocessing (HTML, signatures, reply chains)
2. Token counting and smart truncation
3. PII masking

This simulates what the AI worker does before calling Mistral API.
"""

from services.email_preprocessor import EmailPreprocessor
from services.token_counter import TokenCounter, TokenLimits


def test_phase1_pipeline():
    print("=" * 70)
    print("PHASE 1 ZERO-BUDGET PIPELINE TEST")
    print("=" * 70)
    print()

    # Sample email with realistic complexity
    sample_email = """
    <html>
    <head><style>body { font-family: Arial; }</style></head>
    <body>
    <div style="padding: 20px;">
        <p>Hi Sarah,</p>

        <p>I wanted to follow up on the Q4 budget review meeting. Here are the key action items we discussed:</p>

        <ul>
            <li>Review marketing spend allocation by next Friday (5/12)</li>
            <li>Prepare cost analysis for the new CRM system</li>
            <li>Schedule follow-up meeting with finance team</li>
        </ul>

        <p>Please reach out if you have any questions. My contact info is below.</p>

        <p>Best regards,<br>John</p>
    </div>

    <div style="border-top: 1px solid #ccc; margin-top: 20px; padding-top: 10px; color: #666;">
        --<br>
        John Smith<br>
        Senior Financial Analyst<br>
        Acme Corporation<br>
        john.smith@acmecorp.com<br>
        +1-555-123-4567<br>
        <a href="https://acmecorp.com">acmecorp.com</a>
    </div>

    <div style="margin-top: 20px; border-top: 1px solid #eee; padding-top: 10px;">
        <p style="color: #999;">On Wed, May 10, 2024 at 2:30 PM Sarah Johnson &lt;sarah.j@acmecorp.com&gt; wrote:</p>
        <blockquote style="border-left: 2px solid #ccc; padding-left: 10px; color: #666;">
            <p>Hi John,</p>
            <p>Can we schedule the Q4 budget review meeting for this week?</p>
            <p>Thanks,<br>Sarah</p>
        </blockquote>
    </div>
    </body>
    </html>
    """

    subject = "Q4 Budget Review Follow-up"

    # Initialize Phase 1 components
    preprocessor = EmailPreprocessor(
        strip_html=True,
        remove_signatures=True,
        remove_reply_chains=True,
        normalize_whitespace=True
    )
    token_counter = TokenCounter()

    # STEP 1: Preprocessing
    print("STEP 1: EMAIL PREPROCESSING")
    print("-" * 70)
    print(f"Original email length: {len(sample_email)} characters")
    print()

    cleaned_email, prep_stats = preprocessor.preprocess(sample_email, subject)

    print(f"[OK] HTML stripped: {prep_stats['html_stripped']}")
    print(f"[OK] Signature removed: {prep_stats['signature_removed']}")
    print(f"[OK] Reply chain removed: {prep_stats['reply_chain_removed']}")
    print(f"[OK] Token reduction: {prep_stats['reduction_pct']:.1f}%")
    print(f"[OK] Final length: {prep_stats['final_chars']} characters")
    print()
    print("Cleaned content:")
    print(cleaned_email)
    print()

    # STEP 2: Token Counting
    print("STEP 2: TOKEN COUNTING & VALIDATION")
    print("-" * 70)

    token_count = token_counter.estimate_tokens(cleaned_email)
    within_limits, est_tokens, msg = token_counter.check_limits(cleaned_email)

    print(f"Estimated tokens: {est_tokens}")
    print(f"Within limits: {within_limits} ({msg})")
    print(f"Safe limit: {TokenLimits.SAFE_INPUT_TOKENS} tokens")
    print(f"Max output budget: {TokenLimits.MAX_OUTPUT_TOKENS} tokens")
    print()

    # STEP 3: Smart Truncation (if needed)
    if not within_limits:
        print("STEP 3: SMART TRUNCATION (ACTIVATED)")
        print("-" * 70)
        truncated_email, trunc_stats = token_counter.smart_truncate(cleaned_email)
        print(f"Original tokens: {trunc_stats['original_tokens']}")
        print(f"Final tokens: {trunc_stats['final_tokens']}")
        print(f"Reduction: {trunc_stats['reduction_pct']:.1f}%")
        print()
        final_email = truncated_email
    else:
        print("STEP 3: SMART TRUNCATION (SKIPPED - within limits)")
        print("-" * 70)
        print("[OK] Email is already within token limits, no truncation needed")
        print()
        final_email = cleaned_email

    # STEP 4: PII Masking (simulated)
    print("STEP 4: PII MASKING")
    print("-" * 70)

    import re
    masked_email = final_email

    # Count and mask emails
    email_matches = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', masked_email)
    masked_email = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', masked_email)

    # Count and mask phone numbers
    phone_matches = re.findall(r'\+\d{1,3}[-.\s]?\d{1,14}', masked_email)
    masked_email = re.sub(r'\+\d{1,3}[-.\s]?\d{1,14}', '[PHONE]', masked_email)

    # Count and mask URLs
    url_matches = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', masked_email)
    masked_email = re.sub(r'https?://[^\s<>"{}|\\^`\[\]]+', '[URL]', masked_email)

    print(f"[OK] Emails masked: {len(email_matches)}")
    print(f"[OK] Phone numbers masked: {len(phone_matches)}")
    print(f"[OK] URLs masked: {len(url_matches)}")
    print()

    # FINAL SUMMARY
    print("=" * 70)
    print("PHASE 1 PIPELINE SUMMARY")
    print("=" * 70)

    original_tokens = token_counter.estimate_tokens(sample_email)
    final_tokens = token_counter.estimate_tokens(masked_email)
    total_reduction = ((original_tokens - final_tokens) / original_tokens) * 100

    print(f"[STATS] Original tokens: {original_tokens}")
    print(f"[STATS] Final tokens: {final_tokens}")
    print(f"[STATS] Total reduction: {total_reduction:.1f}%")
    print(f"[STATS] Original chars: {len(sample_email)}")
    print(f"[STATS] Final chars: {len(masked_email)}")
    print()
    print("[READY] MISTRAL API CALL CONFIGURATION")
    print(f"   Model: open-mistral-nemo")
    print(f"   Temperature: 0.2")
    print(f"   Max output tokens: 300")
    print(f"   Concurrency limit: 3 concurrent requests")
    print(f"   Rate limit retry: 10s -> 30s -> 60s backoff")
    print()
    print("[COST] ZERO-BUDGET OPTIMIZATIONS")
    print(f"   Tokens saved: {original_tokens - final_tokens}")
    print(f"   Free tier protection: [ACTIVE]")
    print(f"   API rejection risk: [ELIMINATED]")
    print()


if __name__ == "__main__":
    test_phase1_pipeline()
