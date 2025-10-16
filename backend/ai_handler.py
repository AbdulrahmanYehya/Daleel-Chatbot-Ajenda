import requests
import json
import re
import time
import random
from datetime import datetime, timedelta

class AIHandler:
    def __init__(self):
        self.ollama_url = "http://localhost:11434/api/generate"
        self.model_name = "mistral:7b-instruct"  # Using Mistral 7B instead of Phi-3
        self.conversation_context = []
        self.thinking_patterns = self._load_thinking_patterns()
        
        # Enhanced system prompt for Mistral
        self.system_prompt = """You are an INTELLIGENT PRODUCTIVITY AI that excels at:
1. Complex task planning and scheduling
2. Detailed research and knowledge synthesis  
3. Project breakdown and milestone creation
4. Adaptive workflow optimization
5. Intelligent clarification and follow-up

RESPONSE FORMAT (STRICT JSON):
{
  "mode": "DIRECT_ACTION | CLARIFICATION_NEEDED | RESEARCH_PREVIEW | PROJECT_PLAN",
  "language": "en | ar",
  "message": "Intelligent response to user",
  "tasks": [
    {
      "title": "Descriptive task title",
      "description": "Detailed task description with context", 
      "due_date": "YYYY-MM-DD",
      "due_time": "HH:MM (24h format)",
      "duration": "X hours/minutes",
      "priority": "high | medium | low",
      "category": "work | study | personal | health | other"
    }
  ],
  "notes": [
    {
      "title": "Note title",
      "content": "Comprehensive, well-structured content",
      "category": "Research | Reference | Ideas | Project | Personal"
    }
  ],
  "research_preview": {
    "title": "Research title", 
    "content": "Detailed, structured research content",
    "category": "Research"
  },
  "missing_info": ["specific_field1", "specific_field2"],
  "suggestions": ["helpful_suggestion1", "helpful_suggestion2"]
}

INTELLIGENT BEHAVIORS:
- Ask SPECIFIC clarifying questions when information is incomplete
- Provide helpful suggestions and alternatives
- Break down complex requests into actionable steps
- Consider time management and productivity principles
- Create comprehensive, useful research notes

EXAMPLES:

User: "I'm overwhelmed with work"
{
  "mode": "CLARIFICATION_NEEDED",
  "language": "en",
  "message": "I understand feeling overwhelmed. Let me help you get organized. Could you tell me:\n1. What are your main work responsibilities?\n2. Do you have any urgent deadlines?\n3. How many hours do you typically work per day?",
  "tasks": [],
  "notes": [],
  "missing_info": ["work_responsibilities", "deadlines", "work_hours"],
  "suggestions": ["Consider time blocking", "Prioritize by urgency/importance", "Break large tasks into smaller steps"]
}

User: "ابحث لي عن الذكاء الاصطناعي في التعليم"
{
  "mode": "RESEARCH_PREVIEW", 
  "language": "ar",
  "message": "لقد قمت بالبحث عن الذكاء الاصطناعي في التعليم. هل تريد حفظ هذا البحث كملاحظة؟",
  "tasks": [],
  "notes": [],
  "research_preview": {
    "title": "الذكاء الاصطناعي في التعليم",
    "content": "مقدمة:\nالذكاء الاصطناعي يحدث ثورة في مجال التعليم من خلال...\n\nالتطبيقات الرئيسية:\n1. التخصيص والتكيف مع مستوى الطالب\n2. الأتمتة في التصحيح والتقييم\n3...",
    "category": "Research"
  },
  "suggestions": ["فكر في تطبيقات عملية في مؤسستك", "تابع أحدث الأبحاث في هذا المجال"]
}

User: "Plan my product launch for next month"
{
  "mode": "PROJECT_PLAN",
  "language": "en", 
  "message": "I've created a comprehensive product launch plan with 8 key tasks spread over 4 weeks.",
  "tasks": [
    {
      "title": "Finalize product messaging and positioning",
      "description": "Define core value proposition and key messaging for launch materials",
      "due_date": "2024-02-05",
      "due_time": "14:00",
      "duration": "3 hours",
      "priority": "high",
      "category": "work"
    },
    {
      "title": "Create launch marketing assets",
      "description": "Develop social media graphics, email templates, and press kit",
      "due_date": "2024-02-12", 
      "due_time": "10:00",
      "duration": "6 hours",
      "priority": "high",
      "category": "work"
    }
  ],
  "notes": [
    {
      "title": "Product Launch Strategy",
      "content": "Launch Timeline:\nWeek 1: Final prep\nWeek 2: Asset creation\nWeek 3: Internal training\nWeek 4: Public launch",
      "category": "Project"
    }
  ],
  "suggestions": ["Consider a soft launch to test messaging", "Prepare FAQ for customer support"]
}

User: "عندي ٣ امتحانات الشهر القادم"
{
  "mode": "CLARIFICATION_NEEDED",
  "language": "ar",
  "message": "حسناً، دعني أساعدك في التخطيط لاستعداد الامتحانات. أرجو إخباري:\n١. ما هي المواد الثلاث؟\n٢. متى مواعيد الامتحانات بالتحديد؟\n٣. كم ساعة يمكنك الدراسة يومياً؟",
  "tasks": [],
  "notes": [], 
  "missing_info": ["المواد", "مواعيد_الامتحانات", "ساعات_الدراسة_اليومية"],
  "suggestions": ["استخدم تقنية بومودورو", "راجع المواد الصعبة أولاً", "خذ فترات راحة منتظمة"]
}

ALWAYS respond with valid, well-structured JSON that demonstrates intelligent understanding of productivity principles."""

    def _load_thinking_patterns(self):
        return {
            'research': {
                'en': ["Researching the topic thoroughly...", "Gathering comprehensive information...", "Structuring knowledge systematically..."],
                'ar': ["جاري البحث المتعمق في الموضوع...", "جاري جمع المعلومات الشاملة...", "جاري تنظيم المعرفة بشكل منهجي..."]
            },
            'planning': {
                'en': ["Creating an optimized schedule...", "Breaking down complex requirements...", "Applying productivity frameworks..."],
                'ar': ["جاري إنشاء جدول مُحسّن...", "جاري تحليل المتطلبات المعقدة...", "جاري تطبيق أطر الإنتاجية..."]
            },
            'tasks': {
                'en': ["Designing actionable tasks...", "Prioritizing by importance and urgency...", "Setting realistic timeframes..."],
                'ar': ["جاري تصميم مهام قابلة للتنفيذ...", "جاري ترتيب الأولويات حسب الأهمية والعجلة...", "جاري تحديد إطارات زمنية واقعية..."]
            },
            'general': {
                'en': ["Analyzing your request intelligently...", "Processing complex requirements...", "Generating optimal solutions..."],
                'ar': ["جاري تحليل طلبك بذكاء...", "جاري معالجة المتطلبات المعقدة...", "جاري إنشاء الحلول المثلى..."]
            }
        }

    def detect_language(self, text):
        arabic_chars = len(re.findall(r'[\u0600-\u06FF]', text))
        return "ar" if arabic_chars > len(text) * 0.3 else "en"

    def get_thinking_message(self, user_message, language):
        """Get appropriate thinking message based on content"""
        text_lower = user_message.lower()
        
        if any(word in text_lower for word in ['research', 'ابحث', 'بحث', 'معلومات']):
            category = 'research'
        elif any(word in text_lower for word in ['plan', 'schedule', 'خطط', 'جدول']):
            category = 'planning'
        elif any(word in text_lower for word in ['task', 'مهمة', 'مهام', 'عمل']):
            category = 'tasks'
        else:
            category = 'general'
        
        messages = self.thinking_patterns[category][language]
        return random.choice(messages)

    def test_model(self):
        """Test if model is responsive"""
        start_time = time.time()
        try:
            response = requests.post(self.ollama_url, json={
                "model": self.model_name,
                "prompt": "Respond with only: OK",
                "stream": False
            }, timeout=10)
            
            return {
                "status": "online",
                "response_time": round(time.time() - start_time, 2)
            }
        except:
            return {"status": "offline"}

    def send_to_ai(self, user_message):
        """Send message to AI with enhanced error handling"""
        # Maintain conversation context (last 4 exchanges)
        self.conversation_context.append(f"User: {user_message}")
        if len(self.conversation_context) > 8:
            self.conversation_context = self.conversation_context[-8:]
        
        context_str = "\n".join(self.conversation_context[-4:])  # Last 2 exchanges
        full_prompt = f"SYSTEM: {self.system_prompt}\n\nCONVERSATION CONTEXT:\n{context_str}\n\nASSISTANT (JSON ONLY):"
        
        payload = {
            "model": self.model_name,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,  # Slightly higher for creativity
                "num_predict": 800,  # Longer responses for complex tasks
                "top_k": 50,
                "top_p": 0.9,
                "repeat_penalty": 1.1
            }
        }
        
        try:
            print(f"🧠 Processing: {user_message[:100]}...")
            start_time = time.time()
            
            response = requests.post(self.ollama_url, json=payload, timeout=45)
            processing_time = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                ai_response = result['response'].strip()
                print(f"✅ Response received in {processing_time:.2f}s")
                
                # Add to conversation context
                self.conversation_context.append(f"Assistant: {ai_response}")
                
                parsed_response = self.clean_json_response(ai_response)
                parsed_response['processing_time'] = processing_time
                return parsed_response
            else:
                print(f"❌ API error {response.status_code}")
                return self.create_intelligent_fallback(user_message)
                
        except requests.exceptions.Timeout:
            print("⏰ Request timeout")
            return self.create_timeout_response(user_message)
        except Exception as e:
            print(f"💥 Error: {e}")
            return self.create_intelligent_fallback(user_message)
    
    def clean_json_response(self, text):
        """Enhanced JSON cleaning with multiple fallback strategies"""
        # Strategy 1: Direct JSON parse
        try:
            return json.loads(text)
        except:
            pass
        
        # Strategy 2: Remove markdown and try again
        try:
            clean_text = re.sub(r'```json\s*|```\s*', '', text)
            clean_text = clean_text.strip()
            return json.loads(clean_text)
        except:
            pass
        
        # Strategy 3: Extract JSON with regex
        try:
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except:
            pass
        
        # Strategy 4: Manual JSON construction from text
        return self.create_intelligent_fallback(text)
    
    def create_intelligent_fallback(self, user_message):
        """Create intelligent fallback based on message content"""
        language = self.detect_language(user_message)
        text_lower = user_message.lower()
        
        # Analyze message intent
        if any(word in text_lower for word in ['research', 'ابحث', 'بحث']):
            return self.create_research_fallback(user_message, language)
        elif any(word in text_lower for word in ['task', 'مهمة', 'عمل']):
            return self.create_task_fallback(user_message, language)
        elif any(word in text_lower for word in ['plan', 'schedule', 'خطط', 'جدول']):
            return self.create_planning_fallback(user_message, language)
        else:
            return self.create_general_fallback(user_message, language)
    
    def create_research_fallback(self, user_message, language):
        """Create research-focused fallback"""
        topic = self.extract_topic(user_message)
        if language == 'ar':
            return {
                "mode": "RESEARCH_PREVIEW",
                "language": "ar",
                "message": "لقد واجهت بعض الصعوبة في معالجة طلبك. هل تريد أن أحاول البحث عن هذا الموضوع بطريقة مختلفة؟",
                "research_preview": {
                    "title": f"بحث عن {topic}",
                    "content": "يبدو أن هناك حاجة لمزيد من التفاصيل حول هذا الموضوع. يمكنني مساعدتك في البحث إذا وضحت:\n• الجوانب المحددة التي تهمك\n• مستوى العمق المطلوب\n• الاستخدام المقصود للمعلومات",
                    "category": "Research"
                },
                "suggestions": ["حدد جوانب محددة للبحث", "اختر مستوى التفصيل المناسب"]
            }
        else:
            return {
                "mode": "RESEARCH_PREVIEW",
                "language": "en", 
                "message": "I encountered some difficulty processing your request. Would you like me to try researching this topic differently?",
                "research_preview": {
                    "title": f"Research on {topic}",
                    "content": "It seems more details are needed about this topic. I can help research if you clarify:\n• Specific aspects you're interested in\n• The depth level required\n• Intended use of the information",
                    "category": "Research"
                },
                "suggestions": ["Specify particular aspects to research", "Choose appropriate detail level"]
            }
    
    def create_task_fallback(self, user_message, language):
        """Create task-focused fallback"""
        if language == 'ar':
            return {
                "mode": "CLARIFICATION_NEEDED",
                "language": "ar",
                "message": "أريد مساعدتك في إنشاء المهام بشكل أفضل. هل يمكنك تقديم:\n• وصف واضح للمهمة\n• الموعد النهائي إن وجد\n• الأولوية والمدة المتوقعة",
                "missing_info": ["وصف_المهمة", "الموعد_النهائي", "الأولوية"],
                "suggestions": ["استخدم أوقات محددة", "حدد الأولويات بوضوح"]
            }
        else:
            return {
                "mode": "CLARIFICATION_NEEDED",
                "language": "en",
                "message": "I want to help you create tasks better. Could you provide:\n• Clear task description\n• Deadline if any\n• Priority and expected duration", 
                "missing_info": ["task_description", "deadline", "priority"],
                "suggestions": ["Use specific times", "Define priorities clearly"]
            }
    
    def create_planning_fallback(self, user_message, language):
        """Create planning-focused fallback"""
        if language == 'ar':
            return {
                "mode": "CLARIFICATION_NEEDED", 
                "language": "ar",
                "message": "للمساعدة في التخطيط الفعال، أرجو توضيح:\n• الفترة الزمنية (يوم، أسبوع، شهر)\n• الأنشطة أو الأهداف الرئيسية\n• القيود أو الأولويات",
                "missing_info": ["الفترة_الزمنية", "الأهداف", "القيود"],
                "suggestions": ["ابدء بالأهداف الكبيرة ثم التفاصيل", "ضع في الاعتبار فترات الراحة"]
            }
        else:
            return {
                "mode": "CLARIFICATION_NEEDED",
                "language": "en", 
                "message": "To help with effective planning, please clarify:\n• Time period (day, week, month)\n• Main activities or goals\n• Constraints or priorities",
                "missing_info": ["time_period", "goals", "constraints"],
                "suggestions": ["Start with big goals then details", "Consider break times"]
            }
    
    def create_general_fallback(self, user_message, language):
        """Create general intelligent fallback"""
        if language == 'ar':
            return {
                "mode": "CLARIFICATION_NEEDED",
                "language": "ar", 
                "message": "لم أفهم طلبك بالكامل. هل يمكنك إعادة صياغته أو تقديم مزيد من التفاصيل؟",
                "missing_info": ["الهدف_الرئيسي", "التفاصيل_المطلوبة", "السياق"],
                "suggestions": ["كن محدداً في طلبك", "اذكر السياق والأهداف"]
            }
        else:
            return {
                "mode": "CLARIFICATION_NEEDED",
                "language": "en",
                "message": "I didn't fully understand your request. Could you rephrase or provide more details?",
                "missing_info": ["main_goal", "required_details", "context"],
                "suggestions": ["Be specific in your request", "Mention context and goals"]
            }
    
    def create_timeout_response(self, user_message):
        """Create response for timeout situations"""
        language = self.detect_language(user_message)
        
        if language == 'ar':
            return {
                "mode": "CLARIFICATION_NEEDED",
                "language": "ar",
                "message": "استغرقت المعالجة وقتاً طويلاً. دعنا نحاول بطريقة أبسط. ما هو الشيء الأكثر أهمية الذي تريد تحقيقه؟",
                "missing_info": ["الهدف_الأساسي"],
                "suggestions": ["حاول تقسيم الطلب إلى أجزاء أصغر", "ركز على العناصر الأكثر أهمية أولاً"]
            }
        else:
            return {
                "mode": "CLARIFICATION_NEEDED", 
                "language": "en",
                "message": "Processing took too long. Let's try a simpler approach. What's the most important thing you want to achieve?",
                "missing_info": ["primary_goal"],
                "suggestions": ["Try breaking the request into smaller parts", "Focus on most important elements first"]
            }
    
    def extract_topic(self, text):
        """Extract main topic from text for fallback responses"""
        # Simple topic extraction - can be enhanced
        words = text.split()
        if len(words) > 2:
            return ' '.join(words[:3]) + '...'
        return text[:20] + '...' if len(text) > 20 else text
    
    def process_message(self, user_message, db):
        """Main processing function with enhanced capabilities"""
        ai_response = self.send_to_ai(user_message)
        
        results = {
            'mode': ai_response.get('mode', 'DIRECT_ACTION'),
            'message': ai_response.get('message', ''),
            'language': ai_response.get('language', 'en'),
            'created_tasks': [],
            'created_notes': [],
            'research_preview': ai_response.get('research_preview'),
            'missing_info': ai_response.get('missing_info', []),
            'suggestions': ai_response.get('suggestions', []),
            'processing_time': ai_response.get('processing_time', 0)
        }
        
        # Create tasks and notes if in direct action mode
        if results['mode'] == 'DIRECT_ACTION':
            for task_data in ai_response.get('tasks', []):
                task = db.create_task(
                    title=task_data.get('title', 'Task' if results['language'] == 'en' else 'مهمة'),
                    description=task_data.get('description', ''),
                    due_date=task_data.get('due_date'),
                    due_time=task_data.get('due_time'),
                    duration=task_data.get('duration', '1 hour' if results['language'] == 'en' else '1 ساعة'),
                    priority=task_data.get('priority', 'medium'),
                    category=task_data.get('category', 'work' if results['language'] == 'en' else 'عمل'),
                    language=results['language']
                )
                results['created_tasks'].append(task)
            
            for note_data in ai_response.get('notes', []):
                note = db.create_note(
                    title=note_data.get('title', 'Note' if results['language'] == 'en' else 'ملاحظة'),
                    content=note_data.get('content', ''),
                    category=note_data.get('category', 'General'),
                    language=results['language']
                )
                results['created_notes'].append(note)
        
        print(f"🎯 Processing complete: {results['mode']}, Tasks: {len(results['created_tasks'])}, Notes: {len(results['created_notes'])}")
        return results