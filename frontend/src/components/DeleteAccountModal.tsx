import { motion } from 'framer-motion';
import { X, AlertTriangle, RefreshCw } from 'lucide-react';
import { useEffect, useState } from 'react';
import { FocusTrap } from './FocusTrap';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  isDeleting: boolean;
  error?: string | null;
}

const CONFIRM_PHRASE = 'DELETE MY ACCOUNT';
const TITLE_ID = 'delete-account-title';
const DESC_ID = 'delete-account-desc';

const CONSEQUENCES = [
  'All emails and summaries will be deleted.',
  'All account connections will be removed.',
  'Your preferences and templates will be deleted.',
  'This action cannot be undone.',
];

export function DeleteAccountModal({ isOpen, onClose, onSuccess, isDeleting, error }: Props) {
  const [step, setStep] = useState<1 | 2>(1);
  const [confirmPhrase, setConfirmPhrase] = useState('');

  useEffect(() => {
    if (isOpen) {
      setStep(1);
      setConfirmPhrase('');
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const phraseMatches = confirmPhrase === CONFIRM_PHRASE;

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
      {/* Backdrop — aria-hidden so SR focus stays inside dialog */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[150] bg-black/70 backdrop-blur-sm"
        aria-hidden="true"
      />

      {/* Centering layer */}
      <div className="fixed inset-0 z-[200] flex items-end sm:items-center justify-center p-0 sm:p-6 pointer-events-none">
        <FocusTrap initialFocusSelector="[data-modal-close]">
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 16 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            role="dialog"
            aria-modal="true"
            aria-labelledby={TITLE_ID}
            aria-describedby={DESC_ID}
            className="pointer-events-auto w-full h-full sm:h-auto sm:max-h-[90vh] sm:max-w-md bg-brand-surface border-0 sm:border sm:border-brand-border rounded-none sm:rounded-2xl shadow-2xl flex flex-col overflow-hidden"
          >
            {/* Header */}
            <div className="flex-shrink-0 bg-brand-surface border-b border-white/5 px-4 py-4 sm:px-6 sm:py-5">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <h2
                    id={TITLE_ID}
                    className="text-xl font-black text-white leading-tight"
                  >
                    Delete Account
                  </h2>
                  <p
                    id={DESC_ID}
                    className="mt-1 text-sm text-slate-400"
                  >
                    {step === 1
                      ? 'Review what will be permanently deleted.'
                      : 'Confirm to permanently delete your account.'}
                  </p>
                </div>
                <button
                  data-modal-close
                  type="button"
                  onClick={handleClose}
                  disabled={isDeleting}
                  aria-label="Close"
                  className="inline-flex items-center justify-center min-h-[44px] min-w-[44px] sm:min-h-0 sm:min-w-0 sm:p-2 rounded-xl hover:bg-white/10 text-slate-400 hover:text-white transition-colors flex-shrink-0 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto custom-scrollbar px-5 py-6 sm:px-6">
              {step === 1 ? (
                <div className="rounded-2xl border border-rose-500/20 bg-rose-500/10 px-4 py-4">
                  <div className="flex items-center gap-2 mb-3">
                    <AlertTriangle size={16} className="text-rose-400 flex-shrink-0" />
                    <p className="text-xs font-black uppercase tracking-wide text-rose-300">
                      This action is irreversible
                    </p>
                  </div>
                  <ul className="space-y-2">
                    {CONSEQUENCES.map((consequence) => (
                      <li
                        key={consequence}
                        className="flex items-start gap-2 text-sm text-rose-100/80"
                      >
                        <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-rose-400 flex-shrink-0" />
                        {consequence}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <div className="space-y-4">
                  <p className="text-sm text-slate-300">
                    Type{' '}
                    <span className="font-black text-rose-300 tracking-wide">
                      DELETE MY ACCOUNT
                    </span>{' '}
                    to confirm permanent deletion.
                  </p>
                  <input
                    id="delete-account-confirm-input"
                    name="confirmPhrase"
                    type="text"
                    value={confirmPhrase}
                    onChange={(e) => setConfirmPhrase(e.target.value)}
                    disabled={isDeleting}
                    placeholder="DELETE MY ACCOUNT"
                    autoComplete="off"
                    aria-label="Type DELETE MY ACCOUNT to confirm"
                    className="w-full px-3 py-2 rounded-xl bg-white/[0.04] border border-white/10 text-slate-200 placeholder-slate-600 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-rose-500/50 focus:border-rose-500/50 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                  />
                </div>
              )}
              {error && (
                <p className="text-xs text-rose-400">
                  {error}
                </p>
              )}
            </div>

            {/* Footer */}
            <div className="flex-shrink-0 border-t border-white/[0.12] bg-brand-surface px-4 py-3 sm:px-6 sm:py-4">
              <div className="flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={handleClose}
                  disabled={isDeleting}
                  className="inline-flex items-center justify-center min-h-[44px] sm:min-h-0 sm:py-2 px-4 rounded-xl bg-white/[0.05] border border-white/10 text-slate-400 hover:text-white text-xs font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Cancel
                </button>
                {step === 1 ? (
                  <button
                    type="button"
                    onClick={() => setStep(2)}
                    className="inline-flex items-center justify-center gap-1.5 min-h-[44px] sm:min-h-0 sm:py-2 px-5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold transition-all shadow-lg shadow-rose-600/20"
                  >
                    Continue
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={handleConfirm}
                    disabled={!phraseMatches || isDeleting}
                    className="inline-flex items-center justify-center gap-1.5 min-h-[44px] sm:min-h-0 sm:py-2 px-5 rounded-xl bg-rose-600 hover:bg-rose-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-bold transition-all shadow-lg shadow-rose-600/20"
                  >
                    {isDeleting ? (
                      <>
                        <RefreshCw size={12} className="animate-spin" />
                        Deleting…
                      </>
                    ) : (
                      'Delete My Account'
                    )}
                  </button>
                )}
              </div>
            </div>
          </motion.div>
        </FocusTrap>
      </div>
    </>
  );
}

export default DeleteAccountModal;
