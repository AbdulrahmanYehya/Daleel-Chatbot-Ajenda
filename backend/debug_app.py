from flask import Flask, render_template, request, jsonify
import json
import requests
import re

app = Flask(__name__)

# Simple in-memory storage for debugging
tasks = []
notes = []

class SimpleAIHandler:
    def __init__(self):
        self.ollama_url = "http://localhost:11434/api/generate"
    
    def debug_ai_communication(self, user_message):
        """Test the AI communication and see the raw response"""
        
        # Simple system prompt for testing
        system_prompt = """
You are a task creation assistant. Respond with ONLY JSON in this exact format:
{
  "tasks": [
    {
      "title": "task title",
      "description": "task description", 
      "due_time": "HH:MM"
    }
  ],
  "notes": []
}

User: Create a task for homework at 7pm
Assistant: {"tasks": [{"title": "Complete homework", "description": "Finish homework assignment", "due_time": "19:00"}], "notes": []}
"""
        
        full_prompt = f"{system_prompt}\n\nUser: {user_message}\nAssistant:"
        
        payload = {
            "model": "phi3",
            "prompt": full_prompt,
            "stream": False
        }
        
        print("=== DEBUG AI REQUEST ===")
        print(f"User message: {user_message}")
        print(f"Full prompt: {full_prompt[:500]}...")
        
        try:
            response = requests.post(self.ollama_url, json=payload, timeout=30)
            print(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                raw_response = result['response']
                print(f"Raw AI response: {raw_response}")
                
                # Try to extract JSON
                json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
                    print(f"Extracted JSON: {json_str}")
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError as e:
                        print(f"JSON decode error: {e}")
                        return {"tasks": [], "notes": []}
                else:
                    print("No JSON found in response")
                    return {"tasks": [], "notes": []}
            else:
                print(f"API error: {response.text}")
                return {"tasks": [], "notes": []}
                
        except Exception as e:
            print(f"Error: {e}")
            return {"tasks": [], "notes": []}

ai_handler = SimpleAIHandler()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message', '')
    print(f"\n=== NEW MESSAGE ===")
    print(f"User: {user_message}")
    
    # Get AI response
    ai_response = ai_handler.debug_ai_communication(user_message)
    
    # Create tasks from AI response
    created_tasks = []
    for task_data in ai_response.get('tasks', []):
        task = {
            'id': len(tasks) + 1,
            'title': task_data.get('title', 'Untitled'),
            'description': task_data.get('description', ''),
            'due_time': task_data.get('due_time', ''),
            'language': 'ar' if any(char in '\u0600-\u06FF' for char in user_message) else 'en'
        }
        tasks.append(task)
        created_tasks.append(task)
    
    response_message = f"Created {len(created_tasks)} task(s)"
    
    return jsonify({
        'response': response_message,
        'tasks': tasks,
        'notes': notes
    })

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    return jsonify(tasks)

@app.route('/api/notes', methods=['GET'])
def get_notes():
    return jsonify(notes)

@app.route('/api/clear', methods=['POST'])
def clear_all():
    global tasks, notes
    tasks = []
    notes = []
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True, port=5000)