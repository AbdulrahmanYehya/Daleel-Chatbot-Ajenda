import requests
import json
import re
import time
import random
import logging
import base64
from functools import lru_cache
from datetime import datetime, timedelta
# Ensure rapidfuzz is installed: pip install rapidfuzz
from rapidfuzz import fuzz
from rag_handler import EnhancedRAGHandler
from nlp_handler import LocalSummarizer

# Helper for Arabic numeral conversion
ARABIC_NUMERALS = {
    '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
    '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9'
}

def normalize_arabic_numerals(text):
    if not text: return text
    pattern = re.compile("|".join(ARABIC_NUMERALS.keys()))
    return pattern.sub(lambda m: ARABIC_NUMERALS[m.group()], text)

class EnhancedAIHandler:
    def __init__(self):
        self.ollama_url = "http://localhost:11434/api/generate"
        self.model_name = "mistral" 
        self.enhanced_rag = EnhancedRAGHandler()
        self.thinking_patterns = self._load_thinking_patterns()
        self.conversation_context = {}
        self.summarizer = LocalSummarizer()
        logging.info(f"Initialized EnhancedAIHandler with model: {self.model_name}")

    def _load_thinking_patterns(self):
        return {
            'planning': { 'en': ["Scheduling...", "Planning..."], 'ar': ["جاري الجدول...", "تخطيط..."] },
            'tasks': { 'en': ["Creating task...", "Adding to list..."], 'ar': ["جاري إضافة المهمة...", "إنشاء..."] },
            'notes': { 'en': ["Saving note...", "Writing down..."], 'ar': ["جاري حفظ الملاحظة...", "كتابة..."] },
            'voice': { 'en': ["Listening...", "Processing..."], 'ar': ["استمع...", "معالجة..."] },
            'update': { 'en': ["Updating...", "Modifying..."], 'ar': ["تحديث...", "تعديل..."] },
            'delete': { 'en': ["Deleting...", "Removing..."], 'ar': ["حذف...", "إزالة..."] },
            'general': { 'en': ["Working...", "Processing..."], 'ar': ["جاري العمل...", "معالجة..."] }
        }

    @lru_cache(maxsize=128)
    def detect_language(self, text):
        if not text: return 'en'
        arabic_chars = len(re.findall(r'[\u0600-\u06FF]', text))
        return "ar" if arabic_chars > len(text) * 0.3 else "en"

    def get_thinking_message(self, user_message, language, message_type='text', intent=None):
        if message_type == 'voice': return self.thinking_patterns['voice'][language][0]
        category = 'general'
        if intent:
             cat = intent.split('_')[0]
             if cat in self.thinking_patterns: category = cat
        return random.choice(self.thinking_patterns[category][language])

    def process_multimodal_message(self, user_message, message_type='text', context_data=None, database=None):
        start_time = time.time()
        language = self.detect_language(user_message)
        
        try:
            self._update_context(context_data or {})
            
            if message_type == 'document_text':
                 result = self._handle_document_summarization(user_message, database, language)
            else:
                 result = self._process_text_message(user_message, database, language)
            
            result['language'] = language
            result['processing_time'] = round(time.time() - start_time, 2)
            return result
            
        except Exception as e:
            logging.error(f"Processing error: {e}", exc_info=True)
            return self._create_error_response(str(e), language)

    def _detect_intent(self, user_message, language):
        text = user_message.lower()
        words = text.split()
        
        def check_fuzzy(keywords, threshold=85):
            for word in words:
                for key in keywords:
                    if fuzz.ratio(word, key) > threshold:
                        return True
            return False

        if check_fuzzy(['summarize', 'summary', 'digest', 'lakhis', 'تلخيص', 'لخص']):
            return 'summarize_text'

        if check_fuzzy(['delete', 'remove', 'cancel', 'احذف', 'إلغاء', 'امسح', 'شطب']):
            return 'delete_item'
        
        if check_fuzzy(['update', 'change', 'modify', 'edit', 'تعديل', 'غير', 'تغيير', 'عدل']):
            return 'update_item'

        if check_fuzzy(['note', 'ملاحظة']):
             return 'generate_note'

        # Heuristic for planning/tasks
        has_time = re.search(r'\d{1,2}(?::\d{2})?', text) or 'tomorrow' in text or 'غدا' in text
        if has_time and len(words) > 2:
             return 'create_task'

        return 'create_task'

    def _process_text_message(self, user_message, database, language):
        intent = self._detect_intent(user_message, language)
        logging.info(f"Processing Intent: {intent}")

        if intent == 'summarize_text':
             clean_text = re.sub(r'^(summarize|lakhis|لخص|تلخيص)\s+(this|that|text)?', '', user_message, flags=re.IGNORECASE)
             return self._handle_document_summarization(clean_text, database, language)

        if intent == 'delete_item':
            return self._handle_delete_request(user_message, database, language)

        elif intent == 'update_item':
            return self._handle_update_request(user_message, database, language)

        elif intent == 'generate_note':
             clean_content = re.sub(r'(create|write|make|a|note|for|about|أنشئ|اكتب|ملاحظة|عن|بخصوص)', '', user_message, flags=re.IGNORECASE).strip()
             if not clean_content: clean_content = user_message
             
             # Smart Title Extraction
             lines = clean_content.split('\n')
             title = lines[0][:40] + "..." if len(lines[0]) > 40 else lines[0]
             
             note = database.create_note(title=title, content=clean_content, language=language)
             msg = "Note saved." if language=='en' else "تم حفظ الملاحظة"
             return {"response_message": msg, "notes": [note], "tasks": []}

        elif intent == 'create_task':
            parsed_tasks = self._parse_complex_request(user_message, language)
            if parsed_tasks:
                created_items = self._create_database_entries({"tasks": parsed_tasks}, database, language)
                response_msg = f"Task created." if language == 'en' else f"تم إنشاء المهمة."
                return {
                    "response_message": response_msg,
                    "tasks": created_items['tasks'],
                    "notes": [],
                    "ai_metadata": {'response_type': 'smart_parser'}
                }
            
            rag_response = self.enhanced_rag.get_fallback_response(user_message, language)
            if rag_response.get('tasks') or rag_response.get('notes'):
                self._create_database_entries(rag_response, database, language)
                return rag_response

        return self._ask_clarification(user_message, language)

    def _handle_document_summarization(self, text, database, language):
        summary, title = self.summarizer.summarize(text)
        note = database.create_note(title=f"Summary: {title}", content=summary, category="Documents", language=language)
        msg = "I've summarized the document." if language == 'en' else "تم تلخيص المستند."
        return {"response_message": msg, "tasks": [], "notes": [note]}

    def _handle_delete_request(self, user_message, database, language):
        ignore_words = ['delete', 'remove', 'cancel', 'task', 'note', 'the', 'my', 'احذف', 'إلغاء', 'امسح', 'مهمة', 'ملاحظة', 'ال', 'عن', 'شطب']
        pattern = re.compile('|'.join(map(re.escape, ignore_words)), re.IGNORECASE)
        keyword = pattern.sub('', user_message).strip()
        
        if not keyword: return self._ask_clarification(user_message, language, "delete_item")
        
        tasks = database.get_tasks()
        notes = database.get_notes()
        target_id, target_type, target_title = None, None, ""

        search_key = keyword
        if language == 'ar' and search_key.startswith('ال'): search_key = search_key[2:]

        for t in tasks:
            if search_key.lower() in t['title'].lower():
                target_id = t['id']; target_type = 'task'; target_title = t['title']; break
        
        if not target_id:
            for n in notes:
                if search_key.lower() in n['title'].lower():
                    target_id = n['id']; target_type = 'note'; target_title = n['title']; break
        
        if target_id:
            if target_type == 'task': database.delete_task(target_id)
            else: database.delete_note(target_id)
            msg = f"Deleted {target_type}: {target_title}" if language == 'en' else f"تم حذف {target_title}"
            return {"response_message": msg, "tasks": [], "notes": [], "ai_metadata": {'response_type': 'delete'}}

        return self._ask_clarification(user_message, language, "delete_not_found")

    def _handle_update_request(self, user_message, database, language):
        # Basic update logic - can be expanded
        return {"response_message": "Update logic processed", "tasks": [], "notes": []}

    def _extract_date_and_clean(self, text):
        text_lower = text.lower()
        today = datetime.now()
        target_date = None
        
        days = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3, 'friday': 4, 'saturday': 5, 'sunday': 6,
            'الاثنين': 0, 'الثلاثاء': 1, 'الاربعاء': 2, 'الخميس': 3, 'الجمعة': 4, 'السبت': 5, 'الاحد': 6
        }
        
        found_day = next((day for day in days if day in text_lower), None)

        if found_day:
            target_idx = days[found_day]
            current_weekday = today.weekday()
            days_ahead = (target_idx - current_weekday + 7) % 7
            if days_ahead == 0: days_ahead = 7
            target_date = (today + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
            text = re.sub(r'(?:on |next |by |for |في |يوم |القادم )?' + found_day + r'(?: next)?', '', text, flags=re.IGNORECASE)
            
        elif 'tomorrow' in text_lower or 'غدا' in text_lower:
             target_date = (today + timedelta(days=1)).strftime('%Y-%m-%d')
             text = re.sub(r'(?:on |for )?(tomorrow|غدا)', '', text, flags=re.IGNORECASE)

        return target_date, text

    def _extract_time_and_clean(self, text, language):
        pattern = r'(?:at |around |by |الساعة |في تمام )?(\d{1,2}(?::\d{2})?\s*(?:am|pm| ص| م)?)'
        match = re.search(pattern, text, re.IGNORECASE)
        found_time = None
        if match:
            raw_time = match.group(1)
            if any(x in raw_time.lower() for x in ['am', 'pm', ':', 'ص', 'م']) or (raw_time.isdigit() and int(raw_time) <= 12):
                found_time = self._normalize_time(raw_time, language)
                if found_time:
                    text = text.replace(match.group(0), '')
        return found_time, text

    def _smart_extract_title_desc(self, text, language):
        """Intelligently separates Title from Description."""
        text = text.strip(' ,.-:')
        punc_match = re.search(r'(\s+[:\-]\s+)', text)
        if punc_match:
            split_idx = punc_match.start()
            return text[:split_idx].strip(), text[punc_match.end():].strip()

        splitters = [' for ', ' about ', ' regarding ', ' with ', ' details ', ' لـ ', ' عن ', ' بخصوص ', ' مع ']
        for splitter in splitters:
            idx = text.lower().find(splitter)
            if idx > 8: 
                return text[:idx].strip(), text[idx:].strip()

        words = text.split()
        if len(words) > 8:
            return ' '.join(words[:6]) + "...", text
        return text, ""

    def _parse_complex_request(self, user_message, language):
        tasks = []
        user_message = normalize_arabic_numerals(user_message)
        
        prefixes = [
            r'^(please )?(remind me to|create a? task (to|for|about)?|add a? task (to|for)?|schedule (a )?|task for)[\s:]*',
            r'^(رجاء |لو سمحت )?(ذكرني|أضف مهمة|أنشئ مهمة|جدول|مهمة لـ|مهمة)[\s:]*'
        ]
        clean_msg = user_message
        for p in prefixes:
            clean_msg = re.sub(p, '', clean_msg, flags=re.IGNORECASE).strip()

        items = re.split(r'[,،\n]', clean_msg)

        for item in items:
            item = item.strip()
            if len(item) < 2: continue
            
            task = {'priority': 'medium', 'category': 'personal', 'due_date': datetime.now().strftime('%Y-%m-%d')}
            task['due_time'], item = self._extract_time_and_clean(item, language)
            date_found, item = self._extract_date_and_clean(item)
            if date_found: task['due_date'] = date_found

            if 'high' in item.lower() or 'urgent' in item.lower() or 'عالية' in item:
                task['priority'] = 'high'
                item = re.sub(r'(high priority|urgent|أولوية عالية|هام)', '', item, flags=re.IGNORECASE).strip()

            # THE FIX: Ensure we use the Smart Extraction logic
            task['title'], task['description'] = self._smart_extract_title_desc(item, language)
            
            if language == 'en':
                task['title'] = task['title'].capitalize()
                if task['description']: task['description'] = task['description'].capitalize()

            tasks.append(task)
            
        return tasks

    def _normalize_time(self, time_str, language):
        try:
            time_str = time_str.replace(' ', '').lower()
            if 'am' in time_str or 'pm' in time_str:
                 dt = datetime.strptime(time_str, '%I:%M%p' if ':' in time_str else '%I%p')
                 return dt.strftime('%H:%M')
            elif ':' in time_str: return time_str
            else: return f"{int(time_str):02d}:00"
        except: return None

    def _create_database_entries(self, ai_response, database, language):
        created = {'tasks': [], 'notes': []}
        if not database: return created

        for t in ai_response.get('tasks', []):
            try:
                task = database.create_task(
                    title=t.get('title', 'Task'),
                    description=t.get('description', ''),
                    due_date=t.get('due_date'),
                    due_time=t.get('due_time'),
                    priority=t.get('priority', 'medium'),
                    language=language
                )
                created['tasks'].append(task)
            except Exception as e: logging.error(f"DB Error: {e}")
        
        for n in ai_response.get('notes', []):
            try:
                note = database.create_note(
                    title=n.get('title', 'Note'),
                    content=n.get('content', ''),
                    category=n.get('category', 'General'),
                    language=language
                )
                created['notes'].append(note)
            except Exception as e: logging.error(f"DB Error: {e}")
            
        return created

    def _update_context(self, new_context):
        self.conversation_context.update(new_context)

    def _create_error_response(self, error_message, language):
        msg = "Error occurred." if language == 'en' else "حدث خطأ."
        return {"response_message": msg, "tasks": [], "notes": [], "ai_metadata": {'error': str(error_message)}}
    
    def check_model_health(self):
        return {'status': 'healthy', 'model': self.model_name}

    def _call_ollama(self, prompt, is_json_output_expected=True):
        # Legacy stub for OLLAMA calls if needed later
        return None

    def _ask_clarification(self, msg, lang, type=None):
         return {"response_message": "Can you clarify?" if lang=='en' else "ممكن توضيح؟", "tasks":[]}