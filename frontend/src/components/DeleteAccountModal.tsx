import { motion } from 'framer-motion';
import { AlertTriangle, Check, RefreshCw, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useTranslation as useI18nTranslation } from 'react-i18next';
import { AccountInfo } from '@types';
import { FocusTrap } from './FocusTrap';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (accountId: string) => void;
  isDisconnecting: boolean;
  connectedAccounts: AccountInfo[];
  error?: string | null;
  onDeleteAllData?: () => void;
}

const DISCONNECT_PHRASE = 'DISCONNECT ACCOUNT';
const TITLE_ID = 'disconnect-account-title';
const DESC_ID = 'disconnect-account-desc';

const CONSEQUENCE_KEYS = [
  'delete_modal.consequence_credentials',
  'delete_modal.consequence_sync_stops',
  'delete_modal.consequence_data_preserved',
  'delete_modal.consequence_gmail_safe',
  'delete_modal.consequence_reconnect',
  'delete_modal.consequence_others_safe',
];

export function DeleteAccountModal({
  isOpen,
  onClose,
  onSuccess,
  isDisconnecting,
  connectedAccounts,
  error,
  onDeleteAllData,
}: Props) {
  const { t } = useI18nTranslation();
  const [step, setStep] = useState<1 | 2>(1);
  const [selectedAccountId, setSelectedAccountId] = useState('');
  const [confirmPhrase, setConfirmPhrase] = useState('');

  useEffect(() => {
    if (isOpen) {
      setStep(1);
      setSelectedAccountId('');
      setConfirmPhrase('');
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const phraseMatches = confirmPhrase === DISCONNECT_PHRASE;

  const handleClose = () => {
    if (isDisconnecting) return;
    onClose();
  };

  const handleConfirm = () => {
    if (!phraseMatches || isDisconnecting || selectedAccountId === '') return;
    onSuccess(selectedAccountId);
  };

  const handleContinue = () => {
    if (selectedAccountId === '' || isDisconnecting) return;
    setStep(2);
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
                    {t('delete_modal.title')}
                  </h2>
                  <p
                    id={DESC_ID}
                    className="mt-1 text-sm text-slate-400"
                  >
                    {step === 1
                      ? t('delete_modal.subtitle_select')
                      : t('delete_modal.subtitle_confirm')}
                  </p>
                </div>
                <button
                  data-modal-close
                  type="button"
                  onClick={handleClose}
                  disabled={isDisconnecting}
                  aria-label={t('common.close')}
                  className="inline-flex items-center justify-center min-h-[44px] min-w-[44px] sm:min-h-0 sm:min-w-0 sm:p-2 rounded-xl hover:bg-white/10 text-slate-400 hover:text-white transition-colors flex-shrink-0 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto custom-scrollbar px-5 py-6 sm:px-6">
              {step === 1 ? (
                <div className="space-y-4">
                  <div className="rounded-2xl border border-rose-500/20 bg-rose-500/10 px-4 py-4">
                    <div className="flex items-center gap-2 mb-3">
                      <AlertTriangle size={16} className="text-rose-400 flex-shrink-0" />
                      <p className="text-xs font-black uppercase tracking-wide text-rose-300">
                        {t('delete_modal.irreversible_warning')}
                      </p>
                    </div>
                    <ul className="space-y-2">
                      {CONSEQUENCE_KEYS.map((key) => (
                        <li
                          key={key}
                          className="flex items-start gap-2 text-sm text-rose-100/80"
                        >
                          <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-rose-400 flex-shrink-0" />
                          {t(key)}
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div className="space-y-2" role="radiogroup" aria-label={t('delete_modal.select_account_label')}>
                    <p className="text-xs font-bold uppercase tracking-wide text-slate-400">
                      {t('delete_modal.select_account_label')}
                    </p>
                    {connectedAccounts.map((account) => {
                      const isSelected = selectedAccountId === account.account_id;

                      return (
                        <button
                          key={account.account_id}
                          type="button"
                          role="radio"
                          aria-checked={isSelected}
                          aria-pressed={isSelected}
                          onClick={() => setSelectedAccountId(account.account_id)}
                          disabled={isDisconnecting}
                          className={`flex min-h-[44px] w-full items-center justify-between gap-3 rounded-2xl px-4 py-3 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                            isSelected
                              ? 'border border-rose-500/70 bg-rose-500/10 text-white'
                              : 'border border-white/10 bg-white/[0.04] text-slate-200 hover:border-rose-500/40'
                          }`}
                        >
                          <span className="min-w-0 flex-1 truncate text-sm font-semibold">
                            {account.account_id}
                          </span>
                          <span className="flex flex-shrink-0 items-center gap-2">
                            {account.auth_required && (
                              <span className="rounded-full border border-amber-400/30 bg-amber-400/10 px-2 py-1 text-[10px] font-black uppercase tracking-wide text-amber-200">
                                Reconnect required
                              </span>
                            )}
                            {isSelected && (
                              <Check size={16} className="text-rose-300" aria-hidden="true" />
                            )}
                          </span>
                        </button>
                      );
                    })}
                  </div>

                  {selectedAccountId === '' && (
                    <p className="text-xs text-slate-500">
                      {t('delete_modal.no_account_selected')}
                    </p>
                  )}

                  <p className="text-xs text-slate-500">
                    {t('delete_modal.gmail_not_deleted_notice')}
                  </p>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-4">
                    <p className="text-xs font-bold uppercase tracking-wide text-rose-300">
                      {t('delete_modal.selected_account_label')}
                    </p>
                    <p className="mt-2 break-all text-sm font-black text-white">
                      {selectedAccountId}
                    </p>
                  </div>

                  <p className="text-sm text-slate-300">
                    {t('delete_modal.confirm_instruction')}{' '}
                    <span className="font-black text-rose-300 tracking-wide">
                      DISCONNECT ACCOUNT
                    </span>
                  </p>

                  <input
                    id="disconnect-account-confirm-input"
                    name="confirmPhrase"
                    type="text"
                    value={confirmPhrase}
                    onChange={(e) => setConfirmPhrase(e.target.value)}
                    disabled={isDisconnecting}
                    placeholder="DISCONNECT ACCOUNT"
                    autoComplete="off"
                    aria-label={t('delete_modal.confirm_instruction')}
                    className="w-full min-h-[44px] px-3 py-2 rounded-xl bg-white/[0.04] border border-white/10 text-slate-200 placeholder-slate-600 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-rose-500/50 focus:border-rose-500/50 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                  />
                </div>
              )}

              {error && (
                <p className="mt-4 text-xs text-rose-400">
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
                  disabled={isDisconnecting}
                  className="inline-flex items-center justify-center min-h-[44px] sm:min-h-0 sm:py-2 px-4 rounded-xl bg-white/[0.05] border border-white/10 text-slate-400 hover:text-white text-xs font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {t('delete_modal.btn_cancel')}
                </button>
                {step === 1 ? (
                  <button
                    type="button"
                    onClick={handleContinue}
                    disabled={selectedAccountId === '' || isDisconnecting}
                    className="inline-flex items-center justify-center gap-1.5 min-h-[44px] sm:min-h-0 sm:py-2 px-5 rounded-xl bg-rose-600 hover:bg-rose-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-bold transition-all shadow-lg shadow-rose-600/20"
                  >
                    {t('delete_modal.btn_continue')}
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={handleConfirm}
                    disabled={!phraseMatches || isDisconnecting}
                    className="inline-flex items-center justify-center gap-1.5 min-h-[44px] sm:min-h-0 sm:py-2 px-5 rounded-xl bg-rose-600 hover:bg-rose-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-bold transition-all shadow-lg shadow-rose-600/20"
                  >
                    {isDisconnecting ? (
                      <>
                        <RefreshCw size={12} className="animate-spin" />
                        {t('delete_modal.btn_disconnecting')}
                      </>
                    ) : (
                      t('delete_modal.btn_confirm')
                    )}
                  </button>
                )}
              </div>

              {onDeleteAllData && (
                <button
                  type="button"
                  onClick={onDeleteAllData}
                  disabled={isDisconnecting}
                  className="mt-3 inline-flex min-h-[44px] w-full items-center justify-center rounded-xl text-xs font-semibold text-slate-500 underline-offset-4 transition-colors hover:text-rose-300 hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {t('delete_modal.delete_all_link')}
                </button>
              )}
            </div>
          </motion.div>
        </FocusTrap>
      </div>
    </>
  );
}

export default DeleteAccountModal;