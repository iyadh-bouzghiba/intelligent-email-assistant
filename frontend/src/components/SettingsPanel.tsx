import { motion } from 'framer-motion';
import { AlertTriangle, X } from 'lucide-react';
import { useEffect } from 'react';
import { useTranslation as useI18nTranslation } from 'react-i18next';
import { FocusTrap } from './FocusTrap';

interface SettingsPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onDeleteAllData: () => void;
}

const TITLE_ID = 'settings-panel-title';

const LANGUAGE_LABEL_KEYS: Record<string, string> = {
  en: 'languages.english',
  fr: 'languages.french',
  ar: 'languages.arabic',
  'pt-BR': 'languages.portuguese_brazil',
  de: 'languages.german',
  es: 'languages.spanish',
  zh: 'languages.chinese',
  ja: 'languages.japanese',
  ko: 'languages.korean',
  tr: 'languages.turkish',
};

export default function SettingsPanel({
  isOpen,
  onClose,
  onDeleteAllData,
}: SettingsPanelProps) {
  const { t, i18n } = useI18nTranslation();

  useEffect(() => {
    if (isOpen) {
      document.body.classList.add('panel-open');
    } else {
      document.body.classList.remove('panel-open');
    }

    return () => {
      document.body.classList.remove('panel-open');
    };
  }, [isOpen]);

  if (!isOpen) return null;

  const languageCode = i18n.resolvedLanguage ?? i18n.language ?? 'en';
  const languageLabelKey = LANGUAGE_LABEL_KEYS[languageCode] ?? 'languages.english';

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[150] bg-black/70 backdrop-blur-sm"
        aria-hidden="true"
      />

      <div className="fixed inset-0 z-[200] flex items-end justify-center p-0 pointer-events-none sm:items-center sm:p-6">
        <FocusTrap initialFocusSelector="[data-modal-close]">
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 16 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            role="dialog"
            aria-modal="true"
            aria-labelledby={TITLE_ID}
            className="pointer-events-auto flex w-full flex-col rounded-none border border-brand-border bg-brand-surface shadow-2xl sm:max-w-sm sm:rounded-2xl"
          >
            <div className="flex items-center justify-between gap-4 border-b border-white/5 px-5 py-4">
              <h2 id={TITLE_ID} className="text-sm font-bold text-white">
                {t('settings_panel.title')}
              </h2>
              <button
                data-modal-close
                type="button"
                onClick={onClose}
                aria-label={t('common.close')}
                className="inline-flex min-h-[44px] min-w-[44px] flex-shrink-0 items-center justify-center rounded-xl text-slate-400 transition-colors hover:bg-white/10 hover:text-white"
              >
                <X size={18} aria-hidden="true" />
              </button>
            </div>

            <div className="space-y-4 px-5 pb-5 pt-4">
              <section className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-xs font-semibold text-slate-400">
                    {t('settings_panel.language_label')}
                  </p>
                  <p className="text-xs font-medium text-white">
                    {t(languageLabelKey)}
                  </p>
                </div>
                <p className="mt-1 text-xs italic text-slate-500">
                  {t('nav.language_picker_label')}
                </p>
              </section>

              <section className="space-y-3 rounded-xl border border-rose-500/30 bg-rose-500/5 p-4">
                <div className="flex items-center gap-2">
                  <AlertTriangle size={14} className="flex-shrink-0 text-rose-400" aria-hidden="true" />
                  <h3 className="text-xs font-bold uppercase tracking-wide text-rose-400">
                    {t('settings_panel.danger_zone_title')}
                  </h3>
                </div>

                <p className="text-xs text-slate-400">
                  {t('settings_panel.danger_zone_subtitle')}
                </p>

                <p className="text-xs leading-relaxed text-slate-500">
                  {t('settings_panel.delete_all_description')}
                </p>

                <button
                  type="button"
                  onClick={onDeleteAllData}
                  className="min-h-[44px] w-full rounded-xl bg-rose-600 text-xs font-bold text-white transition-all hover:bg-rose-500"
                >
                  {t('settings_panel.delete_all_btn')}
                </button>
              </section>
            </div>
          </motion.div>
        </FocusTrap>
      </div>
    </>
  );
}
