import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const BASELINE_LOCALE = 'en';
const LOCALES = ['en', 'ar', 'fr', 'pt-BR', 'tr', 'ja', 'ko', 'hi', 'id', 'zh', 'de', 'es'];

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DEFAULT_LOCALES_DIR = path.resolve(__dirname, '../src/i18n/locales');

function getArgValue(flag) {
    const index = process.argv.indexOf(flag);
    if (index === -1) {
        return null;
    }

    const value = process.argv[index + 1];
    if (!value || value.startsWith('--')) {
        throw new Error(`Missing value for ${flag}`);
    }

    return value;
}

function isPlainObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function flattenKeys(node, prefix = '') {
    if (!isPlainObject(node)) {
        return prefix ? [prefix] : [];
    }

    const keys = [];

    for (const [key, value] of Object.entries(node)) {
        const nextPrefix = prefix ? `${prefix}.${key}` : key;

        if (isPlainObject(value)) {
            const childKeys = flattenKeys(value, nextPrefix);

            if (childKeys.length === 0) {
                keys.push(nextPrefix);
            } else {
                keys.push(...childKeys);
            }
        } else {
            keys.push(nextPrefix);
        }
    }

    return keys;
}

function readLocale(locale, localesDir) {
    const filePath = path.join(localesDir, `${locale}.json`);

    if (!fs.existsSync(filePath)) {
        throw new Error(`Locale file not found: ${filePath}`);
    }

    const raw = fs.readFileSync(filePath, 'utf8');

    try {
        return JSON.parse(raw);
    } catch (error) {
        throw new Error(`Invalid JSON in ${filePath}: ${error.message}`);
    }
}

function uniqueSorted(values) {
    return Array.from(new Set(values)).sort((a, b) => a.localeCompare(b));
}

function printErrorList(items, indent = '  - ') {
    for (const item of items) {
        console.error(`${indent}${item}`);
    }
}

function printWarningList(items, indent = '  - ') {
    for (const item of items) {
        console.warn(`${indent}${item}`);
    }
}

function main() {
    try {
        const localesDirArg = getArgValue('--locales-dir');
        const localesDir = localesDirArg
            ? path.resolve(localesDirArg)
            : DEFAULT_LOCALES_DIR;

        const baselineData = readLocale(BASELINE_LOCALE, localesDir);
        const baselineKeys = uniqueSorted(flattenKeys(baselineData));
        const baselineKeySet = new Set(baselineKeys);

        const failures = [];
        const extras = [];

        for (const locale of LOCALES) {
            const localeData = readLocale(locale, localesDir);
            const localeKeys = uniqueSorted(flattenKeys(localeData));
            const localeKeySet = new Set(localeKeys);

            const missingKeys = baselineKeys.filter((key) => !localeKeySet.has(key));
            const extraKeys =
                locale === BASELINE_LOCALE
                    ? []
                    : localeKeys.filter((key) => !baselineKeySet.has(key));

            if (missingKeys.length > 0) {
                failures.push({ locale, missingKeys });
            }

            if (extraKeys.length > 0) {
                extras.push({ locale, extraKeys });
            }
        }

        if (failures.length > 0) {
            for (const failure of failures) {
                console.error(`✗ PARITY FAILURE in ${failure.locale}:`);
                console.error('  Missing keys:');
                printErrorList(failure.missingKeys);
            }

            if (extras.length > 0) {
                console.warn('⚠ EXTRA KEYS DETECTED (warning only):');
                for (const warning of extras) {
                    console.warn(`  ${warning.locale}:`);
                    printWarningList(warning.extraKeys, '    - ');
                }
            }

            process.exit(1);
        }

        console.log(`✓ All ${LOCALES.length} locales pass parity check.`);
        console.log(`✓ Total keys checked: ${baselineKeys.length}`);

        if (extras.length > 0) {
            console.warn('⚠ EXTRA KEYS DETECTED (warning only):');
            for (const warning of extras) {
                console.warn(`  ${warning.locale}:`);
                printWarningList(warning.extraKeys, '    - ');
            }
        }

        process.exit(0);
    } catch (error) {
        console.error(`✗ I18N parity check failed to run: ${error.message}`);
        process.exit(1);
    }
}

main();
