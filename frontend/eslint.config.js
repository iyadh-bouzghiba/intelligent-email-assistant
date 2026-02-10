import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

/**
 * ESLint 8.57.1-safe flat config:
 * - Do NOT import from "eslint/config" (it is not exported in ESLint 8.57.1) [1](https://github.com/eslint/create-config/issues/160)
 * - Compose configs as array items (flat config style)
 * - Defensive handling when a "configs.*" value might be an object or an array
 */

const asArray = (maybeArrayOrObject) =>
  maybeArrayOrObject ? (Array.isArray(maybeArrayOrObject) ? maybeArrayOrObject : [maybeArrayOrObject]) : [];

// typescript-eslint "recommended" is often provided as a flat-config set (array) in modern versions. [3](https://typescript-eslint.io/getting-started/)
const tsRecommended = asArray(tseslint?.configs?.recommended);

// react-hooks provides flat recommended config in newer versions; docs show configs.flat.recommended. [2](https://www.npmjs.com/package/eslint-plugin-react-hooks)
const reactHooksFlatRecommended = asArray(reactHooks?.configs?.flat?.recommended);

// If flat preset is missing, fall back to classic recommended rules (stable and simple)
const reactHooksRulesFallback = reactHooks?.configs?.recommended?.rules ?? {};

export default [
  // Global ignores
  { ignores: ["dist", "node_modules"] },

  // Base JS recommended rules
  js.configs.recommended,

  // TypeScript recommended configs (array/object tolerant)
  ...tsRecommended,

  // React hooks recommended configs if available
  ...reactHooksFlatRecommended,

  // Node.js scripts configuration (verify-env.js, verify-dist.js)
  {
    files: ["scripts/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: globals.node,
    },
    rules: {
      // Allow console in build scripts
      "no-console": "off",
    },
  },

  // Project-specific rules for TS/TSX
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2020,
      sourceType: "module",
      globals: globals.browser,
      parser: tseslint.parser,
    },
    plugins: {
      "@typescript-eslint": tseslint.plugin,
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      // Ensure hooks rules exist even if flat preset is missing
      ...reactHooksRulesFallback,

      // Vite/React refresh rule (avoid relying on reactRefresh.configs.vite shape)
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],

      // Baseline tolerance: typescript-eslint v8 is stricter than v7
      // Downgrade policy rules to match existing codebase patterns (no code changes required)
      "@typescript-eslint/no-explicit-any": "warn", // Allow strategic any usage (API types, catch blocks)
      "@typescript-eslint/no-unused-vars": ["warn", {
        argsIgnorePattern: "^_", // Ignore unused params starting with _
        varsIgnorePattern: "^_",
        caughtErrors: "none" // Ignore unused error vars in catch blocks
      }],
      "@typescript-eslint/no-unsafe-function-type": "warn", // External library callback types (Socket.IO)
    },
  },
];