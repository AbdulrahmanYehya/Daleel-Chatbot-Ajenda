https://docs.google.com/document/d/1WbwoOhzFtD879Kbb57600DjvEOUbSeX76u5ESuTYlZM/edit?usp=sharing

# AiGenda — AI Agenda & Task Assistant

An AI-powered task and workspace assistant. Users manage workspaces, tasks, and notes through natural conversation instead of manual forms — the agent interprets the request, calls the right tools, and mutates state on a live backend.

## Stack
- **Python / Flask** — service layer and API routes
- **Google Gemini API** — tool-calling conversational agent
- **Sentence-Transformers** — semantic embeddings for contextual memory
- **Server-Sent Events (SSE)** — real-time streaming of agent responses, tool calls, and tool results
- **.NET Master Gateway** — external backend the Python service integrates with for all workspace/task/note CRUD, analytics, and memory
- **ReportLab + arabic-reshaper + python-bidi** — Arabic-aware PDF export for AI-generated briefings

## How it works
1. A user message comes in through `/api/ai/chat` or `/api/ai/chat/stream`.
2. The Gemini-backed agent (`EnhancedAIHandler`) decides whether to call a tool (e.g. create a task, list a workspace) or respond directly.
3. Tool calls are executed against the .NET Master Gateway via `backend_client.py`, which normalizes two different response envelope shapes the gateway returns (`{success, data, error}` for mutations, `{items, pageNumber, ...}` for paginated lists).
4. Results stream back to the client as SSE events: `tool_call`, `tool_result`, `message` (token-by-token), `state` (updated tasks/notes/workspaces), and `done`.
5. If Gemini's follow-up narration call fails transiently (e.g. a 503) *after* a tool already succeeded, a fallback handler reconstructs a plain-language confirmation from the tool's result instead of surfacing a raw error for a request that actually worked.

## Notable engineering details
- No local database — all state lives behind the .NET gateway; the Python service is a stateless orchestration layer.
- Handles a documented gap where no flat "all tasks" or "all notes" endpoint exists, by walking every workspace/space via the documented per-workspace endpoints.
- Explicit `NOT_IMPLEMENTED` responses for capabilities the backend doesn't yet expose, instead of silently returning fake/empty data.

## Demo
A live front-end demo is available: **https://abdulrahmanyehya.github.io/AbdulrahmanYehya_portfolio/AiGenda_Demo.html**

## Status
Built as a full-stack AI product exercise — backend/agent layer complete and integrated with a live external gateway.
