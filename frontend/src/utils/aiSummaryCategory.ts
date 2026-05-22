import type { AIUniversalCategory } from "../types/api";

export const AI_SUMMARY_CATEGORY_LABEL_KEY = "ai_summary_category.label";

const AI_SUMMARY_CATEGORY_KEYS: Record<AIUniversalCategory, string> = {
  ACTION_REQUIRED: "ai_summary_category.ACTION_REQUIRED",
  FINANCIAL_LEGAL: "ai_summary_category.FINANCIAL_LEGAL",
  SECURITY_ACCOUNT: "ai_summary_category.SECURITY_ACCOUNT",
  PROJECT_WORK: "ai_summary_category.PROJECT_WORK",
  CONVERSATION: "ai_summary_category.CONVERSATION",
  SCHEDULING: "ai_summary_category.SCHEDULING",
  CONTENT_INFO: "ai_summary_category.CONTENT_INFO",
  AUTOMATED_SYSTEM: "ai_summary_category.AUTOMATED_SYSTEM",
  PERSONAL_SOCIAL: "ai_summary_category.PERSONAL_SOCIAL",
  UNCATEGORIZED: "ai_summary_category.UNCATEGORIZED",
};

export function getAISummaryCategoryKey(category: AIUniversalCategory): string {
  return AI_SUMMARY_CATEGORY_KEYS[category];
}
