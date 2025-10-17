let currentLanguage = 'en';
let examples = [];
let currentExampleIndex = 0;
let exampleInterval;
let isWaitingForConfirmation = false;
let currentMessageId = null;
let recognition = null;
let isListening = false;
let lastBotMessage = '';

// Initialize the application
async function initializeApp() {
    await checkModelStatus();
    await setLanguage('en');
    startExampleRotation();
    initializeVoiceRecognition();
    
    // Periodically check model status
    setInterval(checkModelStatus, 30000);
}

// Initialize voice recognition
function initializeVoiceRecognition() {
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = true;
        recognition.lang = currentLanguage === 'ar' ? 'ar-SA' : 'en-US';

        recognition.onstart = function() {
            isListening = true;
            updateVoiceUI(true);
        };

        recognition.onresult = function(event) {
            const transcript = Array.from(event.results)
                .map(result => result[0])
                .map(result => result.transcript)
                .join('');
            
            document.getElementById('messageInput').value = transcript;
        };

        recognition.onerror = function(event) {
            console.error('Speech recognition error:', event.error);
            updateVoiceUI(false);
        };

        recognition.onend = function() {
            isListening = false;
            updateVoiceUI(false);
        };
    } else {
        console.warn('Speech recognition not supported');
        document.getElementById('voiceButton').style.display = 'none';
    }
}

// Toggle voice recognition
function toggleVoiceRecognition() {
    if (!recognition) return;

    if (isListening) {
        recognition.stop();
    } else {
        recognition.start();
    }
}

// Update voice UI
function updateVoiceUI(listening) {
    const voiceButton = document.getElementById('voiceButton');
    const voiceStatus = document.getElementById('voiceStatus');
    const voiceStatusText = document.getElementById('voiceStatusText');
    
    if (listening) {
        voiceButton.classList.add('listening');
        voiceStatus.style.display = 'flex';
        voiceStatusText.textContent = currentLanguage === 'ar' ? 'جاري الاستماع...' : 'Listening...';
    } else {
        voiceButton.classList.remove('listening');
        voiceStatus.style.display = 'none';
    }
}

// Text-to-Speech
function speakText(text) {
    if ('speechSynthesis' in window) {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = currentLanguage === 'ar' ? 'ar-SA' : 'en-US';
        utterance.rate = 0.9;
        utterance.pitch = 1;
        
        speechSynthesis.speak(utterance);
    }
}

// Speak the last bot message
function speakLastMessage() {
    if (lastBotMessage) {
        speakText(lastBotMessage);
    }
}

// Check if AI model is online
async function checkModelStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        const statusIndicator = document.getElementById('statusIndicator');
        const modelStatus = document.getElementById('modelStatus');
        
        if (data.status === 'online') {
            statusIndicator.className = 'status-indicator online';
            modelStatus.textContent = `AI Model: Online (${data.response_time}s)`;
        } else {
            statusIndicator.className = 'status-indicator';
            modelStatus.textContent = 'AI Model: Offline';
        }
    } catch (error) {
        console.error('Error checking model status:', error);
    }
}

async function setLanguage(lang) {
    currentLanguage = lang;
    isWaitingForConfirmation = false;
    
    // Update UI elements
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
    
    // Update button states
    document.getElementById('arabicBtn').classList.toggle('active', lang === 'ar');
    document.getElementById('englishBtn').classList.toggle('active', lang === 'en');
    
    // Update voice recognition language
    if (recognition) {
        recognition.lang = lang === 'ar' ? 'ar-SA' : 'en-US';
    }
    
    // Show/hide speak button based on TTS support
    const speakButton = document.getElementById('speakButton');
    speakButton.style.display = 'speechSynthesis' in window ? 'block' : 'none';
    
    // Get configuration from server
    try {
        const response = await fetch(`/api/config?lang=${lang}`);
        const config = await response.json();
        
        // Update text content
        document.getElementById('messageInput').placeholder = config.input_placeholder;
        document.getElementById('sendButton').querySelector('#sendText').textContent = config.send_button;
        document.getElementById('tasksTitle').textContent = config.tasks_title;
        document.getElementById('notesTitle').textContent = config.notes_title;
        document.getElementById('clearButton').textContent = config.clear_button;
        document.getElementById('examplesTitle').textContent = lang === 'ar' ? 'أمثلة للمحاولة' : 'Try These Examples';
        document.getElementById('confirmYes').textContent = lang === 'ar' ? 'نعم، احفظ' : 'Yes, Save';
        document.getElementById('confirmNo').textContent = lang === 'ar' ? 'لا، شكراً' : 'No, Thanks';
        
        // Update welcome message
        document.getElementById('welcomeMessage').innerHTML = config.welcome.replace(/\n/g, '<br>');
        
        // Update examples
        examples = config.examples;
        updateExamplesGrid();
        
    } catch (error) {
        console.error('Error loading config:', error);
    }
    
    await updateItems();
    hideConfirmation();
}

function startExampleRotation() {
    if (exampleInterval) clearInterval(exampleInterval);
    exampleInterval = setInterval(() => {
        currentExampleIndex = (currentExampleIndex + 1) % examples.length;
        updateExamplesGrid();
    }, 5000);
}

function updateExamplesGrid() {
    const examplesGrid = document.getElementById('examplesGrid');
    if (!examplesGrid) return;

    // Show 3 random examples
    const shuffledExamples = [...examples].sort(() => 0.5 - Math.random()).slice(0, 3);
    
    examplesGrid.innerHTML = shuffledExamples.map(example => `
        <div class="example-item" onclick="useExample('${example.replace(/'/g, "\\'")}')">
            ${example}
        </div>
    `).join('');
}

function refreshExamples() {
    updateExamplesGrid();
}

function useExample(exampleText) {
    if (isWaitingForConfirmation) return;
    document.getElementById('messageInput').value = exampleText;
}

function addMessage(text, isUser = false, language = 'en') {
    const container = document.getElementById('chatContainer');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isUser ? 'user-message' : 'bot-message'}`;
    messageDiv.dir = language === 'ar' ? 'rtl' : 'ltr';
    messageDiv.lang = language;
    messageDiv.textContent = text;
    container.appendChild(messageDiv);
    container.scrollTop = container.scrollHeight;
    
    // Store last bot message for TTS
    if (!isUser) {
        lastBotMessage = text;
    }
}

function showThinking(thinkingMessage) {
    const thinkingIndicator = document.getElementById('thinkingIndicator');
    const thinkingText = document.getElementById('thinkingText');
    
    thinkingText.textContent = thinkingMessage;
    thinkingIndicator.style.display = 'flex';
}

function hideThinking() {
    const thinkingIndicator = document.getElementById('thinkingIndicator');
    thinkingIndicator.style.display = 'none';
}

function showConfirmation(researchData) {
    isWaitingForConfirmation = true;
    const banner = document.getElementById('confirmationBanner');
    const preview = document.getElementById('researchPreview');
    
    document.getElementById('confirmationTitle').textContent = 
        currentLanguage === 'ar' ? 'حفظ البحث كملاحظة؟' : 'Save Research as Note?';
    
    preview.innerHTML = `
        <h4>${researchData.title}</h4>
        <div class="research-content">${researchData.content}</div>
        <small>Category: ${researchData.category}</small>
    `;
    
    banner.style.display = 'block';
    document.getElementById('messageInput').disabled = true;
}

function hideConfirmation() {
    isWaitingForConfirmation = false;
    const banner = document.getElementById('confirmationBanner');
    banner.style.display = 'none';
    document.getElementById('messageInput').disabled = false;
}

async function confirmResearch(confirm) {
    hideConfirmation();
    const message = confirm ? 
        (currentLanguage === 'ar' ? 'نعم' : 'yes') : 
        (currentLanguage === 'ar' ? 'لا' : 'no');
    
    addMessage(message, true, currentLanguage);
    await sendConfirmation(message);
}

async function sendConfirmation(message) {
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message })
        });
        
        const data = await response.json();
        addMessage(data.response, false, data.language);
        await updateItems();
        
    } catch (error) {
        addMessage(
            currentLanguage === 'ar' ? 'حدث خطأ' : 'Error occurred', 
            false, 
            currentLanguage
        );
    }
}

async function sendMessage() {
    if (isWaitingForConfirmation) return;
    
    const input = document.getElementById('messageInput');
    const message = input.value.trim();
    
    if (!message) return;
    
    // Generate unique message ID
    currentMessageId = 'msg_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    
    addMessage(message, true, currentLanguage);
    input.value = '';
    
    // Show thinking indicator
    showThinking(currentLanguage === 'ar' ? 'جاري المعالجة...' : 'Processing...');
    
    // Disable send button
    const sendButton = document.getElementById('sendButton');
    const sendText = document.getElementById('sendText');
    const sendLoader = document.getElementById('sendLoader');
    
    sendText.style.display = 'none';
    sendLoader.style.display = 'block';
    sendButton.disabled = true;
    
    try {
        // Send message and wait for immediate response
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                message: message,
                message_id: currentMessageId
            })
        });
        
        const data = await response.json();
        
        // Hide thinking immediately since we got a response
        hideThinking();
        
        if (data.status === 'completed') {
            // Show the AI response
            addMessage(data.result.response_message, false, data.result.language);
            
            // Update tasks and notes immediately
            await updateItems();
            
            // Show processing time
            if (data.processing_time) {
                console.log(`Processing time: ${data.processing_time}s`);
            }
        } else if (data.status === 'processing') {
            // Fallback to polling (though this shouldn't happen with synchronous backend)
            showThinking(data.thinking_message);
            await pollForResult(currentMessageId);
        } else {
            // Error case
            addMessage(
                currentLanguage === 'ar' ? 'حدث خطأ' : 'Error occurred', 
                false, 
                currentLanguage
            );
        }
        
    } catch (error) {
        hideThinking();
        console.error('Send message error:', error);
        const errorMsg = currentLanguage === 'ar' 
            ? 'تعذر الاتصال بالخادم' 
            : 'Failed to connect to server';
        addMessage(errorMsg, false, currentLanguage);
    } finally {
        // Re-enable send button
        sendText.style.display = 'block';
        sendLoader.style.display = 'none';
        sendButton.disabled = false;
    }
}

async function pollForResult(messageId, retries = 0) {
    if (retries > 10) { // Reduced from 30 to 10 seconds timeout
        hideThinking();
        addMessage(
            currentLanguage === 'ar' ? 'انتهت مهلة المعالجة' : 'Processing timeout',
            false,
            currentLanguage
        );
        return;
    }
    
    try {
        const response = await fetch(`/api/chat/result/${messageId}`);
        const data = await response.json();
        
        if (data.status === 'completed') {
            hideThinking();
            
            if (data.result.needs_confirmation && data.result.research_preview) {
                showConfirmation(data.result.research_preview);
            }
            
            addMessage(data.result.response_message, false, data.result.language);
            await updateItems(); // Make sure this is called
            
            // Show processing time
            if (data.processing_time) {
                console.log(`Processing time: ${data.processing_time}s`);
            }
        } else if (data.status === 'processing') {
            // Continue polling
            setTimeout(() => pollForResult(messageId, retries + 1), 1000);
        }
    } catch (error) {
        console.error('Error polling for result:', error);
        setTimeout(() => pollForResult(messageId, retries + 1), 1000);
    }
}

function handleKeyPress(event) {
    if (event.key === 'Enter' && !isWaitingForConfirmation) {
        sendMessage();
    }
}

async function updateItems() {
    try {
        console.log('Updating tasks and notes...'); // Debug log
        
        const [tasksRes, notesRes, analyticsRes] = await Promise.all([
            fetch('/api/tasks'),
            fetch('/api/notes'),
            fetch('/api/analytics')
        ]);
        
        if (!tasksRes.ok || !notesRes.ok) {
            throw new Error('Failed to fetch data');
        }
        
        const tasks = await tasksRes.json();
        const notes = await notesRes.json();
        const analytics = await analyticsRes.json();
        
        console.log(`Loaded ${tasks.length} tasks, ${notes.length} notes`); // Debug log
        
        // Update tasks
        const tasksContainer = document.getElementById('tasksContainer');
        const tasksCount = document.getElementById('tasksCount');
        
        tasksCount.textContent = tasks.length;
        
        if (tasks.length === 0) {
            tasksContainer.innerHTML = `
                <div class="empty-state" dir="${currentLanguage === 'ar' ? 'rtl' : 'ltr'}">
                    ${currentLanguage === 'ar' ? 'لا توجد مهام حالياً' : 'No tasks yet'}
                </div>
            `;
        } else {
            tasksContainer.innerHTML = tasks.map(task => {
                const taskDate = task.due_date ? new Date(task.due_date).toLocaleDateString() : '';
                const dateRange = task.start_date && task.end_date ? 
                    `${new Date(task.start_date).toLocaleDateString()} - ${new Date(task.end_date).toLocaleDateString()}` : '';
                
                return `
                <div class="task-card" dir="${task.language === 'ar' ? 'rtl' : 'ltr'}">
                    <div class="task-header">
                        <h3 class="task-title">${task.title}</h3>
                        <div class="task-actions">
                            <span class="priority-badge priority-${task.priority}">
                                ${task.priority === 'high' ? (task.language === 'ar' ? 'عالي' : 'High') : 
                                  task.priority === 'medium' ? (task.language === 'ar' ? 'متوسط' : 'Medium') : 
                                  (task.language === 'ar' ? 'منخفض' : 'Low')}
                            </span>
                            <span class="delete-btn" onclick="deleteTask(${task.id})" title="${currentLanguage === 'ar' ? 'حذف' : 'Delete'}">×</span>
                        </div>
                    </div>
                    <p class="task-description">${task.description}</p>
                    <div class="task-details">
                        <div class="task-time">
                            <span class="time-icon">🕒</span>
                            ${task.due_time || ''}
                            ${task.duration ? ` • ${task.duration}` : ''}
                        </div>
                        <div class="task-date">
                            ${dateRange || taskDate}
                            ${task.category ? ` • ${task.category}` : ''}
                        </div>
                    </div>
                </div>
                `;
            }).join('');
        }
        
        // Update notes
        const notesContainer = document.getElementById('notesContainer');
        const notesCount = document.getElementById('notesCount');
        
        notesCount.textContent = notes.length;
        
        if (notes.length === 0) {
            notesContainer.innerHTML = `
                <div class="empty-state" dir="${currentLanguage === 'ar' ? 'rtl' : 'ltr'}">
                    ${currentLanguage === 'ar' ? 'لا توجد ملاحظات حالياً' : 'No notes yet'}
                </div>
            `;
        } else {
            notesContainer.innerHTML = notes.map(note => {
                const stats = [];
                if (note.word_count) stats.push(`📊 ${note.word_count} words`);
                if (note.paragraph_count) stats.push(`📝 ${note.paragraph_count} paragraphs`);
                if (note.character_count) stats.push(`🔤 ${note.character_count} chars`);
                
                return `
                <div class="note-card" dir="${note.language === 'ar' ? 'rtl' : 'ltr'}">
                    <div class="note-header">
                        <h3 class="note-title">${note.title}</h3>
                        <span class="delete-btn" onclick="deleteNote(${note.id})" title="${currentLanguage === 'ar' ? 'حذف' : 'Delete'}">×</span>
                    </div>
                    <div class="note-content">${note.content}</div>
                    <div class="note-category">${note.category}</div>
                    ${stats.length > 0 ? `
                    <div class="note-stats">
                        ${stats.map(stat => `<span class="stat-badge">${stat}</span>`).join('')}
                    </div>
                    ` : ''}
                </div>
                `;
            }).join('');
        }
        
        // Update analytics
        document.getElementById('totalTasks').textContent = analytics.total_tasks;
        document.getElementById('totalNotes').textContent = analytics.total_notes;
        document.getElementById('completedTasks').textContent = analytics.completed_tasks;
        
        console.log('Update completed successfully'); // Debug log
        
    } catch (error) {
        console.error('Error updating items:', error);
    }
}

async function deleteTask(taskId) {
    if (confirm(currentLanguage === 'ar' ? 'هل تريد حذف هذه المهمة؟' : 'Delete this task?')) {
        await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
        await updateItems();
    }
}

async function deleteNote(noteId) {
    if (confirm(currentLanguage === 'ar' ? 'هل تريد حذف هذه الملاحظة؟' : 'Delete this note?')) {
        await fetch(`/api/notes/${noteId}`, { method: 'DELETE' });
        await updateItems();
    }
}

async function clearAll() {
    if (confirm(currentLanguage === 'ar' ? 'هل تريد مسح جميع المهام والملاحظات؟' : 'Clear all tasks and notes?')) {
        await fetch('/api/clear', { method: 'POST' });
        await updateItems();
        addMessage(
            currentLanguage === 'ar' ? 'تم مسح الكل' : 'All cleared', 
            false, 
            currentLanguage
        );
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', initializeApp);