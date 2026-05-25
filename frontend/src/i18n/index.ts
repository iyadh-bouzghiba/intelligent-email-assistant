import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

export const APP_LANG_STORAGE_KEY = 'eb_lang';

export type AppShellLanguage = 'en' | 'ar' | 'fr' | 'pt-BR' | 'tr' | 'ja' | 'ko' | 'hi' | 'id' | 'zh' | 'de' | 'es';

export const SUPPORTED_APP_LANGUAGES: AppShellLanguage[] = ['en', 'ar', 'fr', 'pt-BR', 'tr', 'ja', 'ko', 'hi', 'id', 'zh', 'de', 'es'];

type TranslationMessages = Record<string, unknown>;
type LocaleModule = { default: TranslationMessages };

const localeLoaders: Record<AppShellLanguage, () => Promise<LocaleModule>> = {
    en: () => import('./locales/en.json'),
    ar: () => import('./locales/ar.json'),
    fr: () => import('./locales/fr.json'),
    'pt-BR': () => import('./locales/pt-BR.json'),
    tr: () => import('./locales/tr.json'),
    ja: () => import('./locales/ja.json'),
    ko: () => import('./locales/ko.json'),
    hi: () => import('./locales/hi.json'),
    id: () => import('./locales/id.json'),
    zh: () => import('./locales/zh.json'),
    de: () => import('./locales/de.json'),
    es: () => import('./locales/es.json'),
};

const loadedLanguages = new Set<AppShellLanguage>();

let initializationPromise: Promise<typeof i18n> | null = null;
let languageChangedHandlerAttached = false;

const isSupportedAppLanguage = (value: string | null | undefined): value is AppShellLanguage => {
    return value === 'en' || value === 'ar' || value === 'fr' || value === 'pt-BR' || value === 'tr'
        || value === 'ja' || value === 'ko' || value === 'hi' || value === 'id'
        || value === 'zh' || value === 'de' || value === 'es';
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

const persistResolvedLanguage = (language: AppShellLanguage) => {
    if (typeof window !== 'undefined') {
        window.localStorage.setItem(APP_LANG_STORAGE_KEY, language);
    }

    applyDocumentLanguage(language);
};

const attachLanguageChangedHandler = () => {
    if (languageChangedHandlerAttached) return;

    i18n.on('languageChanged', (language) => {
        const resolvedLanguage: AppShellLanguage = isSupportedAppLanguage(language) ? language : 'en';
        persistResolvedLanguage(resolvedLanguage);
    });

    languageChangedHandlerAttached = true;
};

const loadLocaleMessages = async (language: AppShellLanguage): Promise<TranslationMessages> => {
    const module = await localeLoaders[language]();
    return module.default;
};

const registerLocaleBundle = (language: AppShellLanguage, messages: TranslationMessages) => {
    if (i18n.hasResourceBundle(language, 'translation')) {
        loadedLanguages.add(language);
        return;
    }

    i18n.addResourceBundle(language, 'translation', messages, true, true);
    loadedLanguages.add(language);
};

const resolveInitialLocale = async (requestedLanguage: AppShellLanguage): Promise<{
    language: AppShellLanguage;
    messages: TranslationMessages;
}> => {
    try {
        const messages = await loadLocaleMessages(requestedLanguage);
        return {
            language: requestedLanguage,
            messages,
        };
    } catch (error) {
        console.error(`[i18n] Failed to load initial locale chunk "${requestedLanguage}". Falling back to "en".`, error);

        const fallbackMessages = await loadLocaleMessages('en');
        return {
            language: 'en',
            messages: fallbackMessages,
        };
    }
};

export const ensureLocaleLoaded = async (language: AppShellLanguage): Promise<AppShellLanguage> => {
    if (loadedLanguages.has(language) || i18n.hasResourceBundle(language, 'translation')) {
        loadedLanguages.add(language);
        return language;
    }

    try {
        const messages = await loadLocaleMessages(language);
        registerLocaleBundle(language, messages);
        return language;
    } catch (error) {
        console.error(`[i18n] Failed to load locale chunk "${language}". Falling back to "en".`, error);

        if (!loadedLanguages.has('en') && !i18n.hasResourceBundle('en', 'translation')) {
            const fallbackMessages = await loadLocaleMessages('en');
            registerLocaleBundle('en', fallbackMessages);
        }

        return 'en';
    }
};

export const initializeI18n = async (): Promise<typeof i18n> => {
    if (i18n.isInitialized) {
        attachLanguageChangedHandler();
        return i18n;
    }

    if (initializationPromise) {
        return initializationPromise;
    }

    initializationPromise = (async () => {
        const requestedInitialLanguage = getStoredAppLanguage();
        const initialLocale = await resolveInitialLocale(requestedInitialLanguage);

        await i18n
            .use(initReactI18next)
            .init({
                resources: {
                    [initialLocale.language]: {
                        translation: initialLocale.messages,
                    },
                },
                lng: initialLocale.language,
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

        loadedLanguages.add(initialLocale.language);
        persistResolvedLanguage(initialLocale.language);
        attachLanguageChangedHandler();

        return i18n;
    })();

    try {
        return await initializationPromise;
    } catch (error) {
        initializationPromise = null;
        throw error;
    }
};

export const changeAppLanguage = async (language: AppShellLanguage): Promise<AppShellLanguage> => {
    await initializeI18n();

    const requestedLanguage = isSupportedAppLanguage(language) ? language : 'en';

    try {
        const resolvedLanguage = await ensureLocaleLoaded(requestedLanguage);
        await i18n.changeLanguage(resolvedLanguage);
        return resolvedLanguage;
    } catch (error) {
        console.error(`[i18n] Failed to switch app language to "${requestedLanguage}". Falling back to "en".`, error);

        const fallbackLanguage = await ensureLocaleLoaded('en');
        await i18n.changeLanguage(fallbackLanguage);
        return fallbackLanguage;
    }
};

export default i18n;