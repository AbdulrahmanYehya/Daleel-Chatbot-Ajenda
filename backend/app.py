from flask import Flask, render_template, request, jsonify, session, send_file
from database import Database
from ai_handler import EnhancedAIHandler
from nlp_handler import DocumentProcessor
import json
import os
import io
import logging
from logging.handlers import RotatingFileHandler
import PyPDF2
# PDF Generation Imports
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
# Arabic Text Support Imports
import arabic_reshaper
from bidi.algorithm import get_display

app = Flask(__name__)
app.secret_key = 'ai_key_secure'

# --- 1. Logging Setup ---
def setup_logging():
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
        
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
        handlers=[
            RotatingFileHandler('ai_chatbot.log', maxBytes=1000000, backupCount=5, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    logging.info("Logging configured.")

setup_logging()

# --- 2. Initialize Core Components ---
try:
    db = Database()
    ai_handler = EnhancedAIHandler()
    logging.info("Database and AI Handler initialized successfully.")
except Exception as e:
    logging.critical(f"FATAL: Failed to initialize Database or AI Handler: {e}", exc_info=True)
    db = None
    ai_handler = None

# --- 3. Web Routes ---

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/status')
def status():
    if not ai_handler: return jsonify({'status': 'offline'})
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
        # Pass the database instance to the AI so it can Create/Delete/Update items
        response = ai_handler.process_multimodal_message(data.get('message', ''), database=db)
        return jsonify({'status': 'completed', 'result': response})
    except Exception as e:
        logging.error(f"Chat error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# --- 4. Database CRUD Routes ---

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    return jsonify(db.get_tasks() if db else [])

@app.route('/api/notes', methods=['GET'])
def get_notes():
    return jsonify(db.get_notes() if db else [])

@app.route('/api/analytics')
def analytics():
    return jsonify(db.get_analytics() if db else {})

@app.route('/api/tasks/<id>', methods=['DELETE'])
def delete_task(id):
    return jsonify({'success': db.delete_task(id) if db else False})

@app.route('/api/notes/<id>', methods=['DELETE'])
def delete_note(id):
    return jsonify({'success': db.delete_note(id) if db else False})

@app.route('/api/clear', methods=['POST'])
def clear(): 
    if db: db.clear_all()
    return jsonify({'success': True})

# --- 5. Advanced Features: Upload & Export ---

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
        
    try:
        text_content = DocumentProcessor.extract_text_from_file(file)
        if not text_content:
            return jsonify({'error': 'Could not extract text from file.'}), 400
            
        response = ai_handler.process_multimodal_message(
            text_content, 
            message_type='document_text', 
            database=db
        )
        return jsonify({'status': 'completed', 'result': response})
        
    except Exception as e:
        logging.error(f"Upload error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/export/pdf/<note_id>')
def export_pdf(note_id):
    """Generates a PDF for a specific note, supporting Arabic text and Line Wrapping."""
    if not db: return "Database error", 500
    
    notes = db.get_notes()
    note = next((n for n in notes if str(n['id']) == str(note_id)), None)
    
    if not note: return "Note not found", 404
    
    try:
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        
        # --- FONT CONFIGURATION FOR ARABIC ---
        font_path = os.path.join('static', 'Arial.ttf')
        font_name = 'Helvetica' # Default fallback
        
        if os.path.exists(font_path):
            try:
                pdfmetrics.registerFont(TTFont('ArabicFont', font_path))
                font_name = 'ArabicFont'
            except Exception as e:
                logging.warning(f"Could not register Arabic font: {e}")
        
        def fix_text(text):
            if not text: return ""
            try:
                reshaped = arabic_reshaper.reshape(text)
                return get_display(reshaped)
            except:
                return text

        # Draw Title
        p.setFont(font_name, 16)
        title_text = fix_text(note.get('title', 'Untitled'))
        p.drawString(50, height - 50, f"Title: {title_text}")
        
        # Draw Content with Line Wrapping
        p.setFont(font_name, 12)
        y_position = height - 100
        margin = 50
        max_width = width - 2 * margin
        
        content = note.get('content', '')
        
        # Split by newlines first to preserve paragraph structure
        for line in content.split('\n'):
            fixed_line = fix_text(line)
            
            # Now wrap long lines
            words = fixed_line.split()
            current_line = []
            
            for word in words:
                current_line.append(word)
                # Check width of current line
                line_width = p.stringWidth(' '.join(current_line), font_name, 12)
                
                if line_width > max_width:
                    # Pop the last word that made it too long
                    current_line.pop()
                    # Draw the line
                    p.drawString(margin, y_position, ' '.join(current_line))
                    y_position -= 20
                    # Start new line with the word we popped
                    current_line = [word]
                    
                    # Check for page break
                    if y_position < 50:
                        p.showPage()
                        p.setFont(font_name, 12)
                        y_position = height - 50
            
            # Draw remaining words in the line
            if current_line:
                p.drawString(margin, y_position, ' '.join(current_line))
                y_position -= 20
            
            if y_position < 50:
                p.showPage()
                p.setFont(font_name, 12)
                y_position = height - 50
            
        p.save()
        buffer.seek(0)
        
        return send_file(
            buffer, 
            as_attachment=True, 
            download_name=f"note_{note_id}.pdf", 
            mimetype='application/pdf'
        )
    except Exception as e:
        logging.error(f"Export error: {e}", exc_info=True)
        return str(e), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)