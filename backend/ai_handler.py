import requests
import json
import re
import time
import random
import base64
import os
from datetime import datetime, timedelta
from rag_handler import EnhancedRAGHandler
import logging
from functools import lru_cache

# Helper for Arabic numeral conversion (Unchanged)
ARABIC_NUMERALS = {
    '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
    '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9'
}

def normalize_arabic_numerals(text):
    if not text:
        return text
    pattern = re.compile("|".join(ARABIC_NUMERALS.keys()))
    return pattern.sub(lambda m: ARABIC_NUMERALS[m.group()], text)

class EnhancedAIHandler:
    def __init__(self):
        self.ollama_url = "http://localhost:11434/api/generate"
        # Ensure your Ollama model supports JSON mode if available, otherwise rely on prompt structure.
        self.model_name = "mistral:7b-instruct-q4_K_M" 
        self.enhanced_rag = EnhancedRAGHandler()
        self.thinking_patterns = self._load_thinking_patterns()
        self.conversation_context = {}
        logging.info(f"Initialized EnhancedAIHandler with model: {self.model_name}")

    def _load_thinking_patterns(self):
        # (Unchanged from previous version)
        return {
            'planning': {
                'en': ["Creating schedule...", "Planning tasks...", "Organizing timeline..."],
                'ar': ["جاري إنشاء الجدول...", "جاري تخطيط المهام...", "جاري تنظيم الجدول الزمني..."]
            },
            'tasks': {
                'en': ["Creating tasks...", "Setting priorities...", "Scheduling activities..."],
                'ar': ["جاري إنشاء المهام...", "جاري تحديد الأولويات...", "جاري جدولة المهام..."]
            },
            'notes': {
                'en': ["Creating note...", "Structuring information...", "Generating content..."],
                'ar': ["جاري إنشاء الملاحظة...", "جاري تنظيم المعلومات...", "جاري إنشاء المحتوى..."]
            },
            'image': {
                'en': ["Analyzing image...", "Extracting information from visual...", "Processing visual content..."],
                'ar': ["جاري تحليل الصورة...", "جاري استخراج المعلومات من الصورة...", "جاري معالجة المحتوى المرئي..."]
            },
            'voice': {
                'en': ["Processing voice command...", "Transcribing audio...", "Understanding speech..."],
                'ar': ["جاري معالجة الأمر الصوتي...", "جاري تحويل الصوت إلى نص...", "جاري فهم الكلام..."]
            },
             'update': {
                'en': ["Updating item...", "Applying changes...", "Modifying task/note..."],
                'ar': ["جاري تحديث العنصر...", "جاري تطبيق التغييرات...", "جاري تعديل المهمة/الملاحظة..."]
            },
            'delete': {
                'en': ["Deleting item...", "Removing task/note..."],
                'ar': ["جاري حذف العنصر...", "جاري إزالة المهمة/الملاحظة..."]
            },
            'complex': {
                'en': ["Processing complex request...", "Breaking down requirements...", "Creating detailed plan..."],
                'ar': ["جاري معالجة الطلب المعقد...", "جاري تحليل المتطلبات...", "جاري إنشاء خطة مفصلة..."]
            },
            'general': {
                'en': ["Processing your request...", "Analyzing...", "Working on it..."],
                'ar': ["جاري معالجة طلبك...", "جاري التحليل...", "جاري العمل عليه..."]
            }
        }

    def detect_language(self, text):
        # (Unchanged)
        if not text:
            return 'en'
        arabic_chars = len(re.findall(r'[\u0600-\u06FF]', text))
        return "ar" if arabic_chars > len(text) * 0.3 else "en"

    def get_thinking_message(self, user_message, language, message_type='text', intent=None):
        # Added intent parameter for more specific messages
        if message_type == 'image':
            category = 'image'
        elif message_type == 'voice':
            category = 'voice'
        elif intent:
             # Use detected intent if provided
             category = intent.split('_')[0] # e.g., 'create_task' -> 'create' -> maps roughly
             if category not in self.thinking_patterns:
                 category = 'general'
        else:
            # Fallback to keyword detection if intent not provided
            text_lower = user_message.lower() if user_message else ''
            if any(word in text_lower for word in ['plan', 'schedule', 'خطط', 'جدول']):
                category = 'planning'
            elif any(word in text_lower for word in ['update', 'change', 'modify', 'تعديل', 'غير']):
                 category = 'update'
            elif any(word in text_lower for word in ['delete', 'remove', 'cancel', 'احذف', 'إلغاء']):
                 category = 'delete'
            elif any(word in text_lower for word in ['task', 'مهمة', 'todo']):
                category = 'tasks'
            elif any(word in text_lower for word in ['note', 'اكتب', 'ملاحظة']):
                category = 'notes'
            elif any(word in text_lower for word in ['complex', 'multiple', 'معقد', 'متعدد']):
                category = 'complex'
            else:
                category = 'general'
        
        # Ensure category exists, default to general
        if category not in self.thinking_patterns:
             category = 'general'
             
        messages = self.thinking_patterns[category][language]
        return random.choice(messages)

    def process_multimodal_message(self, user_message, message_type='text', context_data=None, file_data=None, database=None):
        # (Structure unchanged, logic delegates to _process_text_message)
        start_time = time.time()
        language = self.detect_language(user_message)
        
        try:
            self._update_context(context_data or {})
            
            if message_type == 'image' and file_data:
                # Basic image processing stub - Ollama call removed for stability
                result = self._process_image_message_stub(file_data, database, language) 
            elif message_type == 'voice' and file_data:
                 # Placeholder remains
                result = self._process_voice_message(file_data, database)
            else:
                result = self._process_text_message(user_message, database, language)
            
            # Ensure language is in the result
            result['language'] = language
            result['processing_time'] = round(time.time() - start_time, 2)
            return result
                
        except Exception as e:
            logging.error(f"Multimodal processing error: {e}", exc_info=True)
            return self._create_error_response(str(e), language)

    def _detect_intent(self, user_message, language):
        """More specific intent detection."""
        text = user_message.lower()
        text_ar = user_message # Keep original for Arabic keywords

        # --- Order matters: Check for specific verbs first ---
        
        # Planning
        if any(k in text for k in ['plan', 'schedule', 'organize']) or any(k in text_ar for k in ['خطط', 'جدول', 'نظم']):
             # Check if it's planning tasks specifically
             if any(k in text for k in ['task', 'lecture', 'meeting']) or any(k in text_ar for k in ['مهمة', 'محاضرة', 'اجتماع']):
                 return 'plan_tasks'
             else:
                 # Could be general planning or requires clarification
                 return 'plan_general' 

        # Delete
        if any(k in text for k in ['delete', 'remove', 'cancel']) or any(k in text_ar for k in ['احذف', 'إلغاء', 'امسح']):
            return 'delete_item'
        
        # Update
        if any(k in text for k in ['update', 'change', 'modify', 'reschedule', 'add to']) or any(k in text_ar for k in ['تعديل', 'غير', 'تغيير', 'أضف إلى']):
            return 'update_item'

        # Note Creation (explicit)
        # Check if user wants content *generated* vs just saving provided text
        generate_note_keywords = ['write a note about', 'create a note explaining', 'generate a note on', 'اكتب ملاحظة عن', 'أنشئ ملاحظة تشرح']
        save_note_keywords = ['note:', 'reminder:', 'save this note:', 'ملاحظة:', 'تذكير:']
        
        if any(k in text for k in generate_note_keywords) or any(k in text_ar for k in ['اكتب ملاحظة عن', 'أنشئ ملاحظة تشرح']):
             return 'generate_note'
        if any(k in text for k in save_note_keywords) or any(k in text_ar for k in ['ملاحظة:', 'تذكير:']):
             return 'save_note'
        # Ambiguous note creation
        if any(k in text for k in ['note', 'ملاحظة']):
             return 'ambiguous_create_note'

        # Task Creation (explicit)
        if any(k in text for k in ['task', 'todo', 'reminder', 'schedule', 'add']) or any(k in text_ar for k in ['مهمة', 'واجب', 'تذكير', 'جدول', 'أضف']):
             # Check for ambiguity
             if text in ['create task', 'make task', 'task', 'اعمل مهمة', 'مهمة']:
                 return 'ambiguous_create_task'
             else:
                 return 'create_task'
                 
        # --- Fallbacks ---
        # If none of the above, but contains note keywords -> assume save note
        if 'note' in text or 'ملاحظة' in text_ar:
            return 'save_note'

        # Default: Assume task creation if not clearly anything else
        return 'create_task'

    def _call_ollama(self, prompt, is_json_output_expected=True):
        """Helper function to call Ollama model."""
        logging.info(f"Calling Ollama. Expect JSON: {is_json_output_expected}. Prompt:\n{prompt[:300]}...") # Log start
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            # Ollama JSON mode (if supported by the model version)
            # "format": "json" if is_json_output_expected else "", 
            "options": {"temperature": 0.2, "num_predict": 512} # Increased predict length
        }
        
        try:
            response = requests.post(self.ollama_url, json=payload, timeout=60) # Increased timeout
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            
            result = response.json()
            ai_response_text = result['response'].strip()
            logging.info(f"Ollama response received. Length: {len(ai_response_text)}")

            if is_json_output_expected:
                # Try to parse JSON robustly
                try:
                    # Clean potential markdown ```json ... ```
                    cleaned_text = re.sub(r'```json\s*|```\s*', '', ai_response_text, flags=re.IGNORECASE)
                    # Find the first valid JSON object
                    json_match = re.search(r'\{.*\}', cleaned_text, re.DOTALL)
                    if json_match:
                        parsed_json = json.loads(json_match.group())
                        logging.info("Successfully parsed JSON from Ollama response.")
                        return parsed_json
                    else:
                        logging.error("Ollama: No JSON object found in response.")
                        return None
                except json.JSONDecodeError as json_err:
                    logging.error(f"Ollama: Failed to parse JSON response: {json_err}\nResponse Text: {ai_response_text}")
                    return None
            else:
                 # Return raw text if JSON wasn't expected
                 return ai_response_text

        except requests.exceptions.RequestException as req_err:
            logging.error(f"Ollama API request failed: {req_err}")
            return None
        except Exception as e:
            logging.error(f"Error during Ollama call: {e}", exc_info=True)
            return None

    def _process_text_message(self, user_message, database, language):
        """Main logic router based on detected intent."""
        intent = self._detect_intent(user_message, language)
        logging.info(f"Processing: '{user_message}' | Lang: {language} | Intent: {intent}")

        thinking_msg = self.get_thinking_message(user_message, language, intent=intent)
        # We don't show thinking message here, app.py/script.js handles UI

        if intent == 'delete_item':
            return self._handle_delete_request(user_message, database, language)

        elif intent == 'update_item':
            return self._handle_update_request(user_message, database, language)

        elif intent == 'plan_tasks':
            return self._handle_planning_request(user_message, database, language)

        elif intent in ['ambiguous_create_task', 'ambiguous_create_note', 'plan_general']:
            return self._ask_clarification(user_message, language, intent)

        elif intent == 'generate_note':
             return self._handle_generate_note(user_message, database, language)

        elif intent == 'save_note':
             # Use RAG to structure the provided note content
             logging.info("Save note intent. Using RAG for structure.")
             rag_response = self.enhanced_rag.get_fallback_response(user_message, language, intent_type='notes')
             # Ensure RAG actually produced a note
             if not rag_response.get('notes'):
                 rag_response['notes'] = [{
                     'title': user_message[:30] + ('...' if len(user_message) > 30 else ''),
                     'content': user_message, # Save the whole message as content
                     'category': 'Personal'
                 }]
                 rag_response['tasks'] = [] # Clear any wrongly generated tasks
                 rag_response['response_message'] = "OK. I've saved that as a note." if language == 'en' else "حسناً. لقد حفظت ذلك كملاحظة."
             
             self._create_database_entries(rag_response, database, language)
             rag_response['used_rag'] = True
             rag_response['ai_metadata'] = {'response_type': 'rag_save_note'}
             return rag_response

        elif intent == 'create_task':
            # 1. Try Smart Parser for complex requests first
            parsed_tasks = self._parse_complex_request(user_message, language)
            if parsed_tasks:
                logging.info(f"Smart Parser successful: Found {len(parsed_tasks)} tasks.")
                created_items = self._create_database_entries({"tasks": parsed_tasks}, database, language)
                response_msg = f"OK, I've created {len(created_items)} tasks." if language == 'en' else f"حسناً، لقد أنشأت {len(created_items)} مهام."
                return {
                    "response_message": response_msg,
                    "tasks": created_items.get('tasks', []),
                    "notes": [],
                    "used_rag": False,
                    "ai_metadata": {'response_type': 'smart_parser'}
                }
            else:
                # 2. Fallback to RAG for simple tasks
                logging.info("Smart Parser failed or not applicable. Using RAG fallback.")
                rag_response = self.enhanced_rag.get_fallback_response(user_message, language, intent_type='tasks')
                # Basic validation for RAG response
                if rag_response.get('tasks') and rag_response['tasks'][0].get('title'):
                    self._create_database_entries(rag_response, database, language)
                    rag_response['used_rag'] = True
                    rag_response['ai_metadata'] = {'response_type': 'rag_fallback_task'}
                    return rag_response
                else:
                    # 3. If RAG also fails badly, ask for clarification
                    logging.warning("RAG fallback also failed to produce a valid task.")
                    return self._ask_clarification(user_message, language, 'create_task')
        
        # Default fallback if intent logic fails somehow
        logging.warning(f"Unhandled intent '{intent}'. Falling back to RAG.")
        rag_response = self.enhanced_rag.get_fallback_response(user_message, language, intent_type='auto')
        self._create_database_entries(rag_response, database, language)
        rag_response['used_rag'] = True
        rag_response['ai_metadata'] = {'response_type': 'rag_fallback_unhandled'}
        return rag_response

    def _handle_planning_request(self, user_message, database, language):
        """Use LLM to generate plans for complex requests."""
        logging.info("Handling planning request using Ollama.")
        
        # Try to extract parameters (basic for now)
        goal = user_message # Default to full message
        timeframe = "next few days" # Default
        
        # Example extraction: "Plan my next 3 days to study 10 lectures, 1 hour each"
        match_time = re.search(r'(next|coming)\s+(\d+)\s+(hour|day|week)', user_message, re.IGNORECASE)
        if match_time:
            timeframe = f"{match_time.group(2)} {match_time.group(3)}s"
        
        match_goal = re.search(r'(to|for)\s+(.*)', user_message, re.IGNORECASE)
        if match_goal:
             # Try to isolate the core goal
             possible_goal = match_goal.group(2).strip()
             # Remove timeframe part if present in goal
             if match_time:
                 possible_goal = possible_goal.replace(match_time.group(0), "").strip()
             if possible_goal:
                 goal = possible_goal
                 
        # Construct prompt for Ollama
        today = datetime.now().strftime('%Y-%m-%d')
        prompt = f"""<s>[INST] You are a scheduling assistant. Create a plan based on the user's request.
User Request: "{user_message}"
Extracted Goal: "{goal}"
Timeframe: "{timeframe}"
Current Date: "{today}"

Generate a list of tasks to fulfill the goal within the timeframe. Distribute tasks reasonably. Assume standard working/study hours (e.g., 9am-5pm, with breaks). If specific times or durations are mentioned (like '1 hour each'), use them.

Output ONLY a VALID JSON object containing a list of tasks in the following format. Do NOT include any explanations before or after the JSON.
{{
  "tasks": [
    {{
      "title": "Concise task title in {language}",
      "description": "Brief description related to '{goal}'",
      "due_date": "YYYY-MM-DD",
      "due_time": "HH:MM",
      "duration": "e.g., '1 hour'",
      "priority": "medium",
      "category": "study | work | personal" // Choose the most relevant
    }}
    // ... more tasks
  ]
}}
[/INST]"""

        ollama_result = self._call_ollama(prompt, is_json_output_expected=True)

        if ollama_result and 'tasks' in ollama_result and ollama_result['tasks']:
            logging.info(f"Ollama planning successful: Generated {len(ollama_result['tasks'])} tasks.")
            created_items = self._create_database_entries(ollama_result, database, language)
            response_msg = f"OK, I've planned out {len(created_items.get('tasks',[]))} tasks for you." if language == 'en' else f"حسناً، لقد خططت لك {len(created_items.get('tasks',[]))} مهام."
            return {
                "response_message": response_msg,
                "tasks": created_items.get('tasks', []),
                "notes": [],
                "used_rag": False,
                "ai_metadata": {'response_type': 'ollama_plan'}
            }
        else:
            logging.warning("Ollama planning failed or returned empty result. Falling back to RAG.")
            # Fallback to RAG if LLM fails
            rag_response = self.enhanced_rag.get_fallback_response(user_message, language, intent_type='tasks')
            self._create_database_entries(rag_response, database, language)
            rag_response['used_rag'] = True
            rag_response['ai_metadata'] = {'response_type': 'rag_fallback_plan'}
            return rag_response
            
    def _handle_generate_note(self, user_message, database, language):
        """Use LLM to generate note content based on user request."""
        logging.info("Handling note generation request using Ollama.")
        
        # Extract topic (simple extraction)
        topic = re.sub(r'(write|create|generate)\s+(a\s+)?note\s+(about|on|explaining)\s+', '', user_message, flags=re.IGNORECASE).strip()
        if not topic:
             topic = "User's Topic" # Fallback topic
             
        prompt = f"""<s>[INST] You are a note-taking assistant. Generate content for a note based on the user's request.
User Request: "{user_message}"
Extracted Topic: "{topic}"

Generate a concise and informative note about the topic. Structure it well if appropriate (e.g., bullet points, short paragraphs).

Output ONLY a VALID JSON object containing a single note in the following format. Do NOT include any explanations before or after the JSON.
{{
  "notes": [
    {{
      "title": "Appropriate title for '{topic}' in {language}",
      "content": "Generated note content here...",
      "category": "Study | Ideas | Reference | Personal" // Choose the most relevant
    }}
  ]
}}
[/INST]"""

        ollama_result = self._call_ollama(prompt, is_json_output_expected=True)

        if ollama_result and 'notes' in ollama_result and ollama_result['notes']:
            logging.info(f"Ollama note generation successful.")
            created_items = self._create_database_entries(ollama_result, database, language)
            response_msg = f"OK, I've created a note about '{topic}' for you." if language == 'en' else f"حسناً، لقد أنشأت ملاحظة حول '{topic}' لك."
            return {
                "response_message": response_msg,
                "tasks": [],
                "notes": created_items.get('notes', []),
                "used_rag": False,
                "ai_metadata": {'response_type': 'ollama_generate_note'}
            }
        else:
            logging.warning("Ollama note generation failed. Asking user to provide content.")
            # If LLM fails, ask user to provide content
            return self._ask_clarification(user_message, language, 'generate_note_failed')

    def _handle_delete_request(self, user_message, database, language):
        # (Unchanged from previous version)
        keyword = re.sub(r'(delete|remove|cancel|احذف|إلغاء|امسح)', '', user_message, flags=re.IGNORECASE).strip()
        keyword = re.sub(r'(my|the|task|note|ال|مهمة|ملاحظة)', '', keyword, flags=re.IGNORECASE).strip()
        
        if not keyword:
            return self._ask_clarification(user_message, language, "delete_item")
        
        tasks = database.find_tasks_by_keyword(keyword, language)
        notes = database.find_notes_by_keyword(keyword, language)
        
        if not tasks and not notes:
            msg = f"I couldn't find any tasks or notes matching '{keyword}'." if language == 'en' else f"لم أجد أي مهام أو ملاحظات تطابق '{keyword}'."
            return {"response_message": msg, "tasks": [], "notes": [], "ai_metadata": {'response_type': 'delete_not_found'}}
            
        if len(tasks) == 1 and not notes:
            task = tasks[0]
            database.delete_task(task['id'])
            msg = f"I've deleted the task: '{task['title']}'." if language == 'en' else f"لقد حذفت المهمة: '{task['title']}'."
            return {"response_message": msg, "tasks": [], "notes": [], "ai_metadata": {'response_type': 'delete_task_success'}}
            
        if len(notes) == 1 and not tasks:
            note = notes[0]
            database.delete_note(note['id'])
            msg = f"I've deleted the note: '{note['title']}'." if language == 'en' else f"لقد حذفت الملاحظة: '{note['title']}'."
            return {"response_message": msg, "tasks": [], "notes": [], "ai_metadata": {'response_type': 'delete_note_success'}}

        # Ambiguous case
        options = [f"Task: {t['title']} (ID: {t['id']})" for t in tasks] + [f"Note: {n['title']} (ID: {n['id']})" for n in notes]
        question = "Which one did you want to delete? Please specify by name or ID." if language == 'en' else "أي واحدة تريد حذفها؟ يرجى التحديد بالاسم أو الرقم التعريفي."
        return {
            "response_message": f"I found several items matching '{keyword}'.",
            "requires_clarification": True,
            "clarification_questions": [question] + options,
             "ai_metadata": {'response_type': 'delete_ambiguous'}
        }

    def _handle_update_request(self, user_message, database, language):
        """Parse update request and apply changes."""
        logging.info("Handling update request.")
        
        # 1. Try to identify the target item (keyword)
        target_keyword = None
        # Look for patterns like "update [task/note] called [name]" or "[name] [task/note]"
        match_target = re.search(r'(update|change|modify|reschedule|add to|تعديل|غير|تغيير|أضف إلى)\s+(?:the|my|ال)?\s*(task|note|meeting|item|مهمة|ملاحظة|اجتماع)?\s*[\'"]?([^\'"]+)[\'"]?', user_message, re.IGNORECASE)
        if match_target:
            target_keyword = match_target.group(3).strip()
            # Remove the update command part to isolate the change description
            change_description = user_message[match_target.end():].strip()
        else:
             # If no clear target, assume the first part of the string might be it (less reliable)
             parts = user_message.split(maxsplit=2)
             if len(parts) > 1:
                  target_keyword = parts[0] # Very basic guess
                  change_description = " ".join(parts[1:])
             else:
                 # Cannot determine target or change
                 return self._ask_clarification(user_message, language, "update_item_failed_parse")

        if not target_keyword:
             return self._ask_clarification(user_message, language, "update_item_failed_parse")

        logging.info(f"Update target: '{target_keyword}', Change: '{change_description}'")

        # 2. Find the item in the database
        tasks = database.find_tasks_by_keyword(target_keyword, language)
        notes = database.find_notes_by_keyword(target_keyword, language)
        
        target_item = None
        item_type = None

        if len(tasks) == 1 and not notes:
            target_item = tasks[0]
            item_type = 'task'
        elif len(notes) == 1 and not tasks:
            target_item = notes[0]
            item_type = 'note'
        elif not tasks and not notes:
             msg = f"I couldn't find any task or note matching '{target_keyword}' to update." if language == 'en' else f"لم أجد أي مهمة أو ملاحظة تطابق '{target_keyword}' لتحديثها."
             return {"response_message": msg, "tasks": [], "notes": [], "ai_metadata": {'response_type': 'update_not_found'}}
        else:
             # Ambiguous: multiple items found
             options = [f"Task: {t['title']} (ID: {t['id']})" for t in tasks] + [f"Note: {n['title']} (ID: {n['id']})" for n in notes]
             question = f"I found several items matching '{target_keyword}'. Which one do you want to update? Please specify by name or ID." if language == 'en' else f"وجدت عدة عناصر تطابق '{target_keyword}'. أي واحدة تريد تحديثها؟ يرجى التحديد بالاسم أو الرقم التعريفي."
             return {
                 "response_message": f"Multiple items found.",
                 "requires_clarification": True,
                 "clarification_questions": [question] + options,
                 "ai_metadata": {'response_type': 'update_ambiguous'}
             }

        # 3. Parse the change description
        updates = self._parse_change_description(change_description, item_type, language)

        if not updates:
             # Could not understand the change
             return self._ask_clarification(user_message, language, "update_item_failed_change_parse")

        # 4. Apply the update
        try:
            if item_type == 'task':
                updated_item = database.update_task(target_item['id'], updates)
                item_name = updated_item['title']
            else: # note
                updated_item = database.update_note(target_item['id'], updates)
                item_name = updated_item['title']
            
            msg = f"OK, I've updated '{item_name}'." if language == 'en' else f"حسناً، لقد قمت بتحديث '{item_name}'."
            return {"response_message": msg, "tasks": [updated_item] if item_type=='task' else [], "notes": [updated_item] if item_type=='note' else [], "ai_metadata": {'response_type': 'update_success'}}

        except Exception as e:
             logging.error(f"Error applying update: {e}", exc_info=True)
             return self._create_error_response(f"Failed to apply update: {e}", language)


    def _parse_change_description(self, change_desc, item_type, language):
        """Parse the update text (e.g., "time to 9pm", "priority to high")."""
        updates = {}
        change_desc_lower = change_desc.lower()

        # Task specific updates
        if item_type == 'task':
            # Time
            time_match = re.search(r'(?:to|at|for|الساعة|إلى)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?|الآن)', change_desc, re.IGNORECASE)
            if time_match:
                 time_val = time_match.group(1)
                 if time_val.lower() in ['now', 'الآن']:
                      updates['due_time'] = datetime.now().strftime('%H:%M')
                 else:
                      updates['due_time'] = self._normalize_time(time_val, language)
                 logging.info(f"Parsed update - Time: {updates['due_time']}")

            # Date
            # Add basic date parsing if needed (e.g., "date to tomorrow", "due date YYYY-MM-DD")
            if 'tomorrow' in change_desc_lower or 'غداً' in change_desc:
                 updates['due_date'] = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
                 logging.info(f"Parsed update - Date: {updates['due_date']}")

            # Priority
            if 'priority to high' in change_desc_lower or 'أولوية عالية' in change_desc or 'أولوية قصوى' in change_desc:
                 updates['priority'] = 'high'
                 logging.info(f"Parsed update - Priority: high")
            elif 'priority to medium' in change_desc_lower or 'أولوية متوسطة' in change_desc:
                 updates['priority'] = 'medium'
                 logging.info(f"Parsed update - Priority: medium")
            elif 'priority to low' in change_desc_lower or 'أولوية منخفضة' in change_desc:
                 updates['priority'] = 'low'
                 logging.info(f"Parsed update - Priority: low")

            # Description / Title (less common, could override existing)
            # Add description match? e.g., "add description 'details here'"

        # Note specific updates (e.g., content)
        if item_type == 'note':
             # Maybe add ability to append to content? "add to note: ..."
             if change_desc: # If there's remaining text, assume it's new content
                  updates['content'] = change_desc # Overwrite content for now
                  logging.info(f"Parsed update - Content updated")


        return updates


    def _ask_clarification(self, user_message, language, intent=None):
        """Return a clarification-seeking response."""
        response_message = ""
        question = ""

        # Default messages
        default_response_en = "I need a little more information to proceed."
        default_question_en = "Could you please provide more details about what you'd like me to do?"
        default_response_ar = "أحتاج إلى مزيد من المعلومات للمتابعة."
        default_question_ar = "هل يمكنك تقديم المزيد من التفاصيل حول ما تريد مني أن أفعله؟"

        if language == 'ar':
            response_message = default_response_ar
            if intent == 'delete_item':
                question = "ما هي المهمة أو الملاحظة المحددة التي تريد حذفها؟"
            elif intent == 'update_item':
                question = "أي مهمة أو ملاحظة تريد تعديلها، وما هو التغيير المحدد الذي تريد القيام به؟"
            elif intent == 'update_item_failed_parse':
                 question = "لم أتمكن من تحديد العنصر الذي تريد تحديثه أو التغيير المطلوب. هل يمكنك إعادة صياغة طلبك؟"
            elif intent == 'update_item_failed_change_parse':
                 question = "لقد وجدت العنصر، لكن لم أفهم التغيير الذي تريد القيام به. هل يمكنك توضيح التحديث؟"
            elif intent == 'plan_general':
                 question = "ما هو الهدف المحدد الذي تريد التخطيط له وما هو الإطار الزمني؟"
            elif intent == 'ambiguous_create_task':
                question = "بالتأكيد. ما هي تفاصيل المهمة التي تريد إنشاؤها (العنوان، الوقت، الأولوية)؟"
            elif intent == 'ambiguous_create_note':
                 question = "بالتأكيد. ما هو عنوان ومحتوى الملاحظة التي تريد إنشاؤها؟"
            elif intent == 'generate_note_failed':
                 question = "لم أتمكن من إنشاء محتوى الملاحظة. هل يمكنك توفير المحتوى بنفسك؟"
            else: # Default create / other
                question = default_question_ar
        else: # English
            response_message = default_response_en
            if intent == 'delete_item':
                question = "Which specific task or note did you want to delete?"
            elif intent == 'update_item':
                question = "Which task or note do you want to update, and what specific change should I make?"
            elif intent == 'update_item_failed_parse':
                 question = "I couldn't identify which item you want to update or the change requested. Could you rephrase your request?"
            elif intent == 'update_item_failed_change_parse':
                 question = "I found the item, but I didn't understand the change you want to make. Could you clarify the update?"
            elif intent == 'plan_general':
                 question = "What specific goal do you want to plan for, and what is the timeframe?"
            elif intent == 'ambiguous_create_task':
                question = "Sure. What are the details for the task (title, time, priority)?"
            elif intent == 'ambiguous_create_note':
                 question = "Sure. What is the title and content for the note?"
            elif intent == 'generate_note_failed':
                 question = "I wasn't able to generate the note content. Could you provide the content yourself?"
            else: # Default create / other
                question = default_question_en

        return {
            "response_message": response_message,
            "tasks": [],
            "notes": [],
            "requires_clarification": True,
            "clarification_questions": [question] if question else [],
            "ai_metadata": {'response_type': 'clarification_needed', 'intent_trigger': intent}
        }
        
    def _parse_complex_request(self, user_message, language):
        """Parse 'Title: item1, item2...' format."""
        # (Unchanged from previous version - this handles explicit lists)
        tasks = []
        user_message = normalize_arabic_numerals(user_message)
        
        # Pattern: "Schedule: exercise 7am, meeting 10am" or similar
        # Requires a keyword like Schedule/Plan/Tasks followed by ":"
        match = re.match(r'^(schedule|plan|tasks|مهام|جدول|خطط)\s*:(.*)', user_message, re.IGNORECASE | re.DOTALL)
        
        if match:
            details = match.group(2).strip()
            # Split details into individual tasks by comma, newline, or 'and'/'و'
            task_items = re.split(r'[,،\n]|(?:\s+and\s+)|(?:\s+و\s+)', details)
            task_items = [item.strip() for item in task_items if item.strip()]
            
            if not task_items:
                 return [] # No items found after the colon

            logging.info(f"Complex parser found {len(task_items)} items.")
            for item in task_items:
                task_data = self._parse_task_item(item, language)
                if task_data and task_data.get('title') != 'Task': # Avoid default empty tasks
                    tasks.append(task_data)
                else:
                    logging.warning(f"Skipping potentially invalid item from complex parse: '{item}'")

        return tasks


    def _parse_task_item(self, item, language):
        """Parse individual task items - Enhanced validation."""
        # (Largely unchanged, minor validation added)
        item_lower = item.lower()
        
        task = {
            'title': '',
            'description': item, # Start with full item as description
            'due_date': None, # Default to None, let DB handle if needed
            'due_time': None,
            'duration': None,
            'priority': 'medium', # Default priority
            'category': 'personal' # Default category
        }
        
        # --- Priority Detection ---
        if any(k in item_lower for k in ['high priority', 'أولوية عالية', 'أولوية قصوى']):
            task['priority'] = 'high'
        elif any(k in item_lower for k in ['low priority', 'أولوية منخفضة']):
            task['priority'] = 'low'
        # Explicitly check medium, otherwise default stands
        elif any(k in item_lower for k in ['medium priority', 'أولوية متوسطة']):
            task['priority'] = 'medium'

        # --- Time Detection ---
        time_patterns = [
            r'(\d{1,2}:\d{2}\s*(?:am|pm))',  # 4:30pm
            r'(\d{1,2}\s*(?:am|pm))',       # 7am
            r'(\d{1,2}\s*:\s*\d{2})',       # 14:30
            r'(?:at|at|الساعة)\s*(\d{1,2})',     # at 8, الساعة 8
        ]
        extracted_time_str = None
        for pattern in time_patterns:
            time_match = re.search(pattern, item, re.IGNORECASE)
            if time_match:
                extracted_time_str = time_match.group(1)
                task['due_time'] = self._normalize_time(extracted_time_str, language)
                break
        
        # --- Date Detection --- (Simple: tomorrow/غداً)
        if 'tomorrow' in item_lower or 'غداً' in item:
             task['due_date'] = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')


        # --- Duration Detection ---
        duration_patterns = [
            # English: 1 hour(s), 30 minute(s)/min, 2 hr/h
            r'(\d+\s*(?:hours?|hrs?|h))',     
            r'(\d+\s*(?:minutes?|mins?|m))', 
            # Arabic: ساعة/ساعات, دقيقة/دقائق
            r'(\d+\s*ساع(?:ة|ات))',          
            r'(\d+\s*دقيق(?:ة|ائق))'          
        ]
        extracted_duration_str = None
        for pattern in duration_patterns:
            duration_match = re.search(pattern, item_lower)
            if duration_match:
                extracted_duration_str = duration_match.group(1)
                task['duration'] = extracted_duration_str # Keep raw string like "1 hour"
                break
        
        # --- Category Detection (Improved) ---
        category_keywords = {
            'study': ['study', 'homework', 'exam', 'quiz', 'lecture', 'assignment', 'learn', 'course', 'دراسة', 'واجب', 'امتحان', 'محاضرة', 'مذاكرة', 'تعلم', 'دورة', 'رياضيات', 'فيزياء'],
            'work': ['work', 'job', 'project', 'meeting', 'client', 'email', 'report', 'presentation', 'call', 'office', 'عمل', 'وظيفة', 'مشروع', 'اجتماع', 'عميل', 'تقرير', 'بريد', 'مكالمة', 'مكتب'],
            'health': ['exercise', 'meditation', 'yoga', 'gym', 'workout', 'doctor', 'run', 'walk', 'appointment', 'تمرين', 'تأمل', 'يوجا', 'رياضة', 'جيم', 'طبيب', 'ركض', 'مشي', 'موعد'],
            'personal': ['read', 'cook', 'clean', 'shopping', 'dinner', 'lunch', 'breakfast', 'break', 'pay bills', 'groceries', 'قراءة', 'طبخ', 'تنظيف', 'تسوق', 'عشاء', 'غداء', 'فطور', 'استراحة', 'دفع فواتير', 'بقالة']
        }
        scores = {cat: 0 for cat in category_keywords}
        item_words = set(item_lower.split())
        for category, keywords in category_keywords.items():
            for keyword in keywords:
                if keyword in item_words or keyword in item_lower: # Check full keyword and substring
                    scores[category] += 1
        if any(scores.values()):
            task['category'] = max(scores, key=scores.get)
        
        # --- Title Generation (Crucial Fix) ---
        task['title'] = self._generate_task_title(item, task['category'], language, 
                                                 extracted_time_str, extracted_duration_str)
                                                 
        # --- Validation ---
        if not task['title'] or task['title'].lower() == 'task' or task['title'] == 'مهمة':
             logging.warning(f"Could not generate a meaningful title for item: '{item}'. Skipping task.")
             return None # Return None if title is invalid/generic

        # If description is same as title, clear description? Optional.
        # if task['description'] == task['title']:
        #     task['description'] = '' 

        return task

    def _normalize_time(self, time_str, language):
        # (Unchanged)
        try:
            time_str = time_str.replace(' ', '').lower()
            if language == 'ar':
                time_str = time_str.replace('ص', 'am').replace('م', 'pm')
                time_str = time_str.replace('صباحاً', 'am').replace('مساء', 'pm')
            
            if 'am' not in time_str and 'pm' not in time_str and ':' not in time_str:
                hour = int(re.sub(r'\D', '', time_str))
                # Simple AM/PM guess based on hour
                if 1 <= hour <= 6: hour += 12 # Assume PM
                # 7-11 assumed AM, 12 assumed PM (12:00)
                elif hour == 12: pass # Treat 12 as 12:00 (No change needed for strftime format)
                # >=13 assumed 24h
                
                # Format check needed here if hour > 12 after adjustment
                if hour > 23: hour = hour % 12 + 12 # Rough fix for >24h numbers if they occur
                
                return f"{hour:02d}:00"

            if 'am' in time_str or 'pm' in time_str:
                # Need to handle cases like '7am' -> '7:00am' before parsing
                if ':' not in time_str:
                     time_str = re.sub(r'(\d+)(am|pm)', r'\1:00\2', time_str)
                time_obj = datetime.strptime(time_str, '%I:%M%p')
            else: # Assume 24h format if no am/pm
                 if ':' not in time_str: # Handle '14' -> '14:00'
                      time_str += ':00'
                 time_obj = datetime.strptime(time_str, '%H:%M')
            
            return time_obj.strftime('%H:%M')
        except ValueError as e:
            logging.warning(f"Could not normalize time '{time_str}': {e}")
            return None # Return None if parsing fails


    def _generate_task_title(self, item, category, language, time_str=None, duration_str=None):
        """Generate a cleaner title by removing parsed details."""
        clean_item = item
        
        # Remove time if found
        if time_str:
            # Escape potential regex characters in the found time string
            escaped_time = re.escape(time_str)
            clean_item = re.sub(r'(?:at|at|الساعة)\s*' + escaped_time + r'\s*(am|pm)?', '', clean_item, flags=re.IGNORECASE)
            clean_item = re.sub(escaped_time + r'\s*(am|pm)?', '', clean_item, flags=re.IGNORECASE)

        # Remove duration if found
        if duration_str:
             escaped_duration = re.escape(duration_str)
             clean_item = re.sub(r'(?:for|لمدة)\s*' + escaped_duration, '', clean_item, flags=re.IGNORECASE)
             clean_item = re.sub(escaped_duration, '', clean_item, flags=re.IGNORECASE)

        # Remove priority
        clean_item = re.sub(r'(high|medium|low)\s*priority', '', clean_item, flags=re.IGNORECASE)
        clean_item = re.sub(r'أولوية\s*(عالية|متوسطة|منخفضة|قصوى)', '', clean_item)
        
        # Remove generic words
        generic_words_en = ['task', 'reminder', 'todo', 'schedule', 'plan', 'for', 'my', 'me']
        generic_words_ar = ['مهمة', 'تذكير', 'واجب', 'جدول', 'خطط', 'لي', 'ال']
        words = clean_item.split()
        
        if language == 'en':
             filtered_words = [w for w in words if w.lower() not in generic_words_en]
        else:
             filtered_words = [w for w in words if w not in generic_words_ar]
             
        clean_item = ' '.join(filtered_words).strip(' ,،-:')
        
        # Capitalize first letter if English
        if language == 'en' and clean_item:
             clean_item = clean_item[0].upper() + clean_item[1:]

        if clean_item and len(clean_item) > 2:
            return clean_item
        else:
            # Fallback title based on category if cleaning removes too much
            titles = {
                'work': {'en': 'Work Task', 'ar': 'مهمة عمل'},
                'study': {'en': 'Study Session', 'ar': 'جلسة دراسة'},
                'health': {'en': 'Health Activity', 'ar': 'نشاط صحي'},
                'personal': {'en': 'Personal Task', 'ar': 'مهمة شخصية'}
            }
            # Add original item in description if title is generic
            logging.warning(f"Using generic title for item: '{item}'")
            return titles.get(category, titles['personal'])[language]

    # --- Stubs & Fallbacks ---

    def _process_image_message_stub(self, image_file, database, language):
        # Placeholder - real implementation would use a multimodal model
        logging.warning("Image processing skipped (using stub).")
        return {
            "response_message": "Image received, but analysis is currently disabled. Please describe the image content." if language == 'en' else "تم استلام الصورة، لكن التحليل معطل حالياً. يرجى وصف محتوى الصورة.",
            "tasks": [],
            "notes": [],
            "ai_metadata": {'response_type': 'image_stub'}
        }

    def _process_voice_message(self, audio_file, database):
        # (Placeholder - Unchanged)
        return {
            "response_message": "Voice processing capability is available via the microphone button. Backend audio file processing is not yet implemented.",
            "tasks": [], "notes": [],
            "ai_metadata": {'feature': 'voice_processing_placeholder', 'status': 'development'}
        }

    def _create_database_entries(self, ai_response, database, language):
        """Create tasks/notes in DB. Returns dict {'tasks': [], 'notes': []} of CREATED items."""
        # (Enhanced logging and returns structure)
        created_items = {'tasks': [], 'notes': []}
        if not database:
            logging.error("Database object is None, cannot save items.")
            return created_items

        for task_data in ai_response.get('tasks', []):
            try:
                # Basic validation before creation
                if not task_data.get('title'):
                     logging.warning(f"Skipping task creation due to missing title: {task_data}")
                     continue
                task = database.create_task(
                    title=task_data.get('title'),
                    description=task_data.get('description', ''),
                    due_date=task_data.get('due_date'),
                    due_time=task_data.get('due_time'),
                    duration=task_data.get('duration'),
                    priority=task_data.get('priority', 'medium'),
                    language=language,
                    category=task_data.get('category', 'personal'),
                    start_date=task_data.get('start_date'),
                    end_date=task_data.get('end_date')
                )
                created_items['tasks'].append(task)
            except Exception as e:
                logging.error(f"Error creating task in DB: {e}", exc_info=True)
        
        for note_data in ai_response.get('notes', []):
            try:
                 # Basic validation
                 if not note_data.get('title') or not note_data.get('content'):
                      logging.warning(f"Skipping note creation due to missing title/content: {note_data}")
                      continue
                 note = database.create_note(
                    title=note_data.get('title'),
                    content=note_data.get('content', ''),
                    category=note_data.get('category', 'General'),
                    language=language,
                    word_count=note_data.get('word_count'),
                    paragraph_count=note_data.get('paragraph_count')
                 )
                 created_items['notes'].append(note)
            except Exception as e:
                logging.error(f"Error creating note in DB: {e}", exc_info=True)
        
        return created_items

    def _update_context(self, new_context):
        # (Unchanged)
        self.conversation_context.update(new_context)
        # Limit context size
        if len(self.conversation_context) > 10: 
            keys_to_remove = list(self.conversation_context.keys())[:5]
            for key in keys_to_remove:
                del self.conversation_context[key]

    def _create_error_response(self, error_message, language):
        # (Unchanged)
        if language == 'ar':
            message = "عذراً، حدث خطأ غير متوقع أثناء المعالجة. يرجى المحاولة مرة أخرى."
        else:
            message = "Sorry, an unexpected error occurred during processing. Please try again."
        
        return {
            "response_message": message,
            "tasks": [], "notes": [], "language": language,
            "ai_metadata": {'error': str(error_message), 'response_type': 'error'}
        }

    def check_model_health(self):
        # (Unchanged)
        try:
            start_time = time.time()
            test_prompt = "Respond ONLY with: ok" # Simpler health check prompt
            
            payload = { "model": self.model_name, "prompt": test_prompt, "stream": False, "options": {"num_predict": 5}}
            
            response = requests.post(self.ollama_url, json=payload, timeout=10)
            response_time = time.time() - start_time
            
            is_healthy = response.status_code == 200 and 'ok' in response.json().get('response', '').lower()
            
            return {
                'status': 'healthy' if is_healthy else 'unhealthy',
                'response_time': round(response_time, 2),
                'model': self.model_name
            }
        except Exception as e:
             logging.error(f"Ollama health check failed: {e}")
             return { 'status': 'unhealthy', 'error': str(e), 'response_time': 0, 'model': self.model_name }

    # --- Stubs for FR-14 & FR-16 (As before) ---
    def generate_suggestions(self, context, suggestion_type='tasks'):
        logging.info("FR-14: Generating suggestions (stub).")
        # Needs implementation: Analyze context/DB to find related items
        return ["Suggestion: Consider linking Note A and Note B (related topics).", "Suggestion: Follow up on 'Project X Task' soon."]

    def analyze_productivity_patterns(self, database):
       # This logic is better placed directly using DB data via the /api/analytics endpoint
       logging.info("FR-16: analyze_productivity_patterns called (delegating to DB analytics).")
       # Return basic structure expected by old endpoint if called directly
       analytics = database.get_analytics()
       return {
            'total_tasks': analytics.get('total_tasks', 0),
            'completed_tasks': analytics.get('completed_tasks', 0),
            'completion_rate': f"{analytics.get('completed_tasks', 0) / analytics.get('total_tasks', 1) * 100:.0f}%",
            'focus_time_today': "N/A", # Needs calculation logic
            'most_productive_category': 'N/A' # Needs calculation logic
       }