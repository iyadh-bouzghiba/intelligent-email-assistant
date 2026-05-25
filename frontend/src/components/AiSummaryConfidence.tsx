import React from 'react';
import { useTranslation } from 'react-i18next';
import { EmailViewModel } from '@types';
import { deriveAiSummaryConfidence } from '@utils/deriveAiSummaryConfidence';

interface Props {
  email: EmailViewModel;
  className?: string;
}

const FIXED_T_LANGS = ['en', 'fr', 'ar', 'de', 'es', 'pt-BR', 'zh', 'ja', 'ko'] as const;

const reasonKeyMap = {
  fallback_summary: 'modal.confidence_reason_fallback_summary',
  summary_too_short: 'modal.confidence_reason_summary_too_short',
  language_mismatch: 'modal.confidence_reason_language_mismatch',
  signal_incomplete: 'modal.confidence_reason_signal_incomplete',
} as const;

const badgeClass: Record<string, string> = {
  high: 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-300',
  medium: 'bg-white/[0.03] border border-white/10 text-slate-300',
  low: 'bg-rose-500/10 border border-rose-500/20 text-rose-300',
};

const reasonTextClass: Record<string, string> = {
  high: 'text-slate-400',
  medium: 'text-slate-400',
  low: 'text-rose-400/80',
};

export default function AiSummaryConfidence({ email, className }: Props) {
  const { t, i18n } = useTranslation();
  const confidence = deriveAiSummaryConfidence(email);

  const prefLang = email.ai_preferred_language ?? '';
  const sumLang = email.ai_summary_language ?? '';

  let tFn = t;
  if ((FIXED_T_LANGS as readonly string[]).includes(prefLang)) {
    tFn = i18n.getFixedT(prefLang);
  } else if ((FIXED_T_LANGS as readonly string[]).includes(sumLang)) {
    tFn = i18n.getFixedT(sumLang);
  }

  const levelLabel: Record<string, string> = {
    high: tFn('modal.confidence_high'),
    medium: tFn('modal.confidence_medium'),
    low: tFn('modal.confidence_low'),
  };

  return (
    <div className={className}>
      <span
        className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${badgeClass[confidence.level]}`}
        aria-label={tFn('modal.confidence_aria_label', { level: levelLabel[confidence.level] })}
      >
        <span className="opacity-60">{tFn('modal.confidence_label')}</span>
        <span>{levelLabel[confidence.level]}</span>
      </span>

      {confidence.reasons.length > 0 && (
        <p className={`mt-1 text-xs ${reasonTextClass[confidence.level]}`}>
          {confidence.reasons.map((r) => tFn(reasonKeyMap[r])).join(' · ')}
        </p>
      )}

      {confidence.level === 'low' && confidence.reviewRequired && (
        <div
          role="alert"
          className="mt-2 rounded-xl border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-xs text-rose-300"
        >
          {tFn('modal.confidence_low_warning')}
        </div>
      )}
    </div>
  );
}
