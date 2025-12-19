# Configuration settings
class Config:
    # Ollama settings
    OLLAMA_URL = "http://localhost:11434/api/generate"
    # UPDATED: Use the standard model name to avoid "Offline" errors
    MODEL_NAME = "mistral:7b-instruct-q4_K_M"
    
    # App settings
    DEBUG = True
    PORT = 5000
    
    # Language detection keywords (Removed 'Research' to avoid confusion)
    ARABIC_KEYWORDS = ['مهمة', 'ملاحظة', 'اعمل', 'أنشئ', 'غدا', 'الساعة', 'خطط', 'جدول']
    ENGLISH_KEYWORDS = ['task', 'note', 'create', 'make', 'tomorrow', 'at', 'plan', 'schedule']
    
    # Voice settings
    VOICE_ENABLED = True
    SPEECH_RATE = 0.9
    
    # UI Text Config
    # This helps the frontend know what placeholders to show
    UI_CONFIG = {
        'en': {
            'input_placeholder': 'Type "Buy milk tomorrow" or "Plan my day"...',
            'send_button': 'Send',
            'tasks_title': 'Tasks',
            'notes_title': 'Notes',
            'clear_button': 'Clear All Data',
            'examples_title': 'Try these examples:',
            'welcome': 'Hello! I am your offline AI assistant.\nI can help you manage tasks and notes.',
            # NEW: Dynamic Examples for English
            'examples': [
                "Plan my day from 9am to 5pm",
                "Remind me to call Mom at 5pm",
                "Create a note about project ideas",
                "Buy groceries tomorrow at 10am",
                "Schedule a meeting with Sarah on Monday",
                "Workout routine for 30 minutes",
                "Note: The meeting code is 1234",
                "Plan a weekend trip to London"
            ]
        },
        'ar': {
            'input_placeholder': 'اكتب "شراء حليب غداً" أو "خطط ليومي"...',
            'send_button': 'إرسال',
            'tasks_title': 'المهام',
            'notes_title': 'ملاحظات',
            'clear_button': 'مسح جميع البيانات',
            'examples_title': 'جرب هذه الأمثلة:',
            'welcome': 'أهلاً بك! أنا مساعدك الذكي (يعمل بدون إنترنت).\nيمكنني مساعدتك في إدارة المهام والملاحظات.',
            # NEW: Dynamic Examples for Arabic
            'examples': [
                "خطط ليومي من 9 صباحاً لـ 5 مساءً",
                "ذكرني بالاتصال بأمي الساعة 5",
                "أنشئ ملاحظة عن أفكار المشروع",
                "شراء خضروات غداً الساعة 10 صباحاً",
                "جدول اجتماع مع سارة يوم الإثنين",
                "تمرين رياضي لمدة 30 دقيقة",
                "ملاحظة: كود الاجتماع هو 1234",
                "خطة لعطلة نهاية الأسبوع"
            ]
        }
    }