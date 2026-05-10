import { useEffect, useRef, useState } from 'react';
import { Check, Globe } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { AppShellLanguage } from '../i18n';

const LANGUAGE_OPTIONS: Array<{
    code: AppShellLanguage;
    nativeLabel: string;
    shortLabel: string;
}> = [
        {
            code: 'en',
            nativeLabel: 'English',
            shortLabel: 'EN',
        },
        {
            code: 'fr',
            nativeLabel: 'Français',
            shortLabel: 'FR',
        },
        {
            code: 'ar',
            nativeLabel: 'العربية',
            shortLabel: 'AR',
        },
        // Pending native-speaker review before broader production activation.
        {
            code: 'pt-BR',
            nativeLabel: 'Português (Brasil)',
            shortLabel: 'PT',
        },
        // Pending native-speaker review before broader production activation.
        {
            code: 'tr',
            nativeLabel: 'Türkçe',
            shortLabel: 'TR',
        },
        // Pending native-speaker review before broader production activation.
        {
            code: 'ja',
            nativeLabel: '日本語',
            shortLabel: 'JA',
        },
        // Pending native-speaker review before broader production activation.
        {
            code: 'ko',
            nativeLabel: '한국어',
            shortLabel: 'KO',
        },
        // Pending native-speaker review before broader production activation.
        {
            code: 'hi',
            nativeLabel: 'हिन्दी',
            shortLabel: 'HI',
        },
        // Pending native-speaker review before broader production activation.
        {
            code: 'id',
            nativeLabel: 'Bahasa Indonesia',
            shortLabel: 'ID',
        },
    ];

const resolveAppLanguage = (language: string | undefined): AppShellLanguage => {
    return language === 'ar' || language === 'fr' || language === 'pt-BR' || language === 'tr'
        || language === 'ja' || language === 'ko' || language === 'hi' || language === 'id'
        ? language : 'en';
};

export function GlobeButton() {
    const { i18n, t } = useTranslation();
    const [isOpen, setIsOpen] = useState(false);
    const rootRef = useRef<HTMLDivElement | null>(null);

    const activeLanguage = resolveAppLanguage(i18n.resolvedLanguage ?? i18n.language);
    const activeOption = LANGUAGE_OPTIONS.find((option) => option.code === activeLanguage) ?? LANGUAGE_OPTIONS[0];

    useEffect(() => {
        if (!isOpen) return;

        const handleDocumentMouseDown = (event: MouseEvent) => {
            if (!rootRef.current) return;
            if (rootRef.current.contains(event.target as Node)) return;

            setIsOpen(false);
        };

        const handleDocumentKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                setIsOpen(false);
            }
        };

        document.addEventListener('mousedown', handleDocumentMouseDown);
        document.addEventListener('keydown', handleDocumentKeyDown);

        return () => {
            document.removeEventListener('mousedown', handleDocumentMouseDown);
            document.removeEventListener('keydown', handleDocumentKeyDown);
        };
    }, [isOpen]);

    const handleLanguageSelect = (language: AppShellLanguage) => {
        if (language !== activeLanguage) {
            void i18n.changeLanguage(language);
        }

        setIsOpen(false);
    };

    return (
        <div ref={rootRef} className="relative flex-shrink-0">
            <button
                type="button"
                aria-haspopup="menu"
                aria-expanded={isOpen}
                aria-label={t('nav.language_picker_label')}
                title={t('nav.language_picker_label')}
                onClick={() => setIsOpen((current) => !current)}
                className="inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.05] text-slate-200 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/60 focus-visible:ring-offset-2 focus-visible:ring-offset-brand-bg"
            >
                <Globe size={14} aria-hidden="true" />
                <span className="text-[11px] font-black uppercase tracking-[0.18em]">
                    {activeOption.shortLabel}
                </span>
            </button>

            {isOpen && (
                <div
                    role="menu"
                    aria-label={t('nav.language_picker_label')}
                    className="fixed left-3 right-3 top-20 z-[340] rounded-2xl border border-white/10 bg-brand-surface/95 backdrop-blur-md shadow-2xl shadow-black/30 p-1.5 sm:absolute sm:left-auto sm:right-0 sm:top-full sm:mt-2 sm:w-44"
                >
                    <div className="space-y-1">
                        {LANGUAGE_OPTIONS.map((option) => {
                            const isActive = option.code === activeLanguage;

                            return (
                                <button
                                    key={option.code}
                                    type="button"
                                    role="menuitemradio"
                                    aria-checked={isActive}
                                    onClick={() => handleLanguageSelect(option.code)}
                                    className={`w-full flex items-center justify-between gap-3 rounded-xl px-3 py-2 text-sm transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/60 ${isActive
                                        ? 'bg-primary-500/16 border border-primary-400/30 text-primary-100'
                                        : 'border border-transparent text-slate-300 hover:bg-white/[0.04] hover:text-white'
                                        }`}
                                >
                                    <span className="font-semibold">{option.nativeLabel}</span>
                                    {isActive ? <Check size={14} aria-hidden="true" /> : <span className="w-[14px]" aria-hidden="true" />}
                                </button>
                            );
                        })}
                    </div>
                </div>
            )}
        </div>
    );
}
