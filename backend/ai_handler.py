import requests
import json
import re
import time
import random
import base64
import io
import os
from datetime import datetime, timedelta
from rag_handler import EnhancedRAGHandler
import logging
from functools import lru_cache
import hashlib

class EnhancedAIHandler:
    def __init__(self):
        self.ollama_url = "http://localhost:11434/api/generate"
        self.model_name = "mistral:7b-instruct-q4_K_M"
        self.multimodal_model = "mistral:7b-instruct-q4_K_M"  # For image understanding
        self.enhanced_rag = EnhancedRAGHandler()
        self.thinking_patterns = self._load_thinking_patterns()
        self.conversation_context = {}
        
        # Enhanced system prompt with multimodal support
        self.system_prompt = """<s>[INST] You are an advanced productivity assistant with multimodal capabilities. Respond with ONLY JSON.

CAPABILITIES:
- Create and schedule tasks with complex timeframes
- Generate detailed research notes with specified formats
- Understand and process images to extract tasks/notes
- Analyze voice inputs and convert to actions
- Provide context-aware suggestions
- Handle complex project planning

RESPONSE FORMAT:
{
  "tasks": [
    {
      "title": "task title in user's language",
      "description": "detailed task description",
      "due_date": "YYYY-MM-DD or date range",
      "due_time": "HH:MM (24h) or time range", 
      "duration": "estimated duration",
      "priority": "high | medium | low",
      "category": "work | study | personal | health | business | creative",
      "recurring": "daily | weekly | monthly | none",
      "dependencies": ["task_ids"],
      "tags": ["tag1", "tag2"]
    }
  ],
  "notes": [
    {
      "title": "note title",
      "content": "detailed, well-structured content",
      "category": "Research | Personal | Work | Ideas | Reference | Study | Creative",
      "format": "paragraphs | bullet_points | numbered | outline",
      "word_count": approximate_count,
      "paragraph_count": count,
      "sections": ["section1", "section2"],
      "tags": ["topic1", "topic2"]
    }
  ],
  "response_message": "natural, conversational response",
  "suggestions": ["relevant follow-up suggestions"],
  "requires_clarification": false,
  "clarification_questions": ["question1", "question2"],
  "context_updates": {"key": "value"}
}

ALWAYS RESPOND WITH VALID JSON. NO EXPLANATIONS. [/INST]"""

    def _load_thinking_patterns(self):
        return {
            'research': {
                'en': ["Researching the topic...", "Gathering information...", "Analyzing content..."],
                'ar': ["جاري البحث في الموضوع...", "جاري جمع المعلومات...", "جاري تحليل المحتوى..."]
            },
            'planning': {
                'en': ["Creating schedule...", "Planning tasks...", "Organizing timeline..."],
                'ar': ["جاري إنشاء الجدول...", "جاري تخطيط المهام...", "جاري تنظيم الجدول الزمني..."]
            },
            'tasks': {
                'en': ["Creating tasks...", "Setting priorities...", "Scheduling activities..."],
                'ar': ["جاري إنشاء المهام...", "جاري تحديد الأولويات...", "جاري جدولة الأنشطة..."]
            },
            'notes': {
                'en': ["Creating note...", "Researching content...", "Structuring information..."],
                'ar': ["جاري إنشاء الملاحظة...", "جاري البحث في المحتوى...", "جاري تنظيم المعلومات..."]
            },
            'image': {
                'en': ["Analyzing image...", "Extracting information from visual...", "Processing visual content..."],
                'ar': ["جاري تحليل الصورة...", "جاري استخراج المعلومات من الصورة...", "جاري معالجة المحتوى المرئي..."]
            },
            'voice': {
                'en': ["Processing voice command...", "Transcribing audio...", "Understanding speech..."],
                'ar': ["جاري معالجة الأمر الصوتي...", "جاري تحويل الصوت إلى نص...", "جاري فهم الكلام..."]
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
        if not text:
            return 'en'
        arabic_chars = len(re.findall(r'[\u0600-\u06FF]', text))
        return "ar" if arabic_chars > len(text) * 0.3 else "en"

    def get_thinking_message(self, user_message, language, message_type='text'):
        """Get appropriate thinking message based on content and type"""
        if message_type == 'image':
            category = 'image'
        elif message_type == 'voice':
            category = 'voice'
        else:
            text_lower = user_message.lower() if user_message else ''
            
            if any(word in text_lower for word in ['research', 'ابحث', 'بحث', 'study', 'دراسة']):
                category = 'research'
            elif any(word in text_lower for word in ['plan', 'schedule', 'خطط', 'جدول', 'week', 'أسبوع', 'month', 'شهر']):
                category = 'planning'
            elif any(word in text_lower for word in ['task', 'مهمة', 'مهام', 'todo', 'مطلوب']):
                category = 'tasks'
            elif any(word in text_lower for word in ['note', 'write', 'اكتب', 'ملاحظة', 'document', 'وثق']):
                category = 'notes'
            elif any(word in text_lower for word in ['complex', 'multiple', 'several', 'معقد', 'متعدد', 'عدة']):
                category = 'complex'
            else:
                category = 'general'
        
        messages = self.thinking_patterns[category][language]
        return random.choice(messages)

    @lru_cache(maxsize=100)
    def get_cached_response(self, message_hash):
        """Cache AI responses for performance"""
        return None  # Implementation would go here

    def process_multimodal_message(self, user_message, message_type='text', context_data=None, file_data=None, database=None):
        """Process messages of any type (text, voice, image)"""
        start_time = time.time()
        
        try:
            # Update conversation context
            self._update_context(context_data or {})
            
            if message_type == 'image' and file_data:
                return self._process_image_message(file_data, database)
            elif message_type == 'voice' and file_data:
                return self._process_voice_message(file_data, database)
            else:
                return self._process_text_message(user_message, database)
                
        except Exception as e:
            logging.error(f"Multimodal processing error: {e}")
            return self._create_error_response(str(e), self.detect_language(user_message))

    def _parse_complex_request(self, user_message, language):
        """Parse complex requests with multiple tasks and extract details"""
        tasks = []
        
        # Common patterns for complex requests
        if ':' in user_message and any(separator in user_message for separator in [',', '،', '\n']):
            # This looks like a complex request with multiple items
            try:
                # Split by colon to separate title from details
                if ':' in user_message:
                    parts = user_message.split(':', 1)
                    main_title = parts[0].strip()
                    details = parts[1].strip()
                else:
                    main_title = "Daily Tasks" if language == 'en' else "المهام اليومية"
                    details = user_message
                
                # Split details into individual tasks
                task_items = []
                for separator in [',', '،', '\n']:
                    if separator in details:
                        task_items = [item.strip() for item in details.split(separator) if item.strip()]
                        break
                
                if not task_items:
                    task_items = [details]
                
                # Parse each task item
                for item in task_items:
                    task_data = self._parse_task_item(item, language)
                    if task_data:
                        tasks.append(task_data)
                
                # If we couldn't parse specific tasks, create generic ones
                if not tasks:
                    for i, item in enumerate(task_items):
                        task = {
                            'title': f"Task {i+1}" if language == 'en' else f"مهمة {i+1}",
                            'description': item,
                            'due_date': datetime.now().strftime('%Y-%m-%d'),
                            'priority': 'medium',
                            'category': 'personal'
                        }
                        tasks.append(task)
                        
            except Exception as e:
                logging.error(f"Error parsing complex request: {e}")
        
        return tasks

    def _parse_task_item(self, item, language):
        """Parse individual task items to extract time, description, etc."""
        item_lower = item.lower()
        
        # Default task structure
        task = {
            'title': '',
            'description': item,
            'due_date': datetime.now().strftime('%Y-%m-%d'),
            'due_time': '',
            'duration': '',
            'priority': 'medium',
            'category': 'personal'
        }
        
        # Extract time patterns
        time_patterns = [
            r'(\d{1,2}:\d{2}\s*(?:am|pm)?)',
            r'(\d{1,2}\s*(?:am|pm))',
            r'(\d{1,2}\s*:\s*\d{2})',
            r'(\d{1,2}\s*ساعة)',
            r'(\d{1,2}\s*:\s*\d{2}\s*مساء)',
            r'(\d{1,2}\s*:\s*\d{2}\s*صباحاً)'
        ]
        
        for pattern in time_patterns:
            time_match = re.search(pattern, item, re.IGNORECASE)
            if time_match:
                task['due_time'] = self._normalize_time(time_match.group(1), language)
                break
        
        # Extract duration
        duration_patterns = [
            r'(\d+\s*(?:hour|hr|minute|min))',
            r'(\d+\s*(?:ساعة|دقيقة))'
        ]
        
        for pattern in duration_patterns:
            duration_match = re.search(pattern, item_lower)
            if duration_match:
                task['duration'] = duration_match.group(1)
                break
        
        # Determine category based on keywords
        category_keywords = {
            'work': ['work', 'job', 'project', 'meeting', 'client', 'عمل', 'وظيفة', 'مشروع', 'اجتماع'],
            'study': ['study', 'homework', 'research', 'learn', 'دراسة', 'واجب', 'بحث', 'تعلم'],
            'health': ['exercise', 'meditation', 'yoga', 'gym', 'workout', 'تمرين', 'تأمل', 'يوجا', 'رياضة'],
            'personal': ['read', 'cook', 'clean', 'shopping', 'قراءة', 'طبخ', 'تنظيف', 'تسوق']
        }
        
        for category, keywords in category_keywords.items():
            if any(keyword in item_lower for keyword in keywords):
                task['category'] = category
                break
        
        # Create a better title
        task['title'] = self._generate_task_title(item, task['category'], language)
        
        return task

    def _normalize_time(self, time_str, language):
        """Normalize time format to HH:MM"""
        try:
            # Remove spaces and convert to lowercase
            time_str = time_str.replace(' ', '').lower()
            
            # Handle Arabic times
            if language == 'ar':
                time_str = time_str.replace('ص', 'am').replace('م', 'pm')
                time_str = time_str.replace('صباحاً', 'am').replace('مساء', 'pm')
            
            # Parse time
            if 'am' in time_str or 'pm' in time_str:
                # 12-hour format
                time_obj = datetime.strptime(time_str, '%I:%M%p')
            else:
                # 24-hour format or just numbers
                if ':' in time_str:
                    time_obj = datetime.strptime(time_str, '%H:%M')
                else:
                    # Assume it's just hours, add :00
                    time_obj = datetime.strptime(time_str + ':00', '%H:%M')
            
            return time_obj.strftime('%H:%M')
        except:
            return time_str  # Return original if parsing fails

    def _generate_task_title(self, item, category, language):
        """Generate a meaningful title from the task item"""
        item_lower = item.lower()
        
        # Remove time and duration information for cleaner title
        clean_item = re.sub(r'\d{1,2}:\d{2}\s*(?:am|pm)?', '', item, flags=re.IGNORECASE)
        clean_item = re.sub(r'\d{1,2}\s*(?:am|pm)', '', clean_item, flags=re.IGNORECASE)
        clean_item = re.sub(r'\d+\s*(?:hour|hr|minute|min)', '', clean_item, flags=re.IGNORECASE)
        clean_item = re.sub(r'\d+\s*(?:ساعة|دقيقة)', '', clean_item)
        clean_item = clean_item.strip()
        
        # Use category-specific titles
        category_titles = {
            'work': {
                'en': ['Work', 'Work Session', 'Professional Task'],
                'ar': ['عمل', 'جلسة عمل', 'مهمة مهنية']
            },
            'study': {
                'en': ['Study', 'Learning', 'Research'],
                'ar': ['دراسة', 'تعلم', 'بحث']
            },
            'health': {
                'en': ['Exercise', 'Workout', 'Meditation'],
                'ar': ['تمرين', 'رياضة', 'تأمل']
            },
            'personal': {
                'en': ['Personal Task', 'Activity', 'Routine'],
                'ar': ['مهمة شخصية', 'نشاط', 'روتين']
            }
        }
        
        # If we have meaningful content left, use it as title
        if clean_item and len(clean_item) > 3:
            return clean_item.title() if language == 'en' else clean_item
        else:
            # Use category-based default title
            titles = category_titles.get(category, category_titles['personal'])
            import random
            return random.choice(titles[language])

    def _process_text_message(self, user_message, database):
        """Process standard text messages with smart parsing"""
        start_time = time.time()
        language = self.detect_language(user_message)
        
        logging.info(f"Processing: '{user_message}' in {language}")
        
        # Try to parse as complex request first
        parsed_tasks = self._parse_complex_request(user_message, language)
        
        if parsed_tasks:
            logging.info(f"Parsed {len(parsed_tasks)} tasks from complex request")
            
            # Create tasks in database
            created_tasks = []
            for task_data in parsed_tasks:
                try:
                    task = database.create_task(
                        title=task_data['title'],
                        description=task_data.get('description', ''),
                        due_date=task_data.get('due_date', datetime.now().strftime('%Y-%m-%d')),
                        due_time=task_data.get('due_time'),
                        duration=task_data.get('duration'),
                        priority=task_data.get('priority', 'medium'),
                        language=language,
                        category=task_data.get('category', 'personal')
                    )
                    created_tasks.append(task)
                except Exception as e:
                    logging.error(f"Error creating task: {e}")
            
            # Create response
            if language == 'ar':
                response_message = f"تم إنشاء {len(created_tasks)} مهام من طلبك المعقد"
            else:
                response_message = f"Created {len(created_tasks)} tasks from your complex request"
            
            response = {
                "response_message": response_message,
                "tasks": created_tasks,
                "notes": [],
                "processing_time": time.time() - start_time,
                "used_rag": False,
                "ai_metadata": {
                    'model': 'smart_parser',
                    'response_type': 'complex_parsing'
                }
            }
            
        else:
            # Fall back to RAG for simple requests
            logging.info("Using RAG fallback for simple request")
            rag_response = self.enhanced_rag.get_fallback_response(user_message, language)
            rag_response['processing_time'] = time.time() - start_time
            rag_response['used_rag'] = True
            
            # Create tasks and notes from RAG response
            self._create_database_entries(rag_response, database, language)
            response = rag_response
        
        return response

    def _process_image_message(self, image_file, database):
        """Process image messages to extract tasks/notes"""
        try:
            # Convert image to base64 for multimodal model
            image_data = base64.b64encode(image_file.read()).decode('utf-8')
            
            prompt = """Analyze this image and extract any tasks, schedules, notes, or actionable information. 
            Return ONLY JSON in this format:
            {
              "tasks": [{"title": "...", "description": "...", "due_date": "...", "priority": "..."}],
              "notes": [{"title": "...", "content": "...", "category": "..."}],
              "response_message": "Summary of what I found in the image"
            }"""
            
            payload = {
                "model": self.multimodal_model,
                "prompt": prompt,
                "images": [image_data],
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 400}
            }
            
            response = requests.post(self.ollama_url, json=payload, timeout=45)
            
            if response.status_code == 200:
                result = response.json()
                ai_response = result['response'].strip()
                
                parsed_response = self._parse_ai_response(ai_response, 'en')
                parsed_response['processing_time'] = time.time() - start_time
                parsed_response['ai_metadata'] = {
                    'model': self.multimodal_model,
                    'content_type': 'image',
                    'analysis_type': 'visual_extraction'
                }
                
                # Create database entries
                self._create_database_entries(parsed_response, database, 'en')
                
                return parsed_response
            else:
                return self._create_image_fallback_response()
                
        except Exception as e:
            logging.error(f"Image processing error: {e}")
            return self._create_image_fallback_response()

    def _process_voice_message(self, audio_file, database):
        """Process voice messages - placeholder for speech-to-text"""
        # In a real implementation, this would use Whisper or similar STT
        # For now, return a placeholder response
        return {
            "response_message": "Voice processing capability is available. Please provide the transcribed text for full functionality.",
            "tasks": [],
            "notes": [],
            "suggestions": ["Try typing your request for immediate processing"],
            "ai_metadata": {
                'feature': 'voice_processing_placeholder',
                'status': 'development'
            }
        }

    def _parse_ai_response(self, ai_text, language):
        """Enhanced AI response parsing with better error handling"""
        try:
            # Clean the response
            cleaned_text = re.sub(r'```json\s*|```\s*', '', ai_text)
            cleaned_text = re.sub(r'\[INST\].*?\[/INST\]', '', cleaned_text, flags=re.DOTALL)
            cleaned_text = cleaned_text.strip()
            
            # Find JSON object
            json_match = re.search(r'\{.*\}', cleaned_text, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                
                # Ensure required fields
                if 'response_message' not in parsed:
                    parsed['response_message'] = self._generate_natural_response(parsed, language)
                
                if 'tasks' not in parsed:
                    parsed['tasks'] = []
                
                if 'notes' not in parsed:
                    parsed['notes'] = []
                
                return parsed
        except Exception as e:
            logging.error(f"JSON parse error: {e}")
        
        # Fallback if parsing fails
        return self._create_fallback_response(ai_text, language, None)

    def _generate_natural_response(self, ai_response, language):
        """Generate sophisticated natural language responses"""
        task_count = len(ai_response.get('tasks', []))
        note_count = len(ai_response.get('notes', []))
        
        if language == 'ar':
            responses = [
                f"تم الإنشاء بنجاح! {task_count} مهمة و {note_count} ملاحظة جاهزة.",
                f"ممتاز! لقد أنشأت {task_count} مهام و {note_count} ملاحظات حسب طلبك.",
                f"جاهز للتطبيق! {task_count} مهمة و {note_count} ملاحظة في انتظارك.",
                f"تمت المعالجة: {task_count} مهام جديدة و {note_count} ملاحظات مضافة.",
                f"إنجاز رائع! {task_count} مهمة و {note_count} ملاحظة تم إنشاؤها بنجاح."
            ]
        else:
            responses = [
                f"Perfect! I've created {task_count} tasks and {note_count} notes for you.",
                f"Excellent! Your {task_count} tasks and {note_count} notes are ready.",
                f"All set! {task_count} tasks and {note_count} notes have been added.",
                f"Processing complete: {task_count} new tasks and {note_count} notes created.",
                f"Great work! Successfully created {task_count} tasks and {note_count} notes."
            ]
        
        return random.choice(responses)

    def _create_database_entries(self, ai_response, database, language):
        """Create tasks and notes in database from AI response"""
        if not database:
            return
        
        created_tasks = []
        created_notes = []
        
        # Create tasks
        for task_data in ai_response.get('tasks', []):
            try:
                task = database.create_task(
                    title=task_data.get('title', 'Task' if language == 'en' else 'مهمة'),
                    description=task_data.get('description', ''),
                    due_date=task_data.get('due_date'),
                    due_time=task_data.get('due_time'),
                    duration=task_data.get('duration'),
                    priority=task_data.get('priority', 'medium'),
                    language=language,
                    category=task_data.get('category', 'work'),
                    start_date=task_data.get('start_date'),
                    end_date=task_data.get('end_date')
                )
                created_tasks.append(task)
            except Exception as e:
                logging.error(f"Error creating task: {e}")
        
        # Create notes
        for note_data in ai_response.get('notes', []):
            try:
                note = database.create_note(
                    title=note_data.get('title', 'Note' if language == 'en' else 'ملاحظة'),
                    content=note_data.get('content', ''),
                    category=note_data.get('category', 'General'),
                    language=language,
                    word_count=note_data.get('word_count'),
                    paragraph_count=note_data.get('paragraph_count'),
                    character_count=note_data.get('character_count')
                )
                created_notes.append(note)
            except Exception as e:
                logging.error(f"Error creating note: {e}")
        
        ai_response['created_tasks'] = created_tasks
        ai_response['created_notes'] = created_notes

    def _update_context(self, new_context):
        """Update conversation context"""
        self.conversation_context.update(new_context)
        # Keep context manageable
        if len(self.conversation_context) > 10:
            # Remove oldest entries
            keys_to_remove = list(self.conversation_context.keys())[:5]
            for key in keys_to_remove:
                del self.conversation_context[key]

    def _update_context_from_response(self, ai_response, user_message):
        """Update context based on AI response"""
        context_updates = ai_response.get('context_updates', {})
        if context_updates:
            self._update_context(context_updates)

    def _create_fallback_response(self, user_message, language, database):
        """Enhanced fallback response"""
        response = self.enhanced_rag.get_fallback_response(user_message, language)
        response['ai_metadata'] = {
            'response_type': 'fallback',
            'reason': 'primary_ai_unavailable'
        }
        
        if database:
            self._create_database_entries(response, database, language)
        
        return response

    def _create_image_fallback_response(self):
        """Fallback for image processing failures"""
        return {
            "response_message": "I encountered an issue processing the image. Please try describing what you see in the image, and I'll help you create tasks or notes based on that.",
            "tasks": [],
            "notes": [],
            "suggestions": ["Try uploading a clearer image", "Describe the image content in text"],
            "ai_metadata": {
                'response_type': 'image_fallback',
                'status': 'processing_error'
            }
        }

    def _create_error_response(self, error_message, language):
        """Create error response"""
        if language == 'ar':
            message = "عذراً، حدث خطأ في المعالجة. يرجى المحاولة مرة أخرى."
        else:
            message = "Sorry, an error occurred during processing. Please try again."
        
        return {
            "response_message": message,
            "tasks": [],
            "notes": [],
            "suggestions": ["Check your connection and try again", "Simplify your request"],
            "ai_metadata": {
                'error': error_message,
                'response_type': 'error'
            }
        }

    def check_model_health(self):
        """Check if AI model is healthy"""
        try:
            start_time = time.time()
            test_prompt = "Respond with only: {'status': 'healthy'}"
            
            payload = {
                "model": self.model_name,
                "prompt": test_prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 10}
            }
            
            response = requests.post(self.ollama_url, json=payload, timeout=10)
            response_time = time.time() - start_time
            
            return {
                'status': 'healthy' if response.status_code == 200 else 'unhealthy',
                'response_time': round(response_time, 2),
                'model': self.model_name
            }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'response_time': 0,
                'model': self.model_name
            }

    def analyze_image(self, image_file, analysis_type, database):
        """Enhanced image analysis"""
        # This would be implemented with proper image processing
        return self._process_image_message(image_file, database)

    def process_voice_input(self, audio_file, language, database):
        """Enhanced voice input processing"""
        # Placeholder for STT implementation
        return self._process_voice_message(audio_file, database)

    def generate_suggestions(self, context, suggestion_type):
        """Generate AI-powered suggestions"""
        language = context.get('language', 'en')
        
        suggestions = {
            'en': [
                "Would you like me to create a detailed schedule for this?",
                "I can break this down into smaller tasks if you'd like",
                "Should I research this topic in more depth?",
                "Would you like me to set reminders for these tasks?",
                "I can help you prioritize these items by importance"
            ],
            'ar': [
                "هل تريد أن أنشئ جدولاً مفصلاً لهذا؟",
                "يمكنني تقسيم هذا إلى مهام أصغر إذا أردت",
                "هل يجب أن أبحث في هذا الموضوع بعمق أكبر؟",
                "هل تريد أن أحدد مواعيد تذكير لهذه المهام؟",
                "يمكنني مساعدتك في تحديد أولويات هذه العناصر حسب الأهمية"
            ]
        }
        
        return random.sample(suggestions.get(language, suggestions['en']), 3)

    def analyze_productivity_patterns(self, database):
        """Analyze productivity patterns using AI"""
        tasks = database.get_tasks()
        notes = database.get_notes()
        
        # Simple pattern analysis - could be enhanced with ML
        high_priority_count = len([t for t in tasks if t.get('priority') == 'high'])
        completed_count = len([t for t in tasks if t.get('completed', False)])
        total_tasks = len(tasks)
        
        completion_rate = (completed_count / total_tasks * 100) if total_tasks > 0 else 0
        
        return {
            'completion_rate': round(completion_rate, 1),
            'high_priority_ratio': round((high_priority_count / total_tasks * 100), 1) if total_tasks > 0 else 0,
            'total_notes': len(notes),
            'productivity_score': min(100, completion_rate + (high_priority_count * 10)),
            'recommendations': [
                "Try breaking large tasks into smaller subtasks",
                "Schedule important tasks during your most productive hours",
                "Use the notes feature to capture ideas and research"
            ]
        }