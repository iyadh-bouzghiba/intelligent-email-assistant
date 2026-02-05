import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'
import { websocketService } from "./services/websocket";

if (!(window as any).__WS_INIT__) {
  (window as any).__WS_INIT__ = true;
  try {
    websocketService.connect();
  } catch (e) {
    console.error("[WebSocket] Startup connect failed:", e);
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
