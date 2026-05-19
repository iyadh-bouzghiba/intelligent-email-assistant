import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import './index.css';
import App from './App';
import { initializeI18n } from './i18n';

// WebSocket connection deferred to App.tsx (connects when account selected)

const rootElement = document.getElementById('root');

if (!rootElement) {
    throw new Error('Root element #root not found');
}

const root = createRoot(rootElement);

const bootstrap = async () => {
    await initializeI18n();

    root.render(
        <StrictMode>
            <App />
        </StrictMode>,
    );
};

void bootstrap();