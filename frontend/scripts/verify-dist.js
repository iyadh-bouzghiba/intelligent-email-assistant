#!/usr/bin/env node
/**
 * DRIFT-KILL BUILD VERIFICATION
 * Fails the build if forbidden strings appear in dist bundle.
 *
 * Forbidden patterns (stale backend URLs):
 * - "7za8"
 * - "2npf"
 * - "intelligent-email-assistant-7za8.onrender.com"
 * - "intelligent-email-assistant-2npf.onrender.com"
 */

import { readFileSync, readdirSync } from 'fs';
import { join } from 'path';

const FORBIDDEN = [
    '7za8',
    '2npf',
    'intelligent-email-assistant-7za8',
    'intelligent-email-assistant-2npf'
];

const DIST_DIR = 'dist';

function scanFile(filePath) {
    const content = readFileSync(filePath, 'utf-8');
    const violations = [];

    for (const pattern of FORBIDDEN) {
        if (content.includes(pattern)) {
            violations.push({ file: filePath, pattern });
        }
    }

    return violations;
}

function scanDirectory(dir) {
    let allViolations = [];

    const entries = readdirSync(dir, { withFileTypes: true });

    for (const entry of entries) {
        const fullPath = join(dir, entry.name);

        if (entry.isDirectory()) {
            allViolations = allViolations.concat(scanDirectory(fullPath));
        } else if (entry.isFile() && (entry.name.endsWith('.js') || entry.name.endsWith('.css') || entry.name.endsWith('.html'))) {
            allViolations = allViolations.concat(scanFile(fullPath));
        }
    }

    return allViolations;
}

console.log('🔍 [VERIFY] Scanning dist/ for forbidden URL patterns...');

const violations = scanDirectory(DIST_DIR);

if (violations.length > 0) {
    console.error('\n❌ [VERIFY] DRIFT DETECTED — Build blocked!\n');
    console.error('Forbidden patterns found in bundle:\n');

    for (const v of violations) {
        console.error(`  ${v.file}: contains "${v.pattern}"`);
    }

    console.error('\n💡 Fix: Remove hardcoded URLs from source. Use import.meta.env instead.\n');
    process.exit(1);
}

console.log('✅ [VERIFY] Clean — no forbidden patterns in dist/\n');
process.exit(0);
