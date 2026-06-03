export const AI_SUMMARY_CATEGORY_LABEL_KEY = "ai_summary_category.label";

const LEGACY_AI_SUMMARY_CATEGORY_TO_DIM1_CATEGORY: Record<string, string> = {
  ACTION_REQUIRED: "action_required",
  FINANCIAL_LEGAL: "finance",
  SCHEDULING: "meeting",
  PROJECT_WORK: "informational",
  CONTENT_INFO: "informational",
  AUTOMATED_SYSTEM: "alert",
  SECURITY_ACCOUNT: "alert",
  CONVERSATION: "informational",
  PERSONAL_SOCIAL: "informational",
  UNCATEGORIZED: "informational",
};

export function getAISummaryCategoryI18nValue(category: string): string {
  const trimmed = category.trim();
  if (trimmed === "") return trimmed;

  if (Object.prototype.hasOwnProperty.call(LEGACY_AI_SUMMARY_CATEGORY_TO_DIM1_CATEGORY, trimmed)) {
    return LEGACY_AI_SUMMARY_CATEGORY_TO_DIM1_CATEGORY[trimmed];
  }

  return trimmed
    .replace(/([a-z])([A-Z])/g, "$1_$2")
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1_$2")
    .replace(/[\s-]+/g, "_")
    .toLowerCase();
}
