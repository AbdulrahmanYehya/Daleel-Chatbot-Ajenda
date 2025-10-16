# Configuration settings
class Config:
    # Ollama settings
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL_NAME = "phi3:3.7b"
    
    # App settings
    DEBUG = True
    PORT = 5000
    
    # Language detection keywords
    ARABIC_KEYWORDS = ['مهمة', 'ملاحظة', 'بحث', 'اعمل', 'أنشئ', 'غدا', 'الساعة']
    ENGLISH_KEYWORDS = ['task', 'note', 'research', 'create', 'make', 'tomorrow', 'at']