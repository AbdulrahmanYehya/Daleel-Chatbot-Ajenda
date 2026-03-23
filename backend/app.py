from flask import Flask, render_template, request, jsonify, send_file
from database import Database
from ai_handler import EnhancedAIHandler
from nlp_handler import DocumentProcessor
import json, os, io, logging
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
# CORE ROUTES
# =====================================================================

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/status')
def status():
    if not ai_handler:
        return jsonify({'status': 'offline'})
    return jsonify(ai_handler.check_model_health())

@app.route('/api/config')
def get_config():
    from config import Config
    lang = request.args.get('lang', 'en')
    return jsonify(Config.UI_CONFIG.get(lang, Config.UI_CONFIG['en']))

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    try:
        response = ai_handler.process_multimodal_message(
            user_message=data.get('message', ''),
            message_type='text',
            language=data.get('language', 'en'),
            database=db
        )
        return jsonify({'status': 'completed', 'result': response})
    except Exception as e:
        logging.error(f"Chat error: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500

# =====================================================================
# WELCOME & BRIEFING
# =====================================================================

@app.route('/api/welcome')
def welcome():
    if not db:
        return jsonify({'message': 'Hello! I am your AI assistant.'})
    memory = db.get_all_memory()
    todays = db.get_todays_tasks()
    overdue = db.get_overdue_tasks()
    hour = datetime.now().hour
    greeting = "Good morning" if hour < 12 else ("Good afternoon" if hour < 17 else "Good evening")
    parts = [f"{greeting}, Yahya! 👋"]
    if todays:
        parts.append(f"You have **{len(todays)} task(s)** scheduled for today.")
    else:
        parts.append("Your schedule is clear today — want me to plan something?")
    if overdue:
        parts.append(f"⚠️ **{len(overdue)} overdue task(s)** need your attention.")
    goal = memory.get('goal') or memory.get('goal_2026')
    if goal:
        parts.append(f"Keep pushing toward: *{goal}* 💪")
    return jsonify({'message': '\n'.join(parts)})

@app.route('/api/briefing')
def briefing():
    """Returns structured daily briefing data for the frontend briefing panel."""
    if not db:
        return jsonify({})
    return jsonify(db.get_daily_briefing())

# =====================================================================
# CRUD ROUTES
# =====================================================================

@app.route('/api/workspaces', methods=['GET'])
def get_workspaces():
    return jsonify(db.get_workspaces() if db else [])

@app.route('/api/workspaces/<int:ws_id>', methods=['PATCH'])
def update_workspace(ws_id):
    """Update workspace color or other fields."""
    data = request.json or {}
    if db:
        ws = db.update_workspace(ws_id, data)
        if ws:
            return jsonify({'success': True, 'workspace': ws})
    return jsonify({'success': False}), 404

@app.route('/api/workspaces/<id>', methods=['DELETE'])
def delete_workspace(id):
    return jsonify({'success': db.delete_workspace(id) if db else False})

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    return jsonify(db.get_tasks() if db else [])

@app.route('/api/notes', methods=['GET'])
def get_notes():
    return jsonify(db.get_notes() if db else [])

@app.route('/api/analytics')
def analytics():
    return jsonify(db.get_analytics() if db else {})

@app.route('/api/smart-analytics')
def smart_analytics():
    """Full behavioral analytics for the analytics panel and agent tool."""
    if not db:
        return jsonify({})
    return jsonify(db.get_smart_analytics())

@app.route('/api/tasks/<id>', methods=['DELETE'])
def delete_task(id):
    return jsonify({'success': db.delete_task(id) if db else False})

@app.route('/api/tasks/<int:task_id>/complete', methods=['POST'])
def complete_task(task_id):
    if not db:
        return jsonify({'success': False}), 500
    data = request.json or {}
    completed = data.get('completed', True)
    task = db.complete_task(task_id) if completed else db.uncomplete_task(task_id)
    if task:
        return jsonify({'success': True, 'task': task, 'analytics': db.get_analytics()})
    return jsonify({'success': False, 'error': 'Task not found'}), 404

@app.route('/api/notes/<id>', methods=['DELETE'])
def delete_note(id):
    return jsonify({'success': db.delete_note(id) if db else False})

@app.route('/api/clear', methods=['POST'])
def clear():
    if db:
        db.clear_all()
    return jsonify({'success': True})

# =====================================================================
# MEMORY ROUTES
# =====================================================================

@app.route('/api/memory', methods=['GET'])
def get_memory():
    return jsonify(db.get_all_memory() if db else {})

@app.route('/api/memory', methods=['POST'])
def save_memory():
    data = request.json
    if db and data.get('key') and data.get('value'):
        db.save_memory(data['key'], data['value'])
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'key and value required'}), 400

@app.route('/api/memory/<key>', methods=['DELETE'])
def delete_memory(key):
    if db:
        return jsonify({'success': db.delete_memory(key)})
    return jsonify({'success': False})

# =====================================================================
# PROACTIVE ALERTS
# =====================================================================

@app.route('/api/proactive')
def proactive_check():
    if not db:
        return jsonify({'alerts': []})
    alerts = []
    overdue = db.get_overdue_tasks()
    if overdue:
        alerts.append({
            "type": "overdue",
            "message": f"You have {len(overdue)} overdue task(s).",
            "tasks": [t['title'] for t in overdue[:3]]
        })
    todays = db.get_todays_tasks()
    if len(todays) > 6:
        alerts.append({
            "type": "heavy_schedule",
            "message": f"You have {len(todays)} tasks today — consider rescheduling some."
        })
    return jsonify({'alerts': alerts})

# =====================================================================
# UPLOAD
# =====================================================================

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    user_prompt = request.form.get('message',
        'Please analyze this document, summarize it, and extract any actionable tasks or notes.')
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    try:
        text_content = DocumentProcessor.extract_text_from_file(file)
        if not text_content:
            return jsonify({'error': 'Could not extract text from file.'}), 400
        response = ai_handler.process_multimodal_message(
            user_message=user_prompt, message_type='document_text',
            context_data=text_content, database=db
        )
        return jsonify({'status': 'completed', 'result': response})
    except Exception as e:
        logging.error(f"Upload error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# =====================================================================
# PDF EXPORT — individual note or full workspace
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
    """Draw text with line wrapping. Returns updated y position."""
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

@app.route('/api/export/pdf/<note_id>')
def export_pdf(note_id):
    if not db:
        return "Database error", 500
    notes = db.get_notes()
    note = next((n for n in notes if str(n['id']) == str(note_id)), None)
    if not note:
        return "Note not found", 404
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
        p.drawString(margin, y, f"Category: {note.get('category', 'General')} | Words: {note.get('word_count', 0)} | Created: {note.get('created_at', '')[:10]}")
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
        return str(e), 500

@app.route('/api/export/workspace/<int:workspace_id>')
def export_workspace_pdf(workspace_id):
    """Export a full workspace summary as PDF — tasks + notes."""
    if not db:
        return "Database error", 500
    summary = db.get_workspace_summary(workspace_id)
    if not summary:
        return "Workspace not found", 404
    try:
        buffer = io.BytesIO()
        p, width, height, font_name = _make_canvas(buffer)
        margin, max_width = 50, width - 100
        y = height - 50

        # Title
        p.setFont(font_name, 20)
        p.drawString(margin, y, _fix_text(summary['workspace']['name']))
        y -= 25
        if summary['workspace'].get('description'):
            p.setFont(font_name, 11)
            p.setFillColorRGB(0.4, 0.4, 0.4)
            y = _draw_wrapped(p, summary['workspace']['description'], font_name, 11, margin, max_width, y, height)
            p.setFillColorRGB(0, 0, 0)
        y -= 10
        p.line(margin, y, width - margin, y)
        y -= 20

        # Tasks section
        p.setFont(font_name, 14)
        p.drawString(margin, y, f"Tasks ({len(summary['tasks'])})")
        y -= 20
        for task in summary['tasks']:
            status = "✓" if task.get('completed') else "○"
            priority_map = {'high': '!!!', 'medium': '!!', 'low': '!'}
            pri = priority_map.get(task.get('priority', 'medium'), '')
            line = f"{status} {pri} {task['title']}"
            if task.get('due_date'):
                line += f"  [{task['due_date']}]"
            if task.get('recurrence'):
                line += f"  ↻ {task['recurrence']}"
            y = _draw_wrapped(p, line, font_name, 11, margin + 10, max_width - 10, y, height)
            if task.get('description'):
                p.setFillColorRGB(0.4, 0.4, 0.4)
                y = _draw_wrapped(p, f"  {task['description']}", font_name, 9, margin + 20, max_width - 20, y, height)
                p.setFillColorRGB(0, 0, 0)
            y -= 4

        y -= 15
        p.line(margin, y, width - margin, y)
        y -= 20

        # Notes section
        p.setFont(font_name, 14)
        p.drawString(margin, y, f"Notes ({len(summary['notes'])})")
        y -= 20
        for note in summary['notes']:
            p.setFont(font_name, 12)
            y = _draw_wrapped(p, note['title'], font_name, 12, margin, max_width, y, height)
            y -= 4
            y = _draw_wrapped(p, note.get('content', ''), font_name, 10, margin + 10, max_width - 10, y, height)
            y -= 15

        p.save()
        buffer.seek(0)
        ws_name = summary['workspace']['name'].replace(' ', '_')
        return send_file(buffer, as_attachment=True,
                         download_name=f"workspace_{ws_name}.pdf",
                         mimetype='application/pdf')
    except Exception as e:
        logging.error(f"Workspace export error: {e}", exc_info=True)
        return str(e), 500

@app.route('/api/export/tasks/today')
def export_today_pdf():
    """Export today's task list as a PDF."""
    if not db:
        return "Database error", 500
    try:
        tasks = db.get_todays_tasks()
        overdue = db.get_overdue_tasks()
        buffer = io.BytesIO()
        p, width, height, font_name = _make_canvas(buffer)
        margin, max_width = 50, width - 100
        y = height - 50
        today_str = datetime.now().strftime('%A, %B %d %Y')
        p.setFont(font_name, 18)
        p.drawString(margin, y, _fix_text(f"Daily Plan — {today_str}"))
        y -= 30
        p.line(margin, y, width - margin, y)
        y -= 20

        if overdue:
            p.setFont(font_name, 13)
            p.setFillColorRGB(0.8, 0.1, 0.1)
            p.drawString(margin, y, f"⚠ Overdue ({len(overdue)})")
            p.setFillColorRGB(0, 0, 0)
            y -= 18
            for t in overdue:
                y = _draw_wrapped(p, f"  • {t['title']} (was due {t['due_date']})", font_name, 10, margin, max_width, y, height)
            y -= 10

        p.setFont(font_name, 13)
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
        return send_file(buffer, as_attachment=True,
                         download_name=f"daily_plan_{datetime.now().strftime('%Y-%m-%d')}.pdf",
                         mimetype='application/pdf')
    except Exception as e:
        logging.error(f"Today export error: {e}", exc_info=True)
        return str(e), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)