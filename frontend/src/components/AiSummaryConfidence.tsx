import React, { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { EmailViewModel } from '@types';
import { deriveAiSummaryConfidence } from '@utils/deriveAiSummaryConfidence';
import { ensureLocaleLoaded } from '@/i18n';
import type { AppShellLanguage } from '@/i18n';

interface Props {
  email: EmailViewModel;
  className?: string;
}

const AI_LANGUAGES = ['en', 'de', 'fr', 'es', 'pt-BR', 'tr', 'ar', 'zh', 'ja', 'ko'] as const;
type AiLanguage = typeof AI_LANGUAGES[number];

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

function resolveAiLanguage(email: EmailViewModel): AiLanguage | null {
  const pref = email.ai_preferred_language ?? '';
  if ((AI_LANGUAGES as readonly string[]).includes(pref)) return pref as AiLanguage;
  const sum = email.ai_summary_language ?? '';
  if ((AI_LANGUAGES as readonly string[]).includes(sum)) return sum as AiLanguage;
  return null;
}

export default function AiSummaryConfidence({ email, className }: Props) {
  const { t, i18n } = useTranslation();
  const confidence = deriveAiSummaryConfidence(email);
  const targetLang = resolveAiLanguage(email);

  const [localeReady, setLocaleReady] = useState(false);
  const [resolvedLang, setResolvedLang] = useState<string | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    if (!targetLang || targetLang === 'en') {
      setResolvedLang(targetLang);
      setLocaleReady(true);
      return;
    }
    setLocaleReady(false);
    setResolvedLang(null);
    let cancelled = false;
    ensureLocaleLoaded(targetLang as AppShellLanguage).then((resolved) => {
      if (!cancelled && mountedRef.current) {
        setResolvedLang(resolved);
        setLocaleReady(true);
      }
    }).catch(() => {
      if (!cancelled && mountedRef.current) {
        setResolvedLang('en');
        setLocaleReady(true);
      }
    });
    return () => { cancelled = true; };
  }, [targetLang]);

  if (!localeReady) {
    return <div className={className} aria-busy="true" />;
  }

  const tFn = resolvedLang ? i18n.getFixedT(resolvedLang) : t;

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
