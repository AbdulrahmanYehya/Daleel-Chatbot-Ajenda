# Ajenda Assistant (مساعد أجندة) - Complete Local Package

This package contains a ready-to-run local bilingual chatbot (English + Arabic) named **Ajenda Assistant (Daleel)**.
It uses Ollama (local LLM runtime) for inference and FastAPI for the backend. The assistant can create tasks and notes,
generate research PDFs, summarize, translate, and accept audio/image uploads. Everything is organized for Abdulrahman & Ahmed.

## Quick overview
- Backend: `backend/` (FastAPI)
- Frontend: `frontend/` (static HTML/JS)
- Data: `backend/data/` (tasks.json, notes/)
- Setup script: `setup.ps1` (Windows)
- .env.example included for secrets
- CI/tests not included in this final package but can be added

Read `Run_Guide.pdf` for step-by-step instructions.
