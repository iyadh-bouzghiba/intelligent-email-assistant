# Intelligent Email Assistant (Full-Stack)

A professional, production-grade application that uses AI to summarize and analyze email content.

## 🏗️ Project Structure

This project is organized into two main parts:

- **[`backend/`](./backend)**: FastAPI server that handles email preprocessing, NLP classification, and LLM-powered summarization.
- **[`frontend/`](./frontend)**: Premium React application (Vite + TS + Tailwind) with a responsive, glassmorphism-inspired design.

## 🚀 Quick Start

### Backend
```bash
cd backend
# Run the server (using the existing venv):
..\.venv\Scripts\python -m uvicorn src.api.service:app --reload
```

### Frontend
```bash
cd frontend
# Install dependencies: npm install
# Start the dev server (supports Node.js 16+):
npm run dev
```

## 🧠 Core Features
- Paste raw email threads for instant AI analysis.
- Extracts Key Points, Action Items, and Overviews.
- Mobile-first, responsive design.
- Real-time backend status indicator.
- Secure Gmail integration (OAuth supported).
