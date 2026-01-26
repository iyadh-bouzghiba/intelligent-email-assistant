# 🤖 Intelligent Email Assistant: Full-Stack AI Monorepo

[![Deployment: Render](https://img.shields.io/badge/Deployment-Render-46E3B7?style=flat-square&logo=render)](https://render.com)
[![Tech: FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Tech: React](https://img.shields.io/badge/Frontend-React-61DAFB?style=flat-square&logo=react)](https://reactjs.org/)

An enterprise-grade, multi-account email intelligence system. This project automates Gmail handshakes, performs deep thread analysis using custom NLP logic, and generates context-aware drafts.

## 🏗️ Monorepo Architecture
This project implements a clean separation of concerns within a single repository to maintain strict version synchronization between the "Brain" and the "UI".

* **/backend**: Python/FastAPI core utilizing a Modular Adapter pattern for future-proofing (Gmail/Outlook ready).
* **/frontend**: TypeScript/React (Vite) dashboard with real-time status tracking.
* **/shared**: Unified JSON schemas for data consistency across the stack.

## 🧠 Core Intelligence Features
- **Neural Handshake:** A robust, multi-account OAuth2 flow that securely manages user tokens without cross-contamination.
- **Thread Synthesizer:** Aggregates complex email chains into actionable summaries.
- **Dynamic Routing:** Environment-aware logic that switches between local development and cloud production automatically.

## 🛠️ Security & DevOps
- **Secret Shielding:** Integrated GitHub Push Protection with zero-leak environment variable architecture.
- **Production Standard:** Powered by Gunicorn/Uvicorn for high-concurrency request handling.
- **CI/CD Ready:** Optimized Docker and Shell scripting for automated deployments.

## 🚦 Getting Started
1. **Clone & Config:** Setup `.env` files in both folders (use `.env.example` as a template).
2. **Launch:** Run `scripts/start-all.sh` for a synchronized full-stack startup.
3. **Analyze:** Access the dashboard to link accounts and start the AI engine.

---
*Designed for performance. Engineered for security.*