from flask import Flask, render_template, request, jsonify, session, copy_current_request_context
from database import Database
from ai_handler import EnhancedAIHandler
import json
import time
import threading
import copy
import requests
import os
from datetime import timedelta
import logging
from logging.handlers import RotatingFileHandler

# Setup logging
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
        handlers=[
            RotatingFileHandler('ai_chatbot.log', maxBytes=1000000, backupCount=5),
            logging.StreamHandler()
        ]
    )

setup_logging()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'ai_chatbot_secure_key_2024')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)

db = Database()
ai_handler = EnhancedAIHandler()

# Enhanced responses with context awareness
RESPONSES = {
    'en': {
        'welcome': "🚀 **Intelligent Productivity AI**\n\nI'm your AI assistant that can:\n• Create and schedule tasks\n• Plan your entire day\n• Research topics and create notes\n• Break down complex projects\n• Understand images and documents\n• Process voice commands\n• Adapt to your workflow\n\nI'll ask clarifying questions to give you the best results!",
        'examples': [
            "Create task for homework at 8pm with high priority",
            "Plan my study session for 2 hours tomorrow",
            "I need to exercise and cook dinner tonight",
            "Research artificial intelligence basics",
            "Make a note for my project ideas",
            "Schedule meetings for tomorrow: 10am team meeting, 2pm client call",
            "Create morning routine: exercise 7am, meditation 7:30, work 8am",
            "Plan my week from Monday to Friday with work tasks",
            "Create a complex project plan with multiple phases",
            "Research climate change effects with 500 words summary"
        ],
        'thinking': ["Analyzing your request...", "Planning your schedule...", "Creating your tasks...", "Optimizing your workflow..."],
        'tasks_title': "🎯 Your Tasks",
        'notes_title': "📚 Knowledge Base", 
        'input_placeholder': "What would you like me to help you accomplish?",
        'send_button': "Send to AI",
        'clear_button': "Clear All",
        'model_status': "AI Model: Ready"
    },
    'ar': {
        'welcome': "🚀 **مساعد الإنتاجية الذكي**\n\nأنا مساعدك الذكي الذي يستطيع:\n• إنشاء وجدولة المهام\n• تخطيط يومك بالكامل\n• البحث في المواضيع وإنشاء الملاحظات\n• تحليل المشاريع المعقدة\n• فهم الصور والمستندات\n• معالجة الأوامر الصوتية\n• التكيف مع أسلوب عملك\n\nسأطرح أسئلة توضيحية لتحقيق أفضل النتائج!",
        'examples': [
            "اعمل مهمة للواجب الساعة 8 مساء بأولوية عالية",
            "خطط لي جلسة مذاكرة لمدة ساعتين غداً",
            "أريد التمرين وطبخ العشاء الليلة",
            "ابحث عن أساسيات الذكاء الاصطناعي",
            "أنشئ ملاحظة لأفكار مشروعي",
            "جدول اجتماعات غداً: فريق العمل 10 صباحاً، اتصال عميل 2 عصراً",
            "أنشئ روتين صباحي: تمارين 7 صباحاً، تأمل 7:30، عمل 8 صباحاً",
            "خطط لأسبوع كامل من الإثنين إلى الجميع بمهام العمل",
            "أنشئ خطة مشروع معقدة بمراحل متعددة",
            "ابحث عن تأثيرات التغير المناخي بملخص 500 كلمة"
        ],
        'thinking': ["جاري تحليل طلبك...", "جاري تخطيط جدولك...", "جاري إنشاء مهامك...", "جاري تحسين سير العمل..."],
        'tasks_title': "🎯 مهامك",
        'notes_title': "📚 قاعدة المعرفة",
        'input_placeholder': "ماذا تريد أن أساعدك في تحقيقه؟",
        'send_button': "إرسال للذكاء الاصطناعي",
        'clear_button': "مسح الكل",
        'model_status': "نموذج الذكاء الاصطناعي: جاهز"
    }
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/ai/status')
def ai_status():
    """Enhanced AI model status check"""
    try:
        # Test AI model with a simple prompt
        test_response = ai_handler.check_model_health()
        return jsonify({
            'status': 'online',
            'model': ai_handler.model_name,
            'response_time': test_response.get('response_time', 0),
            'capabilities': {
                'multimodal': True,
                'voice_processing': True,
                'image_understanding': True,
                'context_awareness': True,
                'smart_scheduling': True
            }
        })
    except Exception as e:
        logging.error(f"AI status check failed: {e}")
        return jsonify({
            'status': 'offline', 
            'model': ai_handler.model_name,
            'error': str(e)
        }), 500
@app.route('/api/status')
def status():
    """General status endpoint for frontend"""
    try:
        response = ai_status()
        return response
    except Exception as e:
        return jsonify({
            'status': 'offline',
            'error': str(e)
        }), 500
        
@app.route('/api/chat', methods=['POST'])
def ai_chat():
    """Enhanced AI chat endpoint with multimodal support - SYNCHRONOUS VERSION"""
    start_time = time.time()
    
    try:
        data = request.json
        user_message = data.get('message', '').strip()
        message_type = data.get('type', 'text')
        context_data = data.get('context', {})
        file_data = data.get('file_data', None)
        
        if not user_message and not file_data:
            return jsonify({'error': 'No message or file provided'}), 400
        
        # Process message SYNCHRONOUSLY (no background thread)
        result = ai_handler.process_multimodal_message(
            user_message=user_message,
            message_type=message_type,
            context_data=context_data,
            file_data=file_data,
            database=db
        )
        
        processing_time = time.time() - start_time
        
        return jsonify({
            'status': 'completed',
            'result': result,
            'processing_time': round(processing_time, 2),
            'ai_metadata': result.get('ai_metadata', {})
        })
        
    except Exception as e:
        logging.error(f"Error in AI chat endpoint: {e}")
        return jsonify({
            'status': 'error',
            'message': 'AI system error occurred'
        }), 500

@app.route('/api/chat/result/<message_id>')
def get_ai_chat_result(message_id):
    """Poll for AI chat result - SIMPLIFIED"""
    # Since we're now synchronous, this endpoint should rarely be called
    # But we'll keep it for compatibility
    return jsonify({
        'status': 'processing',
        'message': 'Request is being processed'
    })

@app.route('/api/ai/analyze/image', methods=['POST'])
def analyze_image():
    """Analyze image and extract tasks/notes"""
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image provided'}), 400
        
        image_file = request.files['image']
        analysis_type = request.form.get('type', 'general')  # tasks, notes, general
        
        # Process image with AI
        result = ai_handler.analyze_image(image_file, analysis_type, db)
        
        return jsonify({
            'status': 'success',
            'result': result,
            'analysis_type': analysis_type
        })
        
    except Exception as e:
        logging.error(f"Image analysis error: {e}")
        return jsonify({'error': 'Image analysis failed'}), 500

@app.route('/api/ai/process/voice', methods=['POST'])
def process_voice():
    """Process voice input"""
    try:
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio provided'}), 400
        
        audio_file = request.files['audio']
        language = request.form.get('language', 'auto')
        
        # Process audio with AI
        result = ai_handler.process_voice_input(audio_file, language, db)
        
        return jsonify({
            'status': 'success',
            'result': result,
            'detected_language': result.get('detected_language', language)
        })
        
    except Exception as e:
        logging.error(f"Voice processing error: {e}")
        return jsonify({'error': 'Voice processing failed'}), 500

@app.route('/api/ai/suggestions', methods=['POST'])
def get_ai_suggestions():
    """Get AI-powered suggestions based on context"""
    try:
        data = request.json
        context = data.get('context', {})
        suggestion_type = data.get('type', 'tasks')  # tasks, notes, both
        
        suggestions = ai_handler.generate_suggestions(context, suggestion_type)
        
        return jsonify({
            'status': 'success',
            'suggestions': suggestions,
            'type': suggestion_type
        })
        
    except Exception as e:
        logging.error(f"Suggestions error: {e}")
        return jsonify({'error': 'Failed to generate suggestions'}), 500

@app.route('/api/ai/analyze/productivity', methods=['GET'])
def analyze_productivity():
    """AI-powered productivity analysis"""
    try:
        analysis = ai_handler.analyze_productivity_patterns(db)
        
        return jsonify({
            'status': 'success',
            'analysis': analysis,
            'timestamp': time.time()
        })
        
    except Exception as e:
        logging.error(f"Productivity analysis error: {e}")
        return jsonify({'error': 'Productivity analysis failed'}), 500

@app.route('/api/config')
def get_config():
    lang = request.args.get('lang', 'en')
    return jsonify(RESPONSES[lang])

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    return jsonify(db.get_tasks())

@app.route('/api/notes', methods=['GET'])
def get_notes():
    return jsonify(db.get_notes())

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    db.delete_task(task_id)
    return jsonify({'success': True})

@app.route('/api/notes/<int:note_id>', methods=['DELETE'])
def delete_note(note_id):
    db.delete_note(note_id)
    return jsonify({'success': True})

@app.route('/api/clear', methods=['POST'])
def clear_all():
    db.clear_all()
    session.clear()
    return jsonify({'success': True})

@app.route('/api/analytics')
def get_analytics():
    tasks = db.get_tasks()
    notes = db.get_notes()
    
    return jsonify({
        'total_tasks': len(tasks),
        'total_notes': len(notes),
        'completed_tasks': len([t for t in tasks if t.get('completed', False)]),
        'high_priority_tasks': len([t for t in tasks if t.get('priority') == 'high'])
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000, threaded=True)