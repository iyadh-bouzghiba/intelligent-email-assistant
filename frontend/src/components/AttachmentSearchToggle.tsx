import { Paperclip } from 'lucide-react';

interface AttachmentSearchToggleProps {
  isActive: boolean;
  label: string;
  isRTL: boolean;
  disabled?: boolean;
  onToggle: () => void;
}

const AttachmentSearchToggle = ({ isActive, label, isRTL, disabled, onToggle }: AttachmentSearchToggleProps) => (
  <button
    type="button"
    role="switch"
    aria-checked={isActive}
    aria-pressed={isActive}
    aria-label={label}
    disabled={disabled}
    onClick={onToggle}
    className={`flex items-center gap-1.5 min-h-[44px] px-3 flex-shrink-0 rounded-xl text-xs font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/60 border ${
      disabled
        ? 'bg-white/[0.02] border-white/[0.04] text-slate-700 cursor-not-allowed opacity-50'
        : isActive
          ? 'bg-primary-600/20 border-primary-500/40 text-primary-400'
          : 'bg-white/[0.04] border-white/[0.08] text-slate-500 hover:text-slate-300'
    } ${isRTL ? 'flex-row-reverse' : ''}`}
  >
    <Paperclip size={13} aria-hidden="true" />
    <span>{label}</span>
  </button>
);

export default AttachmentSearchToggle;
