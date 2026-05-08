import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import en from './locales/en.json';
import ar from './locales/ar.json';
import fr from './locales/fr.json';

export const APP_LANG_STORAGE_KEY = 'eb_lang';

export type AppShellLanguage = 'en' | 'ar' | 'fr';

export const SUPPORTED_APP_LANGUAGES: AppShellLanguage[] = ['en', 'ar', 'fr'];

const isSupportedAppLanguage = (value: string | null): value is AppShellLanguage => {
    return value === 'en' || value === 'ar' || value === 'fr';
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
    const resolvedLanguage: AppShellLanguage =
        language === 'ar' || language === 'fr' ? language : 'en';

    if (typeof window !== 'undefined') {
        window.localStorage.setItem(APP_LANG_STORAGE_KEY, resolvedLanguage);
    }

    applyDocumentLanguage(resolvedLanguage);
});

export default i18n;
