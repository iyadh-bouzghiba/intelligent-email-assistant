/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

const toPosixPath = (value: string) => value.split(path.sep).join('/');

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,         // Fixed Port to match Backend Redirects
    strictPort: true,   // Error out if busy rather than switching to 5174
    host: '127.0.0.1',  // Standardize on localhost for API consistency
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@components': path.resolve(__dirname, './src/components'),
      '@services': path.resolve(__dirname, './src/services'),
      '@hooks': path.resolve(__dirname, './src/hooks'),
      '@types': path.resolve(__dirname, './src/types'),
      '@utils': path.resolve(__dirname, './src/utils'),
      '@shared': path.resolve(__dirname, '../shared'),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          const normalizedId = toPosixPath(id);

          // Preserve per-locale dynamic chunks from src/i18n/locales/*.json
          if (normalizedId.includes('/src/i18n/locales/')) {
            return undefined;
          }

          if (!normalizedId.includes('/node_modules/')) {
            return undefined;
          }

          if (
            normalizedId.includes('/node_modules/react/') ||
            normalizedId.includes('/node_modules/react-dom/') ||
            normalizedId.includes('/node_modules/scheduler/')
          ) {
            return 'vendor-react';
          }

          if (normalizedId.includes('/node_modules/framer-motion/')) {
            return 'vendor-motion';
          }

          if (
            normalizedId.includes('/node_modules/i18next/') ||
            normalizedId.includes('/node_modules/react-i18next/')
          ) {
            return 'vendor-i18n';
          }

          return 'vendor';
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
  },
});