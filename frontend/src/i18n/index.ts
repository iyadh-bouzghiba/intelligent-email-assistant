import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import en from './locales/en.json';
import ar from './locales/ar.json';
import fr from './locales/fr.json';
import ptBR from './locales/pt-BR.json';
import tr from './locales/tr.json';

export const APP_LANG_STORAGE_KEY = 'eb_lang';

export type AppShellLanguage = 'en' | 'ar' | 'fr' | 'pt-BR' | 'tr';

export const SUPPORTED_APP_LANGUAGES: AppShellLanguage[] = ['en', 'ar', 'fr', 'pt-BR', 'tr'];

const isSupportedAppLanguage = (value: string | null): value is AppShellLanguage => {
    return value === 'en' || value === 'ar' || value === 'fr' || value === 'pt-BR' || value === 'tr';
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
