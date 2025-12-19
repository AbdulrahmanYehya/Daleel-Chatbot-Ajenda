https://docs.google.com/document/d/1WbwoOhzFtD879Kbb57600DjvEOUbSeX76u5ESuTYlZM/edit?usp=sharing

🚀 Intelligent Productivity AI Agent - Daleel AiGenda

A sophisticated bilingual (English/Arabic) AI-powered productivity assistant that helps you manage tasks, create notes, and plan your schedule through natural language conversations.

🌟 Features

🤖 AI-Powered Assistance

· Natural Language Processing: Convert spoken or typed requests into organized tasks and notes
· Bilingual Support: Full Arabic and English language support
· Smart Parsing: Automatically extracts times, dates, priorities, and categories from your requests
· Context Awareness: Remembers your preferences and patterns

📋 Productivity Tools

· Task Management: Create, schedule, and organize tasks with smart time parsing
· Note Taking: Generate research notes, project ideas, and personal memos
· Complex Planning: Break down complex requests into multiple organized tasks
· Smart Scheduling: Automatic time slot allocation and duration estimation

🎯 Advanced Capabilities

· Voice Input: Speech-to-text functionality for hands-free operation
· Image Processing: Extract tasks and information from images (planned)
· RAG System: 190+ training examples for accurate response generation
· Real-time Processing: Instant response with fallback systems

🏗️ Project Structure

```
Daleel-Chatbot-Ajenda/
├── backend/
│   ├── app.py                 # 🚀 Main Flask application
│   ├── ai_handler.py          # 🤖 Core AI processing logic
│   ├── rag_handler.py         # 📚 RAG system for intelligent responses
│   ├── rag_examples.py        # 🎓 Training examples database
│   ├── database.py            # 💾 Data storage and management
│   ├── config.py              # ⚙️ Application configuration
│   └── data.json              # 🗃️ Persistent data storage
├── static/
│   ├── style.css              # 🎨 Frontend styling
│   └── script.js              # ⚡ Frontend JavaScript
└── templates/
    └── index.html             # 🏠 Main web interface
```

🔧 Core Components

app.py - Flask Backend

· RESTful API endpoints for chat, tasks, and notes
· Session management for user interactions
· Error handling and logging system
· CORS support for cross-origin requests

ai_handler.py - AI Processing Engine

· Multimodal message processing (text, voice, image)
· Language detection (Arabic/English)
· Complex request parsing with time extraction
· Ollama integration for local AI processing
· Fallback systems for reliable operation

rag_handler.py - Retrieval-Augmented Generation

· TF-IDF vectorization for semantic similarity
· 190+ training examples across tasks and notes
· Context-aware prompting
· Intelligent fallback responses

database.py - Data Management

· JSON-based storage with thread safety
· Task and note CRUD operations
· Analytics tracking
· AI context persistence

🛠️ Technologies Used

Backend

· Flask - Web framework and API server
· Ollama - Local AI model inference (Mistral 7B)
· Scikit-learn - Machine learning for RAG system
· Requests - HTTP client for API calls

Frontend

· HTML5/CSS3 - Responsive web interface
· Vanilla JavaScript - Dynamic interactions
· Web Speech API - Voice recognition and synthesis

AI/ML

· Mistral 7B - Primary language model
· TF-IDF Vectorization - Semantic similarity matching
· Cosine Similarity - Example retrieval
· Regex Parsing - Time and entity extraction

🚀 Quick Start

Prerequisites

· Python 3.8+
· Ollama (with Mistral 7B model)
· Modern web browser

Installation

1. Clone the repository
   ```bash
   git clone https://github.com/yourusername/Daleel-Chatbot-Ajenda.git
   cd Daleel-Chatbot-Ajenda/backend
   ```
2. Install Python dependencies
   ```bash
   pip install flask requests scikit-learn numpy flask-cors
   ```
3. Set up Ollama
   ```bash
   ollama pull mistral:7b-instruct-q4_K_M
   ollama serve
   ```
4. Start the application
   ```bash
   python app.py
   ```
5. Open your browser
   ```
   http://localhost:5000
   ```

💡 Usage Examples

Task Creation

· English: "Create morning routine: exercise 7am, meditation 7:30, work 8am"
· Arabic: "أنشئ روتين صباحي: تمارين 7 صباحاً، تأمل 7:30، عمل 8 صباحاً"

Note Taking

· English: "Research artificial intelligence basics"
· Arabic: "ابحث عن أساسيات الذكاء الاصطناعي"

Complex Planning

· English: "Schedule meetings for tomorrow: 10am team meeting, 2pm client call"
· Arabic: "جدول اجتماعات غداً: فريق العمل 10 صباحاً، اتصال عميل 2 عصراً"

🎯 Key Features in Action

Smart Task Parsing

```python
# Input: "Create morning routine: exercise 7am, meditation 7:30, work 8am"
# Output: 3 separate tasks with extracted times and categories
- Exercise (7:00, Health)
- Meditation (7:30, Health) 
- Work (8:00, Work)
```

Bilingual Intelligence

```python
# Automatically detects language and responds appropriately
User: "اعمل مهمة للدراسة" → AI: "تم إنشاء مهمة الدراسة"
User: "Create study task" → AI: "Created study task"
```

Context Awareness

```python
# Maintains conversation context for follow-up requests
User: "Plan my week"
AI: Creates weekly schedule
User: "Add gym sessions on Monday and Wednesday"  
AI: Updates existing schedule with new tasks
```

🔄 API Endpoints

Endpoint Method Description
/api/chat POST Process user messages and return AI responses
/api/tasks GET Retrieve all tasks
/api/notes GET Retrieve all notes
/api/status GET Check AI model health status
/api/config GET Get language-specific configuration

🌍 Language Support

Arabic (اللغة العربية)

· Right-to-left interface support
· Arabic time parsing (٧ صباحاً → 07:00)
· Cultural context awareness
· Native keyword recognition

English

· Natural language understanding
· Time and date parsing
· Priority and category detection
· Complex sentence processing

🔮 Future Enhancements

· Mobile app development
· Calendar integration (Google Calendar, Outlook)
· Advanced analytics and productivity insights
· Multi-user support with accounts
· Plugin system for extended functionality
· Offline mode with local AI processing
· Export capabilities (PDF, CSV, iCal)


---

<div align="center">Built with ❤️ for the Arabic-speaking community and productivity enthusiasts worldwide

Making AI-assisted productivity accessible to everyone, in their native language

</div>
