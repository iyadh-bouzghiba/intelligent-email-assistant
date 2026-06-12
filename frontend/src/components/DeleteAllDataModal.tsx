import { motion } from 'framer-motion';
import { RefreshCw, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useTranslation as useI18nTranslation } from 'react-i18next';
import { FocusTrap } from './FocusTrap';

interface DeleteAllDataModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  isDeleting: boolean;
  error?: string | null;
}

const DELETE_PHRASE = 'DELETE MY ACCOUNT';
const TITLE_ID = 'delete-all-modal-title';

const WILL_DELETE_KEYS = [
  'delete_all_modal.item_emails',
  'delete_all_modal.item_templates',
  'delete_all_modal.item_preferences',
  'delete_all_modal.item_accounts',
];

const WILL_NOT_DELETE_KEYS = [
  'delete_all_modal.item_gmail',
  'delete_all_modal.item_google',
];

export default function DeleteAllDataModal({
  isOpen,
  onClose,
  onSuccess,
  isDeleting,
  error,
}: DeleteAllDataModalProps) {
  const { t } = useI18nTranslation();
  const [confirmPhrase, setConfirmPhrase] = useState('');

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

  useEffect(() => {
    if (isOpen) {
      setConfirmPhrase('');
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const phraseMatches = confirmPhrase === DELETE_PHRASE;

  const handleClose = () => {
    if (isDeleting) return;
    onClose();
  };

  const handleConfirm = () => {
    if (!phraseMatches || isDeleting) return;
    onSuccess();
  };

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
            className="pointer-events-auto flex w-full flex-col rounded-none border border-brand-border bg-brand-surface shadow-2xl sm:max-w-md sm:rounded-2xl"
          >
            <div className="flex items-center justify-between gap-4 border-b border-rose-500/20 bg-rose-950/30 px-5 py-4">
              <h2 id={TITLE_ID} className="text-sm font-bold text-rose-300">
                {t('delete_all_modal.title')}
              </h2>
              <button
                data-modal-close
                type="button"
                onClick={handleClose}
                disabled={isDeleting}
                aria-label={t('common.close')}
                className="inline-flex min-h-[44px] min-w-[44px] flex-shrink-0 items-center justify-center rounded-xl text-slate-400 transition-colors hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                <X size={18} aria-hidden="true" />
              </button>
            </div>

            <div className="space-y-3 px-5 py-4">
              <p className="text-xs text-slate-400">
                {t('delete_all_modal.subtitle')}
              </p>

              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <section className="rounded-xl border border-rose-500/25 bg-rose-500/5 p-3">
                  <p className="mb-2 text-xs font-bold text-rose-400">
                    {t('delete_all_modal.will_delete')}
                  </p>
                  <ul className="space-y-1.5">
                    {WILL_DELETE_KEYS.map((key) => (
                      <li key={key} className="flex items-center gap-1.5 text-xs text-rose-200/70">
                        <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-rose-400" />
                        <span>{t(key)}</span>
                      </li>
                    ))}
                  </ul>
                </section>

                <section className="rounded-xl border border-emerald-500/25 bg-emerald-500/5 p-3">
                  <p className="mb-2 text-xs font-bold text-emerald-400">
                    {t('delete_all_modal.will_not_delete')}
                  </p>
                  <ul className="space-y-1.5">
                    {WILL_NOT_DELETE_KEYS.map((key) => (
                      <li key={key} className="flex items-center gap-1.5 text-xs text-emerald-200/70">
                        <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-emerald-400" />
                        <span>{t(key)}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              </div>

              <div className="border-t border-white/10 pt-3">
                <p className="mb-2 text-xs text-slate-400">
                  {t('delete_all_modal.confirm_instruction')}{' '}
                  <span className="font-bold text-rose-400">
                    DELETE MY ACCOUNT
                  </span>
                </p>

                <input
                  id="delete-all-confirm-input"
                  name="deleteAllConfirmPhrase"
                  type="text"
                  value={confirmPhrase}
                  onChange={(event) => setConfirmPhrase(event.target.value)}
                  placeholder="DELETE MY ACCOUNT"
                  disabled={isDeleting}
                  autoComplete="off"
                  aria-label={t('delete_all_modal.confirm_instruction')}
                  className="w-full rounded-xl border border-white/10 bg-white/[0.05] px-4 py-3 text-sm text-white placeholder:text-slate-500 transition-colors focus:border-rose-500/40 focus:outline-none disabled:opacity-50"
                />

                {error && (
                  <p className="mt-2 text-xs text-rose-400">
                    {error}
                  </p>
                )}
              </div>
            </div>

            <div className="flex justify-end gap-2 px-5 pb-5">
              <button
                type="button"
                onClick={handleClose}
                disabled={isDeleting}
                className="inline-flex min-h-[44px] items-center justify-center rounded-xl border border-white/10 bg-white/[0.05] px-4 text-xs font-bold text-slate-400 transition-colors hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                {t('delete_all_modal.btn_cancel')}
              </button>
              <button
                type="button"
                onClick={handleConfirm}
                disabled={!phraseMatches || isDeleting}
                className="inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-xl bg-rose-600 px-4 text-xs font-bold text-white shadow-lg shadow-rose-600/20 transition-all hover:bg-rose-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isDeleting ? (
                  <>
                    <RefreshCw size={12} className="animate-spin" aria-hidden="true" />
                    {t('delete_all_modal.btn_deleting')}
                  </>
                ) : (
                  t('delete_all_modal.btn_confirm')
                )}
              </button>
            </div>
          </motion.div>
        </FocusTrap>
      </div>
    </>
  );
}
