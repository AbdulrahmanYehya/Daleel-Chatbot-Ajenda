# Configuration settings
class Config:
    # Ollama settings
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL_NAME = "mistral:7b-instruct-q4_K_M"
    
    # App settings
    DEBUG = True
    PORT = 5000
    
    # Language detection keywords
    ARABIC_KEYWORDS = ['مهمة', 'ملاحظة', 'بحث', 'اعمل', 'أنشئ', 'غدا', 'الساعة', 'خطط', 'جدول']
    ENGLISH_KEYWORDS = ['task', 'note', 'research', 'create', 'make', 'tomorrow', 'at', 'plan', 'schedule']
    
    # Voice settings
    VOICE_ENABLED = True
    SPEECH_RATE = 0.9