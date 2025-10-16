from flask import Flask, render_template, request, jsonify
from database import Database
from ai_handler import AIHandler
from config import Config
import json

app = Flask(__name__)
db = Database()
ai_handler = AIHandler()

# Bilingual responses
RESPONSES = {
    'en': {
        'welcome': "Hello! I can help you create tasks, notes, and research topics in English or Arabic.",
        'success_task': "Created {count} task(s)",
        'success_note': "Created {count} note(s)", 
        'unknown': "I'm not sure what you want me to do. Try being more specific.",
        'error': "Sorry, there was an error processing your request."
    },
    'ar': {
        'welcome': "مرحباً! أستطيع مساعدتك في إنشاء المهام، الملاحظات، والمواضيع البحثية باللغة العربية أو الإنجليزية.",
        'success_task': "تم إنشاء {count} مهمة",
        'success_note': "تم إنشاء {count} ملاحظة",
        'unknown': "لم أفهم ما تريدني أن أفعله. حاول أن تكون أكثر تحديداً.",
        'error': "عذراً، حدث خطأ في معالجة طلبك."
    }
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        user_message = request.json.get('message', '').strip()
        
        if not user_message:
            return jsonify({'error': 'No message provided'}), 400
        
        # Process the message through AI
        result = ai_handler.process_message(user_message, db)
        response_lang = result['language']
        
        # Prepare response message
        response_parts = []
        
        if result['created_tasks']:
            response_parts.append(RESPONSES[response_lang]['success_task'].format(
                count=len(result['created_tasks'])
            ))
        
        if result['created_notes']:
            response_parts.append(RESPONSES[response_lang]['success_note'].format(
                count=len(result['created_notes'])
            ))
        
        if result['intent'] == 'unknown':
            response_message = RESPONSES[response_lang]['unknown']
        elif response_parts:
            response_message = " | ".join(response_parts)
        else:
            response_message = RESPONSES[response_lang]['success_task'].format(count=0)
        
        return jsonify({
            'response': response_message,
            'language': response_lang,
            'details': result,
            'tasks': db.get_tasks(),
            'notes': db.get_notes()
        })
        
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({
            'error': RESPONSES['en']['error'],
            'language': 'en'
        }), 500

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
    # Reset database
    db.data = {'tasks': [], 'notes': [], 'last_id': 0}
    db.save_data()
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=Config.DEBUG, port=Config.PORT)