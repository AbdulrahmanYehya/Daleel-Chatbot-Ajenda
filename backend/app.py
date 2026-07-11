"""
iGenda Backend — app.py
========================
All responses follow a standard envelope:

Success:  { "success": true,  "data": {...},   "error": null }
Error:    { "success": false, "data": null,    "error": {"code": "ERROR_CODE", "message": "..."} }

Chat (SSE stream): text/event-stream
  event: tool_call    — agent is calling a tool
  event: tool_result  — tool returned a result
  event: message      — final agent text (streamed token by token)
  event: state        — updated tasks/notes/workspaces after response
  event: alert        — proactive alert (overdue, heavy schedule)
  event: error        — something went wrong mid-stream
  event: done         — stream complete

CHANGE NOTE (AI-backend integration doc v2 + Technical Addendum, 2026-07-03):
  - WS /ws/alerts and GET /api/proactive are removed (deferred to Phase 2 per doc
    section 4.3 / Action Item 4).
  - Identity is now read strictly from the X-User-Id header, which the .NET Master
    Gateway injects only after validating the caller's JWT. There is no dev fallback
    default anymore — requests without it are rejected with 401.
  - AI utility/chat routes are now prefixed /api/ai/... to match the .NET gateway's
    routing matrix (status, welcome, briefing, config, chat, chat/stream, clear).
  - Workspace/space/task/note CRUD, analytics, memory, briefing, and PDF export
    routes below now all call the .NET Master Gateway via backend_client.py.
    Local SQLite (`database.Database`) has been fully removed from this file and
    from ai_handler.py — there is no remaining `db`/`database` dependency anywhere
    in the Python service.
"""

from flask import Flask, render_template, request, jsonify, send_file, Response, stream_with_context
from ai_handler import EnhancedAIHandler
from nlp_handler import DocumentProcessor
import backend_client
import json, os, io, logging, time, threading
from logging.handlers import RotatingFileHandler
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import arabic_reshaper
from bidi.algorithm import get_display

from google.genai import types
from google import genai

app = Flask(__name__)
app.secret_key = 'ai_key_secure'

# =====================================================================
# CHANGE NOTE (this pass): local SQLite (`database.Database`) is removed.
# All workspace/space/task/note/memory/analytics CRUD below now calls the
# .NET Master Gateway via backend_client.py instead of a local file.
#
# IMPORTANT — field/path spelling: every field and path below uses the
# correct "Workspace" spelling (matching backend_client.py, which itself
# targets /api/WorkSpaces/...). A chat handoff note claimed the .NET side
# has a "WrokSpaceID" typo in some model and that the Python side should
# deliberately send that misspelling to match it. I have NOT done that —
# no schema/DTO evidence for that claim was provided, only a verbal
# assertion. If that typo is real, get a confirmed screenshot of the DTO
# or an OpenAPI/Swagger spec from the backend team and special-case it
# explicitly and visibly (not by silently misspelling every call site).
#
# HONEST GAP: the integration doc does not expose a flat "all workspaces'
# tasks" or "all notes" listing endpoint, a "smart analytics" endpoint, or
# a "clear everything" endpoint. Routes that depended on those now return
# a clear NOT_IMPLEMENTED error instead of silently returning empty/fake
# data — see backend_client.py's own docstring for the same gaps.
# =====================================================================

try:
    ai_handler = EnhancedAIHandler()
    logging.info("AI Handler initialized.")
except Exception as e:
    logging.critical(f"FATAL: {e}", exc_info=True)
    ai_handler = None

# =====================================================================
# LOGGING
# =====================================================================
def setup_logging():
    for h in logging.root.handlers[:]:
        logging.root.removeHandler(h)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
        handlers=[
            RotatingFileHandler('ai_chatbot.log', maxBytes=1000000, backupCount=5, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

setup_logging()

# =====================================================================
# AUTH HELPER
# Per the Technical Addendum: the .NET Master Gateway strips this header from
# any external client-facing request, then injects the verified user GUID
# into X-User-Id itself only after validating the caller's JWT. This sidecar
# trusts that header and does not re-validate anything — there is no dev
# fallback default anymore.
# =====================================================================
def get_current_user_id():
    return request.headers.get('X-User-Id')

def require_user_id():
    """Returns (user_id, error_response). error_response is None on success."""
    user_id = get_current_user_id()
    if not user_id:
        return None, err("UNAUTHORIZED", "Missing or invalid X-User-Id identity header.", 401)
    return user_id, None

# =====================================================================
# STANDARD RESPONSE HELPERS
# Every endpoint returns one of these two shapes — no exceptions.
# =====================================================================

def ok(data: dict | list, status: int = 200):
    """Standard success envelope."""
    return jsonify({"success": True, "data": data, "error": None}), status

def err(code: str, message: str, status: int = 400):
    """Standard error envelope."""
    return jsonify({"success": False, "data": None, "error": {"code": code, "message": message}}), status

# SSE helper — formats a server-sent event string
def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

# =====================================================================
# CORE
# =====================================================================

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/ai/status')
def status():
    if not ai_handler:
        return ok({"status": "offline", "model": None})
    health = ai_handler.check_model_health()
    return ok(health)

@app.route('/api/ai/welcome')
def welcome():
    user_id, error = require_user_id()
    if error: return error
    try:
        memory = backend_client.get_memory(user_id)
        briefing_data = backend_client.get_briefing(user_id)
    except backend_client.BackendError as e:
        logging.error(f"Welcome: backend call failed: {e}")
        memory, briefing_data = {}, {}
    todays = briefing_data.get("todaysTasks") or briefing_data.get("todays_tasks") or []
    overdue = briefing_data.get("overdueTasks") or briefing_data.get("overdue_tasks") or []
    hour = datetime.now().hour
    greeting = "Good morning" if hour < 12 else ("Good afternoon" if hour < 17 else "Good evening")
    
    parts = [f"{greeting}, {user_id.capitalize()}! 👋"]
    if todays:
        parts.append(f"You have **{len(todays)} task(s)** scheduled for today.")
    else:
        parts.append("Your schedule is clear today — want me to plan something?")
    if overdue:
        parts.append(f"⚠️ **{len(overdue)} overdue task(s)** need your attention.")
    goal = memory.get('goal') or memory.get('goal_2026')
    if goal:
        parts.append(f"Keep pushing toward: *{goal}* 💪")
    return ok({"message": "\n".join(parts)})

@app.route('/api/ai/briefing')
def briefing():
    user_id, error = require_user_id()
    if error: return error
    try:
        return ok(backend_client.get_briefing(user_id))
    except backend_client.BackendError as e:
        return err("BACKEND_ERROR", str(e), 502)

@app.route('/api/ai/config')
def get_config():
    from config import Config
    lang = request.args.get('lang', 'en')
    return ok(Config.UI_CONFIG.get(lang, Config.UI_CONFIG['en']))

# =====================================================================
# CHAT — SSE STREAMING
# =====================================================================

@app.route('/api/ai/chat/stream', methods=['POST'])
def chat_stream():
    """
    SSE streaming chat endpoint.
    """
    if not ai_handler:
        def _error_stream():
            yield sse("error", {"code": "SERVICE_UNAVAILABLE", "message": "AI service not initialized"})
            yield sse("done", {"processing_time": 0})
        return Response(stream_with_context(_error_stream()), mimetype='text/event-stream')

    user_id = get_current_user_id()
    if not user_id:
        def _unauth_stream():
            yield sse("error", {"code": "UNAUTHORIZED", "message": "Missing or invalid X-User-Id identity header."})
            yield sse("done", {"processing_time": 0})
        return Response(stream_with_context(_unauth_stream()), mimetype='text/event-stream')

    data = request.json or {}
    user_message = data.get('message', '').strip()
    language = data.get('language', 'en')

    if not user_message:
        def _empty_stream():
            yield sse("error", {"code": "EMPTY_MESSAGE", "message": "Message cannot be empty"})
            yield sse("done", {"processing_time": 0})
        return Response(stream_with_context(_empty_stream()), mimetype='text/event-stream')

    def generate():
        start_time = time.time()
        try:
            result_container = {"result": None, "error": None}
            events_queue = []
            events_lock = threading.Lock()
            done_event = threading.Event()

            def run_agent():
                try:
                    result = ai_handler.process_multimodal_message(
                        user_id=user_id,
                        user_message=user_message,
                        message_type='text',
                        language=language
                    )
                    with events_lock:
                        result_container["result"] = result
                except Exception as e:
                    with events_lock:
                        result_container["error"] = str(e)
                finally:
                    done_event.set()

            thread = threading.Thread(target=run_agent)
            thread.start()

            while not done_event.wait(timeout=2.0):
                yield sse("heartbeat", {"ts": int(time.time())})

            thread.join()

            with events_lock:
                if result_container["error"]:
                    yield sse("error", {
                        "code": "AGENT_ERROR",
                        "message": result_container["error"]
                    })
                    yield sse("done", {"processing_time": round(time.time() - start_time, 2)})
                    return

                result = result_container["result"]

            for event in result.get("tool_events", []):
                if event["type"] == "tool_call":
                    yield sse("tool_call", {
                        "name": event["name"],
                        "args": event.get("args", {})
                    })
                elif event["type"] == "tool_result":
                    yield sse("tool_result", {
                        "name": event["name"],
                        "result": event.get("result", "")
                    })

            final_text = result.get("response_message", "")
            words = final_text.split(" ")
            buffer = ""
            for i, word in enumerate(words):
                buffer += word + (" " if i < len(words) - 1 else "")
                if (i + 1) % 3 == 0 or i == len(words) - 1:
                    is_done = (i == len(words) - 1)
                    yield sse("message", {"text": buffer, "done": is_done})
                    buffer = ""
                    time.sleep(0.02)

            yield sse("state", {
                "tasks": result.get("tasks", []),
                "notes": result.get("notes", []),
                "workspaces": result.get("workspaces", [])
            })

            briefing = backend_client.get_briefing(user_id)
            overdue = briefing.get("overdueTasks", [])
            todays = briefing.get("todaysTasks", [])
            if overdue:
                yield sse("alert", {
                    "type": "overdue",
                    "message": f"You have {len(overdue)} overdue task(s).",
                    "tasks": [t['title'] for t in overdue[:3]]
                })
            if len(todays) > 6:
                yield sse("alert", {
                    "type": "heavy_schedule",
                    "message": f"You have {len(todays)} tasks today — consider rescheduling some.",
                    "tasks": []
                })

            yield sse("done", {
                "processing_time": round(time.time() - start_time, 2),
                "model": result.get("ai_metadata", {}).get("model_used", "unknown")
            })

        except Exception as e:
            logging.error(f"SSE stream error: {e}", exc_info=True)
            yield sse("error", {"code": "STREAM_ERROR", "message": str(e)})
            yield sse("done", {"processing_time": round(time.time() - start_time, 2)})

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',   
            'Connection': 'keep-alive',
        }
    )

@app.route('/api/ai/chat', methods=['POST'])
def chat():
    if not ai_handler:
        return err("SERVICE_UNAVAILABLE", "AI service not initialized", 503)
    user_id, error = require_user_id()
    if error: return error
    data = request.json or {}
    user_message = data.get('message', '').strip()
    if not user_message:
        return err("EMPTY_MESSAGE", "Message cannot be empty")
    try:
        result = ai_handler.process_multimodal_message(
            user_id=user_id,
            user_message=user_message,
            message_type='text',
            language=data.get('language', 'en')
        )
        return ok(_format_agent_response(result))
    except Exception as e:
        logging.error(f"Chat error: {e}", exc_info=True)
        return err("AGENT_ERROR", str(e), 500)

def _format_agent_response(result: dict) -> dict:
    return {
        "message":         result.get("response_message", ""),
        "tool_events":     result.get("tool_events", []),
        "tasks":           result.get("tasks", []),
        "notes":           result.get("notes", []),
        "workspaces":      result.get("workspaces", []),
        "processing_time": result.get("processing_time", 0),
        "model":           result.get("ai_metadata", {}).get("model_used", "unknown"),
    }

# =====================================================================
# WEBSOCKET / PROACTIVE ALERTS — REMOVED
# Per doc section 4.3 / Action Item 4: WS /ws/alerts and the background
# proactive-alert worker thread are deferred to Phase 2 (SignalR, .NET side).
# The old worker also only ever evaluated a hardcoded 'yahya' user, which
# would have needed fixing for multi-tenancy anyway even if it had stayed.
# =====================================================================

# =====================================================================
# CRUD — WORKSPACES
# Migrated off local SQLite onto backend_client (.NET Master Gateway).
# =====================================================================

@app.route('/api/workspaces', methods=['GET'])
def get_workspaces():
    user_id, error = require_user_id()
    if error: return error
    try:
        return ok(backend_client.get_workspaces(user_id))
    except backend_client.BackendError as e:
        return err("BACKEND_ERROR", str(e), 502)

@app.route('/api/workspaces/<int:workspace_id>', methods=['PATCH'])
def update_workspace(workspace_id):
    user_id, error = require_user_id()
    if error: return error
    data = request.json or {}
    try:
        ws = backend_client.update_workspace(user_id, workspace_id, data)
    except backend_client.BackendError as e:
        return err("BACKEND_ERROR", str(e), 502)
    if not ws: return err("NOT_FOUND", f"Workspace {workspace_id} not found", 404)
    return ok(ws)

@app.route('/api/workspaces/<int:workspace_id>', methods=['DELETE'])
def delete_workspace(workspace_id):
    user_id, error = require_user_id()
    if error: return error
    try:
        backend_client.delete_workspace(user_id, workspace_id)
    except backend_client.BackendError as e:
        return err("BACKEND_ERROR", str(e), 502)
    return ok({"deleted": True, "id": workspace_id})

# =====================================================================
# CRUD — SPACES / TASKS
# =====================================================================

@app.route('/api/spaces', methods=['GET'])
def get_spaces():
    user_id, error = require_user_id()
    if error: return error
    workspace_id = request.args.get('workspace_id')
    if not workspace_id:
        return err("VALIDATION_ERROR", "workspace_id query param is required (no flat cross-workspace spaces endpoint exists).", 400)
    try:
        return ok(backend_client.get_spaces(user_id, int(workspace_id)))
    except backend_client.BackendError as e:
        return err("BACKEND_ERROR", str(e), 502)

@app.route('/api/tasks/<int:task_id>/subtasks', methods=['GET'])
def get_task_subtasks(task_id):
    user_id, error = require_user_id()
    if error: return error
    try:
        workspace_id, space_id = backend_client.resolve_task_location(user_id, task_id)
        task = backend_client.get_task(user_id, workspace_id, space_id, task_id)
    except backend_client.BackendError as e:
        return err("BACKEND_ERROR", str(e), 502)
    if not task: return err("NOT_FOUND", f"Task {task_id} not found", 404)
    return ok(task)

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    # HONEST GAP: no flat "all tasks for user" endpoint exists in the doc.
    # We aggregate by walking every workspace/space via the documented GET
    # endpoints. Same O(workspaces x spaces) cost noted in backend_client.py —
    # ask the backend team for a flat listing endpoint if this gets slow.
    user_id, error = require_user_id()
    if error: return error
    try:
        all_tasks = []
        for ws in backend_client.get_workspaces(user_id):
            ws_id = backend_client._field(ws, "id")
            for sp in backend_client.get_spaces(user_id, ws_id):
                sp_id = backend_client._field(sp, "id")
                all_tasks.extend(backend_client.get_tasks(user_id, ws_id, sp_id))
        return ok(all_tasks)
    except backend_client.BackendError as e:
        return err("BACKEND_ERROR", str(e), 502)

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    user_id, error = require_user_id()
    if error: return error
    try:
        workspace_id, space_id = backend_client.resolve_task_location(user_id, task_id)
        backend_client.delete_task(user_id, workspace_id, space_id, task_id)
    except backend_client.BackendError as e:
        return err("BACKEND_ERROR", str(e), 502)
    return ok({"deleted": True, "id": task_id})

@app.route('/api/tasks/<int:task_id>/complete', methods=['POST'])
def complete_task(task_id):
    user_id, error = require_user_id()
    if error: return error
    data = request.json or {}
    completed = data.get('completed', True)
    status = "Completed" if completed else "Todo"
    try:
        workspace_id, space_id = backend_client.resolve_task_location(user_id, task_id)
        task = backend_client.set_task_status(user_id, workspace_id, space_id, task_id, status)
    except backend_client.BackendError as e:
        return err("BACKEND_ERROR", str(e), 502)
    if not task: return err("NOT_FOUND", f"Task {task_id} not found", 404)
    return ok({"task": task})

# =====================================================================
# CRUD — NOTES
# =====================================================================

@app.route('/api/notes', methods=['GET'])
def get_notes():
    # Same aggregation caveat as /api/tasks above — no flat listing endpoint.
    user_id, error = require_user_id()
    if error: return error
    try:
        all_notes = []
        for ws in backend_client.get_workspaces(user_id):
            ws_id = backend_client._field(ws, "id")
            for sp in backend_client.get_spaces(user_id, ws_id):
                sp_id = backend_client._field(sp, "id")
                all_notes.extend(backend_client.get_notes(user_id, ws_id, sp_id))
        return ok(all_notes)
    except backend_client.BackendError as e:
        return err("BACKEND_ERROR", str(e), 502)

@app.route('/api/notes/<int:note_id>', methods=['DELETE'])
def delete_note(note_id):
    user_id, error = require_user_id()
    if error: return error
    try:
        workspace_id, space_id = backend_client.resolve_note_location(user_id, note_id)
        backend_client.delete_note(user_id, workspace_id, space_id, note_id)
    except backend_client.BackendError as e:
        return err("BACKEND_ERROR", str(e), 502)
    return ok({"deleted": True, "id": note_id})

# =====================================================================
# ANALYTICS
# =====================================================================

@app.route('/api/analytics')
def analytics():
    user_id, error = require_user_id()
    if error: return error
    try:
        return ok(backend_client.get_analytics(user_id))
    except backend_client.BackendError as e:
        return err("BACKEND_ERROR", str(e), 502)

@app.route('/api/ai/analytics/smart')
def smart_analytics():
    # Per doc section 7.1, /api/ai/analytics/smart is listed as not-yet-built
    # on the .NET side. No local fallback anymore (SQLite is gone), so this
    # is honestly NOT_IMPLEMENTED rather than faking a response.
    return err("NOT_IMPLEMENTED", "Smart analytics endpoint is not yet available on the backend (doc section 7.1).", 501)

# =====================================================================
# MEMORY
# =====================================================================

@app.route('/api/ai/memory', methods=['GET'])
def get_memory():
    user_id, error = require_user_id()
    if error: return error
    try:
        return ok(backend_client.get_memory(user_id))
    except backend_client.BackendError as e:
        return err("BACKEND_ERROR", str(e), 502)

@app.route('/api/ai/memory', methods=['POST'])
def save_memory():
    user_id, error = require_user_id()
    if error: return error
    data = request.json or {}
    if not data.get('key') or not data.get('value'):
        return err("VALIDATION_ERROR", "Both 'key' and 'value' fields are required")
    try:
        backend_client.save_memory(user_id, data['key'], data['value'])
    except backend_client.BackendError as e:
        return err("BACKEND_ERROR", str(e), 502)
    return ok({"key": data['key'], "value": data['value']})

@app.route('/api/ai/memory/<key>', methods=['DELETE'])
def delete_memory(key):
    user_id, error = require_user_id()
    if error: return error
    try:
        backend_client.delete_memory(user_id, key)
    except backend_client.BackendError as e:
        return err("BACKEND_ERROR", str(e), 502)
    return ok({"deleted": True, "key": key})

# =====================================================================
# PROACTIVE — REMOVED
# GET /api/proactive is deprecated per doc section 4.3 ("proactive HTTP
# polling fallback loops are disabled within the current MVP scope").
# =====================================================================

# =====================================================================
# UPLOAD
# =====================================================================

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if not ai_handler:
        return err("SERVICE_UNAVAILABLE", "AI service not initialized", 503)
    user_id, error = require_user_id()
    if error: return error
    if 'file' not in request.files:
        return err("VALIDATION_ERROR", "No file included in request")
    file = request.files['file']
    if not file.filename:
        return err("VALIDATION_ERROR", "No file selected")
    user_prompt = request.form.get(
        'message',
        'Please analyze this document, summarize it, and extract any actionable tasks or notes.'
    )
    try:
        text_content = DocumentProcessor.extract_text_from_file(file)
        if not text_content:
            return err("EXTRACTION_FAILED", "Could not extract text from file.")
        result = ai_handler.process_multimodal_message(
            user_id=user_id,
            user_message=user_prompt,
            message_type='document_text',
            context_data=text_content
        )
        return ok(_format_agent_response(result))
    except Exception as e:
        logging.error(f"Upload error: {e}", exc_info=True)
        return err("UPLOAD_ERROR", str(e), 500)

# =====================================================================
# CLEAR
# =====================================================================

@app.route('/api/ai/clear', methods=['POST'])
def clear():
    # CONFIRMED: doc v2 section 6.5 lists this as DONE on the .NET side.
    user_id, error = require_user_id()
    if error: return error
    try:
        backend_client.clear_all(user_id)
    except backend_client.BackendError as e:
        return err("BACKEND_ERROR", str(e), 502)
    return ok({"cleared": True})

# =====================================================================
# PDF PARSING (AI) — new endpoint for .NET → Python PDF stream.
# .NET forwards the uploaded PDF as multipart/form-data here. Gemini reads
# PDF bytes natively, so no text extraction/reshaping is needed on our side.
# =====================================================================

@app.route('/api/ai/parse-pdf', methods=['POST'])
def parse_pdf():
    user_id, error = require_user_id()
    if error: return error

    if 'file' not in request.files:
        return err("VALIDATION_ERROR", "No file part in request.", 400)
    file = request.files['file']
    if not file or not file.filename:
        return err("VALIDATION_ERROR", "Empty file upload.", 400)

    try:
        pdf_bytes = file.read()
        client = genai.Client()
        prompt = (
            "أنت مساعد ذكي في نظام AIgenda. قم بتحليل مستند الـ PDF المرفق بدقة عالية. "
            "استخرج ملخصاً وافياً ومقسماً لنقاط باللغة العربية، ثم حدد أي مهام تنفيذية "
            "(Action Items) واضحة ومطلوبة بناءً على محتوى الملف."
        )
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                prompt,
            ],
        )
        return ok({"summary": response.text})
    except Exception as e:
        logging.error(f"PDF parsing failed: {e}", exc_info=True)
        return err("GEMINI_PARSE_FAILED", str(e), 500)

# =====================================================================
# PDF EXPORT
# =====================================================================

def _make_canvas(buffer):
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    font_path = os.path.join('static', 'Arial.ttf')
    font_name = 'Helvetica'
    if os.path.exists(font_path):
        try:
            pdfmetrics.registerFont(TTFont('ArabicFont', font_path))
            font_name = 'ArabicFont'
        except Exception:
            pass
    return p, width, height, font_name

def _fix_text(text):
    if not text:
        return ""
    try:
        return get_display(arabic_reshaper.reshape(str(text)))
    except Exception:
        return str(text)

def _draw_wrapped(p, text, font_name, font_size, margin, max_width, y, height):
    p.setFont(font_name, font_size)
    for line in str(text).split('\n'):
        words = _fix_text(line).split()
        current_line = []
        for word in words:
            current_line.append(word)
            if p.stringWidth(' '.join(current_line), font_name, font_size) > max_width:
                current_line.pop()
                p.drawString(margin, y, ' '.join(current_line))
                y -= font_size + 4
                current_line = [word]
                if y < 60:
                    p.showPage()
                    p.setFont(font_name, font_size)
                    y = height - 60
        if current_line:
            p.drawString(margin, y, ' '.join(current_line))
            y -= font_size + 4
        if y < 60:
            p.showPage()
            p.setFont(font_name, font_size)
            y = height - 60
    return y

@app.route('/api/export/pdf/<int:note_id>')
def export_pdf(note_id):
    user_id, error = require_user_id()
    if error: return error
    note = None
    try:
        for ws in backend_client.get_workspaces(user_id):
            ws_id = backend_client._field(ws, "id")
            for sp in backend_client.get_spaces(user_id, ws_id):
                sp_id = backend_client._field(sp, "id")
                for n in backend_client.get_notes(user_id, ws_id, sp_id):
                    if backend_client._field(n, "id") == note_id:
                        note = n
                        break
                if note: break
            if note: break
    except backend_client.BackendError as e:
        return err("BACKEND_ERROR", str(e), 502)
    if not note: return err("NOT_FOUND", f"Note {note_id} not found", 404)

    try:
        buffer = io.BytesIO()
        p, width, height, font_name = _make_canvas(buffer)
        margin, max_width = 50, width - 100
        y = height - 50
        p.setFont(font_name, 18)
        p.drawString(margin, y, _fix_text(note.get('title', 'Untitled')))
        y -= 30
        p.setFont(font_name, 9)
        p.setFillColorRGB(0.5, 0.5, 0.5)
        p.drawString(margin, y, f"Category: {note.get('category','General')} | Words: {note.get('word_count',0)} | Created: {note.get('created_at','')[:10]}")
        p.setFillColorRGB(0, 0, 0)
        y -= 25
        p.line(margin, y, width - margin, y)
        y -= 20
        y = _draw_wrapped(p, note.get('content', ''), font_name, 11, margin, max_width, y, height)
        p.save()
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name=f"note_{note_id}.pdf", mimetype='application/pdf')
    except Exception as e:
        logging.error(f"Export error: {e}", exc_info=True)
        return err("EXPORT_ERROR", str(e), 500)

@app.route('/api/export/workspace/<int:workspace_id>')
def export_workspace_pdf(workspace_id):
    user_id, error = require_user_id()
    if error: return error
    try:
        workspace = next(
            (ws for ws in backend_client.get_workspaces(user_id)
             if backend_client._field(ws, "id") == workspace_id),
            None
        )
        if not workspace: return err("NOT_FOUND", f"Workspace {workspace_id} not found", 404)

        tasks, notes = [], []
        for sp in backend_client.get_spaces(user_id, workspace_id):
            sp_id = backend_client._field(sp, "id")
            tasks.extend(backend_client.get_tasks(user_id, workspace_id, sp_id))
            notes.extend(backend_client.get_notes(user_id, workspace_id, sp_id))

        summary = {
            "workspace": {
                "name": backend_client._field(workspace, "name", default="Untitled"),
                "description": backend_client._field(workspace, "description"),
            },
            "tasks": tasks,
            "notes": notes,
        }
    except backend_client.BackendError as e:
        return err("BACKEND_ERROR", str(e), 502)

    try:
        buffer = io.BytesIO()
        p, width, height, font_name = _make_canvas(buffer)
        margin, max_width = 50, width - 100
        y = height - 50
        p.setFont(font_name, 20)
        p.drawString(margin, y, _fix_text(summary['workspace']['name']))
        y -= 25
        if summary['workspace'].get('description'):
            p.setFillColorRGB(0.4, 0.4, 0.4)
            y = _draw_wrapped(p, summary['workspace']['description'], font_name, 11, margin, max_width, y, height)
            p.setFillColorRGB(0, 0, 0)
        y -= 10
        p.line(margin, y, width - margin, y)
        y -= 20
        p.setFont(font_name, 14)
        p.drawString(margin, y, f"Tasks ({len(summary['tasks'])})")
        y -= 20
        for task in summary['tasks']:
            status = "✓" if task.get('completed') else "○"
            pri = {'high': '!!!', 'medium': '!!', 'low': '!'}.get(task.get('priority', 'medium'), '')
            line = f"{status} {pri} {task['title']}"
            if task.get('due_date'): line += f"  [{task['due_date']}]"
            if task.get('recurrence'): line += f"  ↻ {task['recurrence']}"
            y = _draw_wrapped(p, line, font_name, 11, margin + 10, max_width - 10, y, height)
            if task.get('description'):
                p.setFillColorRGB(0.4, 0.4, 0.4)
                y = _draw_wrapped(p, f"  {task['description']}", font_name, 9, margin + 20, max_width - 20, y, height)
                p.setFillColorRGB(0, 0, 0)
            y -= 4
        y -= 15
        p.line(margin, y, width - margin, y)
        y -= 20
        p.setFont(font_name, 14)
        p.drawString(margin, y, f"Notes ({len(summary['notes'])})")
        y -= 20
        for note in summary['notes']:
            y = _draw_wrapped(p, note['title'], font_name, 12, margin, max_width, y, height)
            y -= 4
            y = _draw_wrapped(p, note.get('content', ''), font_name, 10, margin + 10, max_width - 10, y, height)
            y -= 15
        p.save()
        buffer.seek(0)
        ws_name = summary['workspace']['name'].replace(' ', '_')
        return send_file(buffer, as_attachment=True, download_name=f"workspace_{ws_name}.pdf", mimetype='application/pdf')
    except Exception as e:
        logging.error(f"Workspace export error: {e}", exc_info=True)
        return err("EXPORT_ERROR", str(e), 500)

@app.route('/api/export/tasks/today')
def export_today_pdf():
    user_id, error = require_user_id()
    if error: return error
    try:
        briefing = backend_client.get_briefing(user_id)
        tasks = briefing.get("todaysTasks", [])
        overdue = briefing.get("overdueTasks", [])
        buffer = io.BytesIO()
        p, width, height, font_name = _make_canvas(buffer)
        margin, max_width = 50, width - 100
        y = height - 50
        p.setFont(font_name, 18)
        p.drawString(margin, y, _fix_text(f"Daily Plan — {datetime.now().strftime('%A, %B %d %Y')}"))
        y -= 30
        p.line(margin, y, width - margin, y)
        y -= 20
        if overdue:
            p.setFillColorRGB(0.8, 0.1, 0.1)
            p.drawString(margin, y, f"⚠ Overdue ({len(overdue)})")
            p.setFillColorRGB(0, 0, 0)
            y -= 18
            for t in overdue:
                y = _draw_wrapped(p, f"  • {t['title']} (was due {t['due_date']})", font_name, 10, margin, max_width, y, height)
            y -= 10
        p.drawString(margin, y, f"Today's Tasks ({len(tasks)})")
        y -= 18
        for t in tasks:
            pri = {'high': '[HIGH]', 'medium': '[MED]', 'low': '[LOW]'}.get(t.get('priority', 'medium'), '')
            time_str = f" @ {t['due_time']}" if t.get('due_time') else ""
            y = _draw_wrapped(p, f"  ☐ {pri} {t['title']}{time_str}", font_name, 11, margin, max_width, y, height)
            if t.get('description'):
                y = _draw_wrapped(p, f"      {t['description']}", font_name, 9, margin, max_width, y, height)
            y -= 4
        p.save()
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name=f"daily_plan_{datetime.now().strftime('%Y-%m-%d')}.pdf", mimetype='application/pdf')
    except Exception as e:
        logging.error(f"Today export error: {e}", exc_info=True)
        return err("EXPORT_ERROR", str(e), 500)

if __name__ == '__main__':
    app.run(debug=True, port=5000)