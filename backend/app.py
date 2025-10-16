from flask import Flask, render_template, request, jsonify, session
from database import Database
from ai_handler import AIHandler
import json
import time
import threading
from datetime import timedelta

app = Flask(__name__)
app.secret_key = 'productivity_secret_2024'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)

db = Database()
ai_handler = AIHandler()

# Enhanced responses with Mistral 7B
RESPONSES = {
    'en': {
        'welcome': "🚀 **Intelligent Productivity AI**\n\nI'm your AI assistant that can:\n• Create and schedule tasks\n• Plan your entire day\n• Research topics and create notes\n• Break down complex projects\n• Adapt to your workflow\n\nI'll ask clarifying questions to give you the best results!",
        'examples': [
            "Plan my entire workday: deep work 9-11am, meetings 2-3pm, email catchup 4pm",
            "Research quantum computing and create a detailed study note",
            "I have a big project due Friday - break it down into daily tasks",
            "Create a morning routine: exercise 7am, meditation 7:30, planning 8am",
            "Make a note for my business plan with market analysis and financial projections",
            "Schedule my exam preparation: 2 weeks, 3 subjects, 2 hours daily",
            "Create tasks for home renovation: planning, purchasing, execution phases"
        ],
        'thinking': ["Analyzing your request...", "Planning your schedule...", "Researching the topic...", "Creating your tasks...", "Optimizing your workflow..."],
        'tasks_title': "🎯 Your Tasks",
        'notes_title': "📚 Knowledge Base", 
        'input_placeholder': "What would you like me to help you accomplish?",
        'send_button': "Send to AI",
        'clear_button': "Clear All",
        'model_status': "AI Model: Ready"
    },
    'ar': {
        'welcome': "🚀 **مساعد الإنتاجية الذكي**\n\nأنا مساعدك الذكي الذي يستطيع:\n• إنشاء وجدولة المهام\n• تخطيط يومك بالكامل\n• البحث في المواضيع وإنشاء الملاحظات\n• تحليل المشاريع المعقدة\n• التكيف مع أسلوب عملك\n\nسأطرح أسئلة توضيحية لتحقيق أفضل النتائج!",
        'examples': [
            "خطط لي يوم عمل كامل: عمل مركز 9-11 صباحاً، اجتماعات 2-3 عصراً، متابعة البريد 4 عصراً",
            "ابحث عن الحوسبة الكمية وأنشئ ملاحظة دراسة مفصلة",
            "لدي مشروع كبير due يوم الجمعة - قم بتقسيمه إلى مهام يومية",
            "أنشئ روتين صباحي: تمارين 7 صباحاً، تأمل 7:30، تخطيط 8 صباحاً",
            "أنشئ ملاحظة لخطة عملي مع تحليل السوق والتوقعات المالية",
            "جدول تحضيري للامتحان: أسبوعين، 3 مواد، ساعتين يومياً",
            "أنشئ مهام لتجديد المنزل: التخطيط، الشراء، التنفيذ"
        ],
        'thinking': ["جاري تحليل طلبك...", "جاري تخطيط جدولك...", "جاري البحث في الموضوع...", "جاري إنشاء مهامك...", "جاري تحسين سير العمل..."],
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

@app.route('/api/status')
def api_status():
    """Check if AI model is responding"""
    try:
        test_response = ai_handler.test_model()
        return jsonify({
            'status': 'online',
            'model': ai_handler.model_name,
            'response_time': test_response.get('response_time', 0)
        })
    except:
        return jsonify({'status': 'offline', 'model': ai_handler.model_name}), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    start_time = time.time()
    
    try:
        user_message = request.json.get('message', '').strip()
        message_id = request.json.get('message_id', '')
        
        if not user_message:
            return jsonify({'error': 'No message provided'}), 400
        
        # Get thinking message based on content
        language = ai_handler.detect_language(user_message)
        thinking_msg = ai_handler.get_thinking_message(user_message, language)
        
        # Process message in background thread for better UX
        def process_message():
            result = ai_handler.process_message(user_message, db)
            processing_time = time.time() - start_time
            
            # Store result in session for frontend to fetch
            session[f'result_{message_id}'] = {
                'result': result,
                'processing_time': processing_time,
                'timestamp': time.time()
            }
        
        # Start processing in background
        thread = threading.Thread(target=process_message)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'status': 'processing',
            'thinking_message': thinking_msg,
            'message_id': message_id,
            'language': language
        })
        
    except Exception as e:
        print(f"Error in chat endpoint: {e}")
        return jsonify({
            'status': 'error',
            'message': 'System error occurred'
        }), 500

@app.route('/api/chat/result/<message_id>')
def get_chat_result(message_id):
    """Poll for chat result"""
    result_data = session.get(f'result_{message_id}')
    
    if not result_data:
        return jsonify({'status': 'processing'})
    
    result = result_data['result']
    processing_time = result_data['processing_time']
    
    # Clean up
    session.pop(f'result_{message_id}', None)
    
    return jsonify({
        'status': 'completed',
        'result': result,
        'processing_time': round(processing_time, 2)
    })

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
        'high_priority_tasks': len([t for t in tasks if t.get('priority') == 'high']),
        'recent_activity': len([t for t in tasks if is_recent(t.get('created_at', ''))])
    })

def is_recent(timestamp):
    from datetime import datetime, timedelta
    try:
        created = datetime.fromisoformat(timestamp)
        return datetime.now() - created < timedelta(hours=24)
    except:
        return False

if __name__ == '__main__':
    app.run(debug=True, port=5000, threaded=True)