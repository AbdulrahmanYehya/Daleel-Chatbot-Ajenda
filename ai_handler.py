import requests
import json
import re
from datetime import datetime, timedelta
from config import Config

class AIHandler:
    def __init__(self):
        self.ollama_url = Config.OLLAMA_URL
        self.model_name = Config.MODEL_NAME
        
        # Bilingual system prompt
        self.system_prompt = """
You are an advanced bilingual productivity assistant. You respond in the same language the user writes in (Arabic or English) and output structured JSON.

CRITICAL RULES:
1. Respond with ONLY valid JSON, no other text
2. Use the exact JSON structure provided
3. Handle multiple tasks/notes in one request
4. Match the user's language (Arabic/English) in your output
5. For research requests, create detailed, well-structured notes

RESPONSE FORMAT (ALWAYS USE THIS EXACT STRUCTURE):
{
  "intent": "create_tasks | create_notes | create_research | plan_day | unknown",
  "language": "ar | en",
  "tasks": [
    {
      "title": "Task title in user's language",
      "description": "Task description in user's language",
      "due_date": "YYYY-MM-DD",
      "due_time": "HH:MM",
      "priority": "low | medium | high"
    }
  ],
  "notes": [
    {
      "title": "Note title in user's language",
      "content": "Detailed content in user's language",
      "category": "Research | Personal | Work | Ideas"
    }
  ]
}

LANGUAGE DETECTION:
- If user writes in Arabic: set "language" to "ar" and use Arabic in titles/descriptions
- If user writes in English: set "language" to "en" and use English in titles/descriptions

TASK CREATION:
- Extract ALL tasks from the message
- Infer dates/times from context
- Set appropriate priorities

NOTE CREATION:
- For simple notes: capture the content
- For research: create comprehensive, organized information

RESEARCH EXAMPLES:
User: "ابحث لي عن الذكاء الاصطناعي"
→ Create detailed Arabic note about AI

User: "Research machine learning applications"
→ Create detailed English note about ML

MULTIPLE ITEMS EXAMPLES:
User: "اعمل مهمة للواجب الساعة 7 ومهمة للرياضيات غدا واكتب ملاحظة عن أفكار المشروع"
→ Creates 2 tasks (homework at 7pm, math tomorrow) + 1 note (project ideas)

User: "Create task for CS assignment at 7pm and also make a note about project ideas"
→ Creates 1 task (CS assignment) + 1 note (project ideas)

ALWAYS RESPOND WITH VALID JSON ONLY!
"""

    def detect_language(self, text):
        """Detect if text is Arabic or English"""
        arabic_chars = len(re.findall(r'[\u0600-\u06FF]', text))
        english_chars = len(re.findall(r'[a-zA-Z]', text))
        
        if arabic_chars > english_chars:
            return "ar"
        else:
            return "en"

    def parse_date_references(self, text, language):
        """Convert natural language dates to actual dates"""
        today = datetime.now()
        text_lower = text.lower()
        
        if language == "en":
            if 'tomorrow' in text_lower:
                return (today + timedelta(days=1)).strftime('%Y-%m-%d')
            elif 'today' in text_lower:
                return today.strftime('%Y-%m-%d')
            elif 'next week' in text_lower:
                return (today + timedelta(days=7)).strftime('%Y-%m-%d')
        elif language == "ar":
            if 'غدا' in text or 'غداً' in text:
                return (today + timedelta(days=1)).strftime('%Y-%m-%d')
            elif 'اليوم' in text:
                return today.strftime('%Y-%m-%d')
            elif 'الأسبوع القادم' in text:
                return (today + timedelta(days=7)).strftime('%Y-%m-%d')
        
        return today.strftime('%Y-%m-%d')

    def parse_time(self, text, language):
        """Extract time from text"""
        if language == "en":
            time_pattern = r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?'
            matches = re.findall(time_pattern, text.lower())
            
            if matches:
                hour, minute, period = matches[0]
                hour = int(hour)
                minute = int(minute) if minute else 0
                
                if period == 'pm' and hour < 12:
                    hour += 12
                elif period == 'am' and hour == 12:
                    hour = 0
                    
                return f"{hour:02d}:{minute:02d}"
        
        elif language == "ar":
            # Arabic time patterns like "الساعة 7" or "7 مساء"
            time_pattern = r'(\d{1,2})'
            matches = re.findall(time_pattern, text)
            
            if matches:
                hour = int(matches[0])
                # Simple conversion - you can enhance this
                if 'مساء' in text or 'ليل' in text and hour < 12:
                    hour += 12
                return f"{hour:02d}:00"
        
        return None

    def send_to_ai(self, user_message, detected_language):
        """Send message to Phi-3 model and get structured response"""
        
        # Add language context to prompt
        language_context = f"User is writing in {detected_language.upper()}. Respond in the same language."
        full_prompt = f"System: {self.system_prompt}\n\nAdditional: {language_context}\n\nUser: {user_message}\n\nAssistant:"
        
        payload = {
            "model": self.model_name,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "top_p": 0.9
            }
        }
        
        try:
            print(f"Sending to AI: {user_message[:100]}...")
            response = requests.post(self.ollama_url, json=payload, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                ai_response = result['response'].strip()
                print(f"Raw AI response: {ai_response}")
                
                # Clean the response
                ai_response = self.clean_json_response(ai_response)
                
                try:
                    parsed_response = json.loads(ai_response)
                    # Ensure language is set correctly
                    if 'language' not in parsed_response:
                        parsed_response['language'] = detected_language
                    return parsed_response
                except json.JSONDecodeError as e:
                    print(f"JSON parse error: {e}")
                    print(f"Raw AI response: {ai_response}")
                    return {
                        "intent": "unknown", 
                        "language": detected_language, 
                        "tasks": [], 
                        "notes": []
                    }
            else:
                print(f"Ollama API error: {response.status_code}")
                return {
                    "intent": "error", 
                    "language": detected_language, 
                    "tasks": [], 
                    "notes": []
                }
                
        except Exception as e:
            print(f"Error communicating with Ollama: {e}")
            return {
                "intent": "error", 
                "language": detected_language, 
                "tasks": [], 
                "notes": []
            }
    
    def clean_json_response(self, text):
        """Extract JSON from AI response"""
        # Remove any text before and after JSON
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            return json_match.group()
        
        # If no JSON found, return empty structure
        return '{"intent": "unknown", "tasks": [], "notes": []}'
    
    def process_message(self, user_message, db):
        """Main method to process user message"""
        # Detect language
        detected_language = self.detect_language(user_message)
        print(f"Detected language: {detected_language}")
        
        # Get structured response from AI
        ai_response = self.send_to_ai(user_message, detected_language)
        
        results = {
            'created_tasks': [],
            'created_notes': [],
            'intent': ai_response.get('intent', 'unknown'),
            'language': ai_response.get('language', detected_language)
        }
        
        # Create tasks from AI response
        for task_data in ai_response.get('tasks', []):
            task = db.create_task(
                title=task_data['title'],
                description=task_data.get('description', ''),
                due_date=task_data.get('due_date'),
                due_time=task_data.get('due_time'),
                priority=task_data.get('priority', 'medium'),
                language=results['language']
            )
            results['created_tasks'].append(task)
        
        # Create notes from AI response
        for note_data in ai_response.get('notes', []):
            note = db.create_note(
                title=note_data['title'],
                content=note_data['content'],
                category=note_data.get('category', 'General'),
                language=results['language']
            )
            results['created_notes'].append(note)
        
        return results