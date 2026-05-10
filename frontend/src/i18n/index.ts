import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import en from './locales/en.json';
import ar from './locales/ar.json';
import fr from './locales/fr.json';
import ptBR from './locales/pt-BR.json';
import tr from './locales/tr.json';
import ja from './locales/ja.json';
import ko from './locales/ko.json';
import hi from './locales/hi.json';
import id from './locales/id.json';

export const APP_LANG_STORAGE_KEY = 'eb_lang';

export type AppShellLanguage = 'en' | 'ar' | 'fr' | 'pt-BR' | 'tr' | 'ja' | 'ko' | 'hi' | 'id';

export const SUPPORTED_APP_LANGUAGES: AppShellLanguage[] = ['en', 'ar', 'fr', 'pt-BR', 'tr', 'ja', 'ko', 'hi', 'id'];

const isSupportedAppLanguage = (value: string | null): value is AppShellLanguage => {
    return value === 'en' || value === 'ar' || value === 'fr' || value === 'pt-BR' || value === 'tr'
        || value === 'ja' || value === 'ko' || value === 'hi' || value === 'id';
};

export const getStoredAppLanguage = (): AppShellLanguage => {
    if (typeof window === 'undefined') return 'en';

    const stored = window.localStorage.getItem(APP_LANG_STORAGE_KEY);
    return isSupportedAppLanguage(stored) ? stored : 'en';
};

export const getDocumentDirection = (language: AppShellLanguage): 'ltr' | 'rtl' => {
    return language === 'ar' ? 'rtl' : 'ltr';
};

export const applyDocumentLanguage = (language: AppShellLanguage) => {
    if (typeof document === 'undefined') return;

    document.documentElement.lang = language;
    document.documentElement.dir = getDocumentDirection(language);
};

const initialLanguage = getStoredAppLanguage();

const resources = {
    en: { translation: en },
    ar: { translation: ar },
    fr: { translation: fr },
    'pt-BR': { translation: ptBR },
    tr: { translation: tr },
    ja: { translation: ja },
    ko: { translation: ko },
    hi: { translation: hi },
    id: { translation: id },
};

void i18n
    .use(initReactI18next)
    .init({
        resources,
        lng: initialLanguage,
        fallbackLng: 'en',
        supportedLngs: SUPPORTED_APP_LANGUAGES,
        defaultNS: 'translation',
        ns: ['translation'],
        interpolation: {
            escapeValue: false,
        },
        returnNull: false,
        react: {
            useSuspense: false,
        },
    });

applyDocumentLanguage(initialLanguage);

i18n.on('languageChanged', (language) => {
    const resolvedLanguage: AppShellLanguage = isSupportedAppLanguage(language) ? language : 'en';

    if (typeof window !== 'undefined') {
        window.localStorage.setItem(APP_LANG_STORAGE_KEY, resolvedLanguage);
    }

    applyDocumentLanguage(resolvedLanguage);
});

export default i18n;
