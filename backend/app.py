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

WebSocket /ws/alerts  — pushes proactive alerts in real time
"""

from flask import Flask, render_template, request, jsonify, send_file, Response, stream_with_context
from flask_sock import Sock
from database import Database
from ai_handler import EnhancedAIHandler
from nlp_handler import DocumentProcessor
import json, os, io, logging, time, threading
from logging.handlers import RotatingFileHandler
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import arabic_reshaper
from bidi.algorithm import get_display

app = Flask(__name__)
app.secret_key = 'ai_key_secure'
sock = Sock(app)  # WebSocket support via flask-sock

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

try:
    db = Database()
    ai_handler = EnhancedAIHandler()
    logging.info("Database and AI Handler initialized.")
except Exception as e:
    logging.critical(f"FATAL: {e}", exc_info=True)
    db = None
    ai_handler = None

# =====================================================================
# AUTH HELPER
# For handoff: The backend team will replace this with their JWT/Session auth.
# Currently defaults to 'yahya' to keep your local test UI working.
# =====================================================================
def get_current_user_id():
    return request.headers.get('X-User-Id', 'yahya')

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

@app.route('/api/status')
def status():
    if not ai_handler:
        return ok({"status": "offline", "model": None})
    health = ai_handler.check_model_health()
    return ok(health)

@app.route('/api/welcome')
def welcome():
    if not db:
        return ok({"message": "Hello! I am your AI assistant."})
    
    user_id = get_current_user_id()
    memory = db.get_all_memory(user_id=user_id)
    todays = db.get_todays_tasks(user_id=user_id)
    overdue = db.get_overdue_tasks(user_id=user_id)
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

@app.route('/api/briefing')
def briefing():
    if not db:
        return ok({})
    return ok(db.get_daily_briefing(user_id=get_current_user_id()))

@app.route('/api/config')
def get_config():
    from config import Config
    lang = request.args.get('lang', 'en')
    return ok(Config.UI_CONFIG.get(lang, Config.UI_CONFIG['en']))

# =====================================================================
# CHAT — SSE STREAMING
# =====================================================================

@app.route('/api/chat/stream', methods=['POST'])
def chat_stream():
    """
    SSE streaming chat endpoint.
    """
    if not ai_handler or not db:
        def _error_stream():
            yield sse("error", {"code": "SERVICE_UNAVAILABLE", "message": "AI service not initialized"})
            yield sse("done", {"processing_time": 0})
        return Response(stream_with_context(_error_stream()), mimetype='text/event-stream')

    data = request.json or {}
    user_message = data.get('message', '').strip()
    language = data.get('language', 'en')
    user_id = get_current_user_id()

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
                        language=language,
                        database=db
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

            overdue = db.get_overdue_tasks(user_id=user_id)
            if overdue:
                yield sse("alert", {
                    "type": "overdue",
                    "message": f"You have {len(overdue)} overdue task(s).",
                    "tasks": [t['title'] for t in overdue[:3]]
                })
            todays = db.get_todays_tasks(user_id=user_id)
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

@app.route('/api/chat', methods=['POST'])
def chat():
    if not ai_handler or not db:
        return err("SERVICE_UNAVAILABLE", "AI service not initialized", 503)
    data = request.json or {}
    user_message = data.get('message', '').strip()
    if not user_message:
        return err("EMPTY_MESSAGE", "Message cannot be empty")
    try:
        result = ai_handler.process_multimodal_message(
            user_id=get_current_user_id(),
            user_message=user_message,
            message_type='text',
            language=data.get('language', 'en'),
            database=db
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
# WEBSOCKET — PROACTIVE ALERTS (push-based)
# =====================================================================

_ws_clients: list = []
_ws_lock = threading.Lock()

def _broadcast_alert(alert: dict):
    dead = []
    with _ws_lock:
        for ws in _ws_clients:
            try:
                ws.send(json.dumps({"type": "alert", "data": alert}))
            except Exception:
                dead.append(ws)
        for ws in dead:
            _ws_clients.remove(ws)

@sock.route('/ws/alerts')
def ws_alerts(ws):
    with _ws_lock:
        _ws_clients.append(ws)
    logging.info(f"WebSocket client connected. Total: {len(_ws_clients)}")
    try:
        ws.send(json.dumps({"type": "connected", "data": {"message": "iGenda alerts connected"}}))
        while True:
            msg = ws.receive(timeout=30)
            if msg is None:
                break
            try:
                data = json.loads(msg)
                if data.get("type") == "ping":
                    ws.send(json.dumps({"type": "pong", "data": {"ts": int(time.time())}}))
            except Exception:
                pass
    except Exception:
        pass
    finally:
        with _ws_lock:
            if ws in _ws_clients:
                _ws_clients.remove(ws)
        logging.info(f"WebSocket client disconnected. Total: {len(_ws_clients)}")

def _proactive_alert_worker():
    """
    Background thread — checks for overdue tasks and heavy schedules
    every 60 seconds and pushes alerts to all connected WebSocket clients.
    NOTE: For the backend team, this currently defaults to evaluating 'yahya'. 
    You will need to iterate over connected active users.
    """
    while True:
        time.sleep(60)
        if not db or not _ws_clients:
            continue
        try:
            # Defaulting to 'yahya' for the local worker thread
            user_id = 'yahya'
            overdue = db.get_overdue_tasks(user_id=user_id)
            if overdue:
                _broadcast_alert({
                    "type": "overdue",
                    "message": f"You have {len(overdue)} overdue task(s).",
                    "tasks": [t['title'] for t in overdue[:3]]
                })
            todays = db.get_todays_tasks(user_id=user_id)
            if len(todays) > 6:
                _broadcast_alert({
                    "type": "heavy_schedule",
                    "message": f"You have {len(todays)} tasks today — heavy schedule.",
                    "tasks": []
                })
        except Exception as e:
            logging.warning(f"Proactive worker error: {e}")

_alert_thread = threading.Thread(target=_proactive_alert_worker, daemon=True)
_alert_thread.start()

# =====================================================================
# CRUD — WORKSPACES
# =====================================================================

@app.route('/api/workspaces', methods=['GET'])
def get_workspaces():
    if not db: return err("DB_UNAVAILABLE", "Database not available", 503)
    return ok(db.get_workspaces(user_id=get_current_user_id()))

@app.route('/api/workspaces/<int:ws_id>', methods=['PATCH'])
def update_workspace(ws_id):
    if not db: return err("DB_UNAVAILABLE", "Database not available", 503)
    data = request.json or {}
    ws = db.update_workspace(user_id=get_current_user_id(), workspace_id=ws_id, updates=data)
    if not ws: return err("NOT_FOUND", f"Workspace {ws_id} not found", 404)
    return ok(ws)

@app.route('/api/workspaces/<int:ws_id>', methods=['DELETE'])
def delete_workspace(ws_id):
    if not db: return err("DB_UNAVAILABLE", "Database not available", 503)
    success = db.delete_workspace(user_id=get_current_user_id(), workspace_id=ws_id)
    if not success: return err("NOT_FOUND", f"Workspace {ws_id} not found", 404)
    return ok({"deleted": True, "id": ws_id})

# =====================================================================
# CRUD — TASKS
# =====================================================================

@app.route('/api/spaces', methods=['GET'])
def get_spaces():
    if not db: return err("DB_UNAVAILABLE", "Database not available", 503)
    workspace_id = request.args.get('workspace_id')
    spaces = db.get_spaces(user_id=get_current_user_id(), workspace_id=int(workspace_id) if workspace_id else None)
    return ok(spaces)

@app.route('/api/tasks/<int:task_id>/subtasks', methods=['GET'])
def get_task_subtasks(task_id):
    if not db: return err("DB_UNAVAILABLE", "Database not available", 503)
    data = db.get_task_with_subtasks(user_id=get_current_user_id(), task_id=task_id)
    if not data: return err("NOT_FOUND", f"Task {task_id} not found", 404)
    return ok(data)

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    if not db: return err("DB_UNAVAILABLE", "Database not available", 503)
    include_subtasks = request.args.get('include_subtasks', 'false').lower() == 'true'
    return ok(db.get_tasks(user_id=get_current_user_id(), include_subtasks=include_subtasks))

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    if not db: return err("DB_UNAVAILABLE", "Database not available", 503)
    success = db.delete_task(user_id=get_current_user_id(), task_id=task_id)
    if not success: return err("NOT_FOUND", f"Task {task_id} not found", 404)
    return ok({"deleted": True, "id": task_id})

@app.route('/api/tasks/<int:task_id>/complete', methods=['POST'])
def complete_task(task_id):
    if not db: return err("DB_UNAVAILABLE", "Database not available", 503)
    data = request.json or {}
    user_id = get_current_user_id()
    completed = data.get('completed', True)
    task = db.complete_task(user_id=user_id, task_id=task_id) if completed else db.uncomplete_task(user_id=user_id, task_id=task_id)
    if not task: return err("NOT_FOUND", f"Task {task_id} not found", 404)
    return ok({"task": task, "analytics": db.get_analytics(user_id=user_id)})

# =====================================================================
# CRUD — NOTES
# =====================================================================

@app.route('/api/notes', methods=['GET'])
def get_notes():
    if not db: return err("DB_UNAVAILABLE", "Database not available", 503)
    return ok(db.get_notes(user_id=get_current_user_id()))

@app.route('/api/notes/<int:note_id>', methods=['DELETE'])
def delete_note(note_id):
    if not db: return err("DB_UNAVAILABLE", "Database not available", 503)
    success = db.delete_note(user_id=get_current_user_id(), note_id=note_id)
    if not success: return err("NOT_FOUND", f"Note {note_id} not found", 404)
    return ok({"deleted": True, "id": note_id})

# =====================================================================
# ANALYTICS
# =====================================================================

@app.route('/api/analytics')
def analytics():
    if not db: return err("DB_UNAVAILABLE", "Database not available", 503)
    return ok(db.get_analytics(user_id=get_current_user_id()))

@app.route('/api/smart-analytics')
def smart_analytics():
    if not db: return err("DB_UNAVAILABLE", "Database not available", 503)
    return ok(db.get_smart_analytics(user_id=get_current_user_id()))

# =====================================================================
# MEMORY
# =====================================================================

@app.route('/api/memory', methods=['GET'])
def get_memory():
    if not db: return err("DB_UNAVAILABLE", "Database not available", 503)
    return ok(db.get_all_memory(user_id=get_current_user_id()))

@app.route('/api/memory', methods=['POST'])
def save_memory():
    if not db: return err("DB_UNAVAILABLE", "Database not available", 503)
    data = request.json or {}
    if not data.get('key') or not data.get('value'):
        return err("VALIDATION_ERROR", "Both 'key' and 'value' fields are required")
    db.save_memory(user_id=get_current_user_id(), key=data['key'], value=data['value'])
    return ok({"key": data['key'], "value": data['value']})

@app.route('/api/memory/<key>', methods=['DELETE'])
def delete_memory(key):
    if not db: return err("DB_UNAVAILABLE", "Database not available", 503)
    success = db.delete_memory(user_id=get_current_user_id(), key=key)
    if not success: return err("NOT_FOUND", f"Memory key '{key}' not found", 404)
    return ok({"deleted": True, "key": key})

# =====================================================================
# PROACTIVE — polling fallback
# =====================================================================

@app.route('/api/proactive')
def proactive_check():
    if not db: return ok({"alerts": []})
    alerts = []
    user_id = get_current_user_id()
    overdue = db.get_overdue_tasks(user_id=user_id)
    if overdue:
        alerts.append({
            "type": "overdue",
            "message": f"You have {len(overdue)} overdue task(s).",
            "tasks": [t['title'] for t in overdue[:3]]
        })
    todays = db.get_todays_tasks(user_id=user_id)
    if len(todays) > 6:
        alerts.append({
            "type": "heavy_schedule",
            "message": f"You have {len(todays)} tasks today — consider rescheduling.",
            "tasks": []
        })
    return ok({"alerts": alerts})

# =====================================================================
# UPLOAD
# =====================================================================

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if not ai_handler or not db:
        return err("SERVICE_UNAVAILABLE", "AI service not initialized", 503)
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
            user_id=get_current_user_id(),
            user_message=user_prompt,
            message_type='document_text',
            context_data=text_content,
            database=db
        )
        return ok(_format_agent_response(result))
    except Exception as e:
        logging.error(f"Upload error: {e}", exc_info=True)
        return err("UPLOAD_ERROR", str(e), 500)

# =====================================================================
# CLEAR
# =====================================================================

@app.route('/api/clear', methods=['POST'])
def clear():
    if not db: return err("DB_UNAVAILABLE", "Database not available", 503)
    db.clear_all(user_id=get_current_user_id())
    return ok({"cleared": True})

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
    if not db: return err("DB_UNAVAILABLE", "Database not available", 503)
    user_id = get_current_user_id()
    notes = db.get_notes(user_id=user_id)
    note = next((n for n in notes if n['id'] == note_id), None)
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
    if not db: return err("DB_UNAVAILABLE", "Database not available", 503)
    user_id = get_current_user_id()
    summary = db.get_workspace_summary(user_id=user_id, workspace_id=workspace_id)
    if not summary: return err("NOT_FOUND", f"Workspace {workspace_id} not found", 404)
    
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
    if not db: return err("DB_UNAVAILABLE", "Database not available", 503)
    user_id = get_current_user_id()
    try:
        tasks = db.get_todays_tasks(user_id=user_id)
        overdue = db.get_overdue_tasks(user_id=user_id)
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