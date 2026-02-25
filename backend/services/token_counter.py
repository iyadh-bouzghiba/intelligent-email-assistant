"""
Token Counter Module

ZERO-BUDGET TOKEN MANAGEMENT: Estimate and enforce token limits to prevent API rejections
and control costs on Mistral free tier.

Token Limits (Mistral Free Tier Safe):
- MAX_INPUT_TOKENS: 4000 (safe buffer below API limit)
- MAX_OUTPUT_TOKENS: 300 (structured summary size)
- TOTAL_REQUEST_TOKENS: 4300

Estimation Formula:
- 1 token ≈ 4 characters (English)
- 1 token ≈ 2-3 characters (Arabic/Chinese)
- Includes both content + prompt overhead
"""

import os
from typing import Tuple, Literal
from enum import Enum


class TokenEstimationMode(Enum):
    """Token estimation modes for different languages."""
    ENGLISH = 4.0      # 1 token per 4 chars
    MULTILINGUAL = 3.5  # 1 token per 3.5 chars (average for European languages)
    CJK_ARABIC = 2.5   # 1 token per 2.5 chars (Chinese/Japanese/Korean/Arabic)


class TokenLimits:
    """
    Zero-budget token limits for Mistral free tier safety.

    These limits ensure:
    1. No API rejections
    2. Predictable costs
    3. Fast response times
    4. Free-tier compliance
    """
    MAX_INPUT_TOKENS = 4000   # Input content limit
    MAX_OUTPUT_TOKENS = 300   # Output summary limit
    MAX_TOTAL_TOKENS = 4300   # Total request budget

    # Prompt overhead (system prompt + JSON structure)
    PROMPT_OVERHEAD_TOKENS = 150

    # Safety margins
    SAFE_INPUT_TOKENS = MAX_INPUT_TOKENS - PROMPT_OVERHEAD_TOKENS  # 3850


class TokenCounter:
    """
    Zero-budget token counter for cost control.

    All operations are local estimates, no API calls.
    """

    def __init__(self, mode: TokenEstimationMode = TokenEstimationMode.ENGLISH):
        """
        Initialize token counter.

        Args:
            mode: Estimation mode based on language type
        """
        self.mode = mode
        self.chars_per_token = mode.value

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for given text.

        Uses character-based approximation:
        - English: 1 token ≈ 4 chars
        - Multilingual: 1 token ≈ 3.5 chars
        - CJK/Arabic: 1 token ≈ 2.5 chars

        Args:
            text: Input text

        Returns:
            Estimated token count
        """
        if not text or len(text.strip()) == 0:
            return 0

        char_count = len(text)
        estimated_tokens = int(char_count / self.chars_per_token)

        return estimated_tokens

    def check_limits(self, text: str) -> Tuple[bool, int, str]:
        """
        Check if text fits within token limits.

        Args:
            text: Input text to check

        Returns:
            Tuple of (is_within_limits, estimated_tokens, message)
        """
        estimated = self.estimate_tokens(text)

        if estimated <= TokenLimits.SAFE_INPUT_TOKENS:
            return True, estimated, "OK"
        elif estimated <= TokenLimits.MAX_INPUT_TOKENS:
            return True, estimated, "WARNING: Near limit, consider truncation"
        else:
            overflow = estimated - TokenLimits.MAX_INPUT_TOKENS
            return False, estimated, f"EXCEEDS LIMIT by {overflow} tokens"

    def smart_truncate(self, text: str, target_tokens: int = None) -> Tuple[str, dict]:
        """
        Smart truncation to fit within token limits.

        Strategy:
        1. Keep first 20% (context/greeting)
        2. Keep last 40% (main content/conclusion)
        3. Remove middle 40% (usually less critical)

        This preserves:
        - Email context (who, when)
        - Core message (conclusion)
        - Action items (usually at end)

        Args:
            text: Input text to truncate
            target_tokens: Target token count (default: SAFE_INPUT_TOKENS)

        Returns:
            Tuple of (truncated_text, stats_dict)
        """
        if target_tokens is None:
            target_tokens = TokenLimits.SAFE_INPUT_TOKENS

        current_tokens = self.estimate_tokens(text)

        if current_tokens <= target_tokens:
            return text, {
                "truncated": False,
                "original_tokens": current_tokens,
                "final_tokens": current_tokens,
                "reduction_pct": 0
            }

        # Calculate target character count
        target_chars = int(target_tokens * self.chars_per_token)

        # Smart truncation: keep first 20% + last 40%
        lines = text.split('\n')
        total_lines = len(lines)

        # Calculate split points
        first_keep_lines = int(total_lines * 0.20)
        last_keep_lines = int(total_lines * 0.40)

        # Keep first 20% and last 40%
        kept_lines = lines[:first_keep_lines] + ["...[content truncated for length]..."] + lines[-last_keep_lines:]
        truncated_text = '\n'.join(kept_lines)

        # Verify we're under limit, if not, do hard truncation
        truncated_tokens = self.estimate_tokens(truncated_text)

        if truncated_tokens > target_tokens:
            # Fallback: hard truncate to character limit
            truncated_text = text[:target_chars] + "...[truncated]"
            truncated_tokens = self.estimate_tokens(truncated_text)

        stats = {
            "truncated": True,
            "original_tokens": current_tokens,
            "final_tokens": truncated_tokens,
            "reduction_pct": round(((current_tokens - truncated_tokens) / current_tokens) * 100, 1)
        }

        return truncated_text, stats

    def should_bypass_summarization(self, text: str, threshold_tokens: int = 50) -> bool:
        """
        Determine if text is too short to warrant summarization.

        Args:
            text: Input text
            threshold_tokens: Minimum tokens to summarize (default: 50)

        Returns:
            True if text is too short, False otherwise
        """
        estimated = self.estimate_tokens(text)
        return estimated < threshold_tokens


# Convenience functions

def estimate_tokens(text: str, mode: TokenEstimationMode = TokenEstimationMode.ENGLISH) -> int:
    """Quick token estimation."""
    counter = TokenCounter(mode)
    return counter.estimate_tokens(text)


def check_token_limits(text: str) -> Tuple[bool, int, str]:
    """Quick limit check."""
    counter = TokenCounter()
    return counter.check_limits(text)


def smart_truncate_to_limit(text: str, target_tokens: int = TokenLimits.SAFE_INPUT_TOKENS) -> Tuple[str, dict]:
    """Quick smart truncation."""
    counter = TokenCounter()
    return counter.smart_truncate(text, target_tokens)


def get_token_budget_remaining(text: str) -> int:
    """Get remaining token budget for output."""
    counter = TokenCounter()
    input_tokens = counter.estimate_tokens(text)
    input_with_overhead = input_tokens + TokenLimits.PROMPT_OVERHEAD_TOKENS
    remaining = TokenLimits.MAX_TOTAL_TOKENS - input_with_overhead

    return max(0, min(remaining, TokenLimits.MAX_OUTPUT_TOKENS))


if __name__ == "__main__":
    # Test cases
    print("=== TOKEN COUNTER TEST ===\n")

    # Test 1: Short email (should not be summarized)
    short_email = "Hi, thanks for your email. Will follow up tomorrow."
    counter = TokenCounter()

    tokens = counter.estimate_tokens(short_email)
    bypass = counter.should_bypass_summarization(short_email)
    print(f"Test 1: Short email")
    print(f"  Tokens: {tokens}")
    print(f"  Should bypass: {bypass}")
    print()

    # Test 2: Medium email (should be fine)
    medium_email = "Hi John,\n\n" + ("This is a longer email with more content. " * 50)
    tokens = counter.estimate_tokens(medium_email)
    is_ok, est, msg = counter.check_limits(medium_email)
    print(f"Test 2: Medium email")
    print(f"  Tokens: {tokens}")
    print(f"  Within limits: {is_ok} ({msg})")
    print()

    # Test 3: Very long email (needs truncation)
    long_email = "Hi John,\n\n" + ("This is a very long email with excessive content. " * 200)
    tokens_before = counter.estimate_tokens(long_email)
    is_ok, est, msg = counter.check_limits(long_email)
    print(f"Test 3: Very long email")
    print(f"  Tokens before: {tokens_before}")
    print(f"  Within limits: {is_ok} ({msg})")

    if not is_ok:
        truncated, stats = counter.smart_truncate(long_email)
        print(f"  After truncation: {stats['final_tokens']} tokens ({stats['reduction_pct']}% reduction)")
        print(f"  Truncated text length: {len(truncated)} chars")
    print()

    # Test 4: Budget calculation
    sample_text = "This is a sample email for budget calculation. " * 20
    budget = get_token_budget_remaining(sample_text)
    print(f"Test 4: Output budget")
    print(f"  Input tokens: {counter.estimate_tokens(sample_text)}")
    print(f"  Remaining output budget: {budget} tokens")
