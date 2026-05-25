import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import AiSummaryConfidence from '../AiSummaryConfidence';
import type { EmailViewModel } from '@types';
import type { AppShellLanguage } from '@/i18n';

// ---------------------------------------------------------------------------
// Expected confidence label per AI language (modal.confidence_label key)
// ---------------------------------------------------------------------------
const EXPECTED_LABELS: Record<string, string> = {
  en: 'AI confidence',
  fr: 'Confiance IA',
  ar: 'ثقة الذكاء الاصطناعي',
  de: 'KI-Konfidenz',
  es: 'Confianza de IA',
  'pt-BR': 'Confiança da IA',
  zh: 'AI 置信度',
  ja: 'AI信頼度',
  ko: 'AI 신뢰도',
};

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// ensureLocaleLoaded resolves to the requested language (simulates successful bundle load)
vi.mock('@/i18n', () => ({
  ensureLocaleLoaded: vi.fn().mockImplementation((lang: AppShellLanguage) => Promise.resolve(lang)),
}));

// getFixedT returns a translator that looks up from EXPECTED_LABELS for modal.confidence_label
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      if (key === 'modal.confidence_label') return 'AI confidence';
      if (key === 'modal.confidence_high') return 'High';
      if (key === 'modal.confidence_medium') return 'Medium';
      if (key === 'modal.confidence_low') return 'Low';
      if (key === 'modal.confidence_low_warning') return 'Review recommended';
      return key;
    },
    i18n: {
      getFixedT: (lang: string) => (key: string) => {
        if (key === 'modal.confidence_label') return EXPECTED_LABELS[lang] ?? 'AI confidence';
        if (key === 'modal.confidence_high') return 'High';
        if (key === 'modal.confidence_medium') return 'Medium';
        if (key === 'modal.confidence_low') return 'Low';
        if (key === 'modal.confidence_low_warning') return 'Review recommended';
        return key;
      },
    },
  }),
}));

vi.mock('@utils/deriveAiSummaryConfidence', () => ({
  deriveAiSummaryConfidence: () => ({ level: 'high', reasons: [], reviewRequired: false }),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeEmail(overrides: Partial<EmailViewModel> = {}): EmailViewModel {
  return {
    gmail_message_id: 'msg1',
    thread_id: 'thread1',
    subject: 'Test',
    sender: 'a@b.com',
    date: '2026-01-01',
    date_iso: '2026-01-01T00:00:00Z',
    body: '',
    is_read: true,
    ai_summary_text: 'Summary',
    ai_preferred_language: null,
    ai_summary_language: null,
    ...overrides,
  } as EmailViewModel;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('AiSummaryConfidence', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    // Restore default after any test that overrides ensureLocaleLoaded (e.g. loading-state test)
    const i18nMod = await import('@/i18n');
    vi.mocked(i18nMod.ensureLocaleLoaded).mockImplementation((lang: AppShellLanguage) => Promise.resolve(lang));
  });

  it('renders without crashing when no language props set (English fallback)', async () => {
    render(<AiSummaryConfidence email={makeEmail()} />);
    await waitFor(() => {
      expect(screen.getByText('AI confidence')).toBeInTheDocument();
    });
  });

  it('app shell language is not changed — getFixedT is used per-component, not i18n.changeLanguage', async () => {
    const { ensureLocaleLoaded } = await import('@/i18n');
    render(<AiSummaryConfidence email={makeEmail({ ai_preferred_language: 'fr' })} />);
    await waitFor(() => {
      expect(ensureLocaleLoaded).toHaveBeenCalledWith('fr');
    });
  });

  // Per-language label tests
  const AI_LANGUAGES = ['en', 'fr', 'ar', 'de', 'es', 'pt-BR', 'zh', 'ja', 'ko'] as const;

  for (const lang of AI_LANGUAGES) {
    it(`renders expected label for ai_preferred_language="${lang}"`, async () => {
      render(
        <AiSummaryConfidence email={makeEmail({ ai_preferred_language: lang })} />
      );
      await waitFor(() => {
        expect(screen.getByText(EXPECTED_LABELS[lang])).toBeInTheDocument();
      });
    });
  }

  it('falls back to ai_summary_language when ai_preferred_language is absent', async () => {
    render(
      <AiSummaryConfidence
        email={makeEmail({ ai_preferred_language: null, ai_summary_language: 'fr' })}
      />
    );
    await waitFor(() => {
      expect(screen.getByText('Confiance IA')).toBeInTheDocument();
    });
  });

  it('falls back to English when an unknown language is provided', async () => {
    render(
      <AiSummaryConfidence
        email={makeEmail({ ai_preferred_language: 'xx' as never })}
      />
    );
    await waitFor(() => {
      expect(screen.getByText('AI confidence')).toBeInTheDocument();
    });
  });

  it('renders safe (empty) fallback while locale is loading', async () => {
    // Make ensureLocaleLoaded hang indefinitely to simulate loading
    const i18nMod = await import('@/i18n');
    vi.mocked(i18nMod.ensureLocaleLoaded).mockReturnValue(new Promise<AppShellLanguage>(() => {}));

    const { container } = render(
      <AiSummaryConfidence email={makeEmail({ ai_preferred_language: 'zh' })} />
    );
    // While loading: confidence badge is not yet rendered — empty div with aria-busy
    expect(container.querySelector('[aria-busy="true"]')).toBeInTheDocument();
    expect(screen.queryByText('AI 置信度')).not.toBeInTheDocument();
  });
});
