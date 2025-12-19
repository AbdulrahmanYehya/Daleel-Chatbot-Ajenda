from flask import Flask, render_template, request, jsonify, session
from database import Database
from ai_handler import EnhancedAIHandler
import json
import time
import os
from datetime import timedelta
import logging
from logging.handlers import RotatingFileHandler

# --- Setup logging ---
def setup_logging():
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
        
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
        handlers=[
            RotatingFileHandler('ai_chatbot.log', maxBytes=1000000, backupCount=5, encoding='utf-8'), # Added encoding
            logging.StreamHandler()
        ]
    )
    logging.info("Logging configured.")

setup_logging()
# --- End logging setup ---

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'ai_chatbot_secure_key_2024_v2') # Changed key slightly
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)

# --- Initialize Core Components ---
try:
    db = Database()
    ai_handler = EnhancedAIHandler()
    logging.info("Database and AI Handler initialized successfully.")
except Exception as e:
     logging.critical(f"FATAL: Failed to initialize Database or AI Handler: {e}", exc_info=True)
     # Depending on deployment, might want to exit or raise further
     db = None
     ai_handler = None
# --- End Initialization ---


# Responses (Unchanged, keep as is)
RESPONSES = {
    'en': {
        'welcome': "🚀 **Intelligent Productivity AI**\n\nHow can I help you be more productive today?\nI can:\n• Create tasks from complex requests\n• Plan your schedule over hours or days\n• Generate notes or save your thoughts\n• Update or delete existing items\n• Understand voice commands (via mic button)\n\nJust tell me what you need!",
        'examples': [
            "Schedule: Exercise 7am for 1 hour, Team meeting 10am, Lunch 1pm, Project work 2-5pm",
            "Create task: Finish report by Friday high priority",
            "Plan my next 3 days to study 10 lectures, 1 hour each",
            "Write a note about the benefits of time blocking",
            "Note: Remember to buy milk and eggs",
            "Update my 'Team meeting' task time to 11am",
            "Delete the 'buy milk' note"
        ],
        'thinking': ["Analyzing...", "Planning...", "Creating...", "Updating...", "Working on it..."],
        'tasks_title': "🎯 Your Tasks",
        'notes_title': "📚 Knowledge Base",
        'input_placeholder': "Tell me what you need help with...",
        'send_button': "Send",
        'clear_button': "Clear All",
        'model_status': "AI Model: Ready"
    },
    'ar': {
        'welcome': "🚀 **مساعد الإنتاجية الذكي**\n\nكيف يمكنني مساعدتك لتكون أكثر إنتاجية اليوم؟\nأستطيع:\n• إنشاء مهام من طلبات معقدة\n• تخطيط جدولك لساعات أو أيام\n• إنشاء ملاحظات أو حفظ أفكارك\n• تحديث أو حذف العناصر الموجودة\n• فهم الأوامر الصوتية (عبر زر الميكروفون)\n\nفقط أخبرني بما تحتاجه!",
        'examples': [
            "جدول: تمرين 7 صباحاً لمدة ساعة، اجتماع الفريق 10 صباحاً، غداء 1 ظهراً، عمل المشروع 2-5 مساءً",
            "أنشئ مهمة: إنهاء التقرير بحلول الجمعة بأولوية عالية",
            "خطط لي الأيام الثلاثة القادمة لدراسة 10 محاضرات، ساعة لكل محاضرة",
            "اكتب ملاحظة عن فوائد تنظيم الوقت",
            "ملاحظة: تذكر شراء الحليب والبيض",
            "حدث وقت مهمة 'اجتماع الفريق' إلى 11 صباحاً",
            "احذف ملاحظة 'شراء الحليب'"
        ],
        'thinking': ["جاري التحليل...", "جاري التخطيط...", "جاري الإنشاء...", "جاري التحديث...", "جاري العمل..."],
        'tasks_title': "🎯 مهامك",
        'notes_title': "📚 قاعدة المعرفة",
        'input_placeholder': "أخبرني بما تحتاج للمساعدة فيه...",
        'send_button': "إرسال",
        'clear_button': "مسح الكل",
        'model_status': "نموذج الذكاء الاصطناعي: جاهز"
    }
}


@app.route('/')
def index():
    # Ensure components initialized
    if not db or not ai_handler:
         return "Error: Backend components failed to initialize. Check logs.", 500
    return render_template('index.html')

@app.route('/api/status')
def status():
    """General status endpoint including AI model health."""
    if not ai_handler:
         return jsonify({'status': 'offline', 'error': 'AI Handler not initialized'}), 500
         
    try:
        ai_health = ai_handler.check_model_health()
        db_status = 'online' if db else 'offline' # Simple check if db object exists

        return jsonify({
            'status': ai_health['status'], # Overall status mirrors AI model
            'ai_model_status': ai_health['status'],
            'database_status': db_status,
            'model': ai_health.get('model', 'N/A'),
            'response_time': ai_health.get('response_time', 0),
            'ai_error': ai_health.get('error') # Include AI error if present
        })
    except Exception as e:
        logging.error(f"Error in /api/status endpoint: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@app.route('/api/chat', methods=['POST'])
def ai_chat():
    """Main endpoint for processing user messages (synchronous)."""
    if not ai_handler or not db:
         return jsonify({'status': 'error', 'message': 'Backend components not initialized'}), 500

    start_time = time.time()
    try:
        data = request.json
        user_message = data.get('message', '').strip()
        message_type = data.get('type', 'text') # For potential future use (e.g., image description)
        context_data = data.get('context', {}) # For potential future use

        if not user_message:
            return jsonify({'error': 'No message provided'}), 400

        # Process message SYNCHRONOUSLY using the revamped handler
        result = ai_handler.process_multimodal_message(
            user_message=user_message,
            message_type=message_type,
            context_data=context_data,
            # file_data=None, # Not handling file uploads via this endpoint currently
            database=db
        )

        processing_time = time.time() - start_time
        logging.info(f"Chat request processed in {processing_time:.2f}s. Result: {result}")

        return jsonify({
            'status': 'completed', # Always completed for sync
            'result': result, # Pass the whole result dict from ai_handler
            'processing_time': round(processing_time, 2),
            'ai_metadata': result.get('ai_metadata', {})
        })

    except Exception as e:
        # Log the full traceback
        logging.error(f"Error in AI chat endpoint: {e}", exc_info=True)
        # Determine language for error message
        try:
             lang = ai_handler.detect_language(data.get('message','')) if ai_handler else 'en'
        except:
             lang = 'en'
        error_msg = "Sorry, an internal error occurred." if lang=='en' else "عذراً، حدث خطأ داخلي."
        return jsonify({
            'status': 'error',
            'message': error_msg,
            'result': {'response_message': error_msg, 'tasks': [], 'notes': [], 'language': lang} # Provide basic structure
        }), 500


@app.route('/api/config')
def get_config():
    lang = request.args.get('lang', 'en')
    return jsonify(RESPONSES.get(lang, RESPONSES['en']))

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    if not db: return jsonify({"error": "Database not initialized"}), 500
    try:
        return jsonify(db.get_tasks())
    except Exception as e:
         logging.error(f"Error fetching tasks: {e}", exc_info=True)
         return jsonify({"error": "Failed to fetch tasks"}), 500


@app.route('/api/notes', methods=['GET'])
def get_notes():
    if not db: return jsonify({"error": "Database not initialized"}), 500
    try:
        return jsonify(db.get_notes())
    except Exception as e:
         logging.error(f"Error fetching notes: {e}", exc_info=True)
         return jsonify({"error": "Failed to fetch notes"}), 500


@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    if not db: return jsonify({"error": "Database not initialized"}), 500
    try:
        success = db.delete_task(task_id)
        if success:
             return jsonify({'success': True})
        else:
             return jsonify({'success': False, 'error': 'Task not found'}), 404
    except Exception as e:
        logging.error(f"Error deleting task {task_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/notes/<int:note_id>', methods=['DELETE'])
def delete_note(note_id):
    if not db: return jsonify({"error": "Database not initialized"}), 500
    try:
        success = db.delete_note(note_id)
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Note not found'}), 404
    except Exception as e:
        logging.error(f"Error deleting note {note_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/clear', methods=['POST'])
def clear_all():
    if not db: return jsonify({"error": "Database not initialized"}), 500
    try:
        db.clear_all()
        session.clear() # Clear Flask session as well
        return jsonify({'success': True})
    except Exception as e:
         logging.error(f"Error clearing database: {e}", exc_info=True)
         return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/analytics')
def get_analytics():
    """FR-16: Provide user insights from database."""
    if not db: return jsonify({"error": "Database not initialized"}), 500
    try:
        # get_analytics now calculates counts correctly
        analytics_data = db.get_analytics()
        return jsonify(analytics_data)

    except Exception as e:
        logging.error(f"Error getting analytics: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# --- Removed unused AI endpoints: ---
# /api/ai/suggestions (FR-14 stub remains in ai_handler but no dedicated endpoint for now)
# /api/ai/analyze/productivity (Merged into /api/analytics)


if __name__ == '__main__':
    if not db or not ai_handler:
         print("CRITICAL: Failed to initialize backend components. Exiting.")
    else:
         # Use waitress or gunicorn for production instead of Flask's dev server
         # For development:
         app.run(debug=True, port=5000, threaded=True) # threaded=True can help with responsiveness