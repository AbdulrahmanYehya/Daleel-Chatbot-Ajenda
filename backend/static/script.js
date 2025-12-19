let currentLanguage = 'en';
let examples = [];
let currentExampleIndex = 0;
let exampleInterval;
// isWaitingForConfirmation is now used specifically for AI clarifications
let isWaitingForConfirmation = false; 
let currentMessageId = null;
let recognition = null;
let isListening = false;
let lastBotMessage = '';
let manualStop = false; // Flag for voice recognition stop

// Initialize the application
async function initializeApp() {
    console.log("Initializing App...");
    await checkModelStatus();
    await setLanguage('en'); // Default to English
    startExampleRotation();
    initializeVoiceRecognition();
    
    // Periodically check model status
    setInterval(checkModelStatus, 30000); // Check every 30 seconds
    console.log("App Initialized.");
}

// Initialize voice recognition
function initializeVoiceRecognition() {
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        recognition.continuous = false; // Listen for a single utterance
        recognition.interimResults = true; // Show results as they come
        recognition.lang = currentLanguage === 'ar' ? 'ar-SA' : 'en-US';
        console.log("Voice Recognition Initialized. Lang:", recognition.lang);

        recognition.onstart = function() {
            console.log("Voice Recognition Started.");
            isListening = true;
            manualStop = false;
            updateVoiceUI(true);
        };

        recognition.onresult = function(event) {
            let transcript = '';
            for (let i = event.resultIndex; i < event.results.length; ++i) {
                transcript += event.results[i][0].transcript;
            }
            // Update input field with interim or final results
            document.getElementById('messageInput').value = transcript;
            console.log("Voice Result:", transcript);
        };

        recognition.onerror = function(event) {
            console.error('Speech recognition error:', event.error);
            // Handle common errors like 'no-speech' gracefully
            if (event.error === 'no-speech' || event.error === 'audio-capture') {
                 console.warn("No speech detected or audio capture issue.");
            }
            isListening = false;
            updateVoiceUI(false);
        };

        recognition.onend = function() {
            console.log("Voice Recognition Ended.");
            // Only stop UI if it wasn't a manual stop and still marked as listening
            // This prevents UI glitches if errors occur rapidly
            if (!manualStop && isListening) {
                isListening = false;
                updateVoiceUI(false);
            }
             // Reset manualStop flag
             manualStop = false; 
        };
    } else {
        console.warn('Speech recognition not supported by this browser.');
        document.getElementById('voiceButton').style.display = 'none';
    }
}

// Toggle voice recognition
function toggleVoiceRecognition() {
    if (!recognition) {
        console.error("Recognition not initialized.");
        return;
    }

    if (isListening) {
        console.log("Manually stopping voice recognition.");
        manualStop = true; // Set flag to indicate manual stop
        recognition.stop();
        // UI update will happen in onend handler
    } else {
        console.log("Starting voice recognition.");
        recognition.lang = currentLanguage === 'ar' ? 'ar-SA' : 'en-US'; // Ensure lang is current
        try {
            recognition.start();
        } catch (e) {
             console.error("Error starting recognition:", e);
             // Reset state if start fails immediately
             isListening = false;
             updateVoiceUI(false);
        }
    }
}

// Update voice UI (Icon, Status Text)
function updateVoiceUI(listening) {
    const voiceButton = document.getElementById('voiceButton');
    const voiceStatus = document.getElementById('voiceStatus');
    const voiceStatusText = document.getElementById('voiceStatusText');
    
    if (listening) {
        voiceButton.classList.add('listening'); // CSS class for visual feedback
        voiceStatus.style.display = 'flex';
        voiceStatusText.textContent = currentLanguage === 'ar' ? 'جاري الاستماع...' : 'Listening...';
    } else {
        voiceButton.classList.remove('listening');
        voiceStatus.style.display = 'none';
    }
}

// Text-to-Speech (TTS)
function speakText(text) {
    if ('speechSynthesis' in window) {
        // Cancel any previous speech first
        speechSynthesis.cancel(); 
        
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = currentLanguage === 'ar' ? 'ar-SA' : 'en-US';
        utterance.rate = 1.0; // Normal speaking rate
        utterance.pitch = 1; // Normal pitch
        
        console.log("Speaking:", text.substring(0, 50) + "...");
        speechSynthesis.speak(utterance);
    } else {
         console.warn("Speech synthesis not supported.");
    }
}

// Speak the last message received from the bot
function speakLastMessage() {
    if (lastBotMessage) {
        speakText(lastBotMessage);
    } else {
         console.log("No bot message available to speak.");
    }
}

// Check AI model status via API
async function checkModelStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        const statusIndicator = document.getElementById('statusIndicator');
        const modelStatus = document.getElementById('modelStatus');
        
        if (data.status === 'healthy' || data.status === 'online') { // Check for 'healthy' too
            statusIndicator.className = 'status-indicator online';
            let statusText = `AI Model: Online`;
            if(data.response_time) statusText += ` (${data.response_time}s)`;
            modelStatus.textContent = statusText;
        } else {
            statusIndicator.className = 'status-indicator'; // Default (offline/red)
            modelStatus.textContent = 'AI Model: Offline';
             if(data.ai_error) console.error("AI Status Error:", data.ai_error);
        }
    } catch (error) {
        console.error('Error checking model status:', error);
        // Update UI to show offline status on fetch error
        document.getElementById('statusIndicator').className = 'status-indicator';
        document.getElementById('modelStatus').textContent = 'AI Model: Offline (Connection Error)';
    }
}

// Set application language (UI texts, voice recognition lang)
async function setLanguage(lang) {
    if(lang !== 'en' && lang !== 'ar') {
         console.warn("Unsupported language requested:", lang);
         return;
    }
    console.log("Setting language to:", lang);
    currentLanguage = lang;
    isWaitingForConfirmation = false; // Reset confirmation state on language change
    
    // Update HTML attributes
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
    
    // Update language button active state
    document.getElementById('arabicBtn').classList.toggle('active', lang === 'ar');
    document.getElementById('englishBtn').classList.toggle('active', lang === 'en');
    
    // Update voice recognition language if initialized
    if (recognition) {
        recognition.lang = lang === 'ar' ? 'ar-SA' : 'en-US';
        console.log("Updated Recognition Lang:", recognition.lang);
    }
    
    // Toggle TTS button visibility
    const speakButton = document.getElementById('speakButton');
    speakButton.style.display = 'speechSynthesis' in window ? 'block' : 'none';
    
    // Fetch language-specific UI config from backend
    try {
        const response = await fetch(`/api/config?lang=${lang}`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const config = await response.json();
        
        // Update UI text elements
        document.getElementById('messageInput').placeholder = config.input_placeholder;
        document.getElementById('sendButton').querySelector('#sendText').textContent = config.send_button;
        document.getElementById('tasksTitle').textContent = config.tasks_title;
        document.getElementById('notesTitle').textContent = config.notes_title;
        document.getElementById('clearButton').textContent = config.clear_button;
        document.getElementById('examplesTitle').textContent = config.examples_title || (lang === 'ar' ? 'أمثلة للمحاولة' : 'Try These Examples'); // Added fallback
        
        // Update welcome message
        const welcomeElement = document.getElementById('welcomeMessage');
        if (welcomeElement) {
             welcomeElement.innerHTML = config.welcome.replace(/\n/g, '<br>');
        }
        
        // Update examples
        examples = config.examples || []; // Ensure examples is an array
        updateExamplesGrid();
        
    } catch (error) {
        console.error('Error loading config:', error);
        // Provide fallback text if config fails
        document.getElementById('messageInput').placeholder = "Enter your message...";
    }
    
    // Refresh tasks/notes display
    await updateItems(); 
}

// Start rotating example prompts in the UI
function startExampleRotation() {
    if (exampleInterval) clearInterval(exampleInterval);
    exampleInterval = setInterval(() => {
        if (examples.length > 0) { // Only rotate if examples exist
             currentExampleIndex = (currentExampleIndex + 1) % examples.length;
             updateExamplesGrid();
        }
    }, 5000); // Rotate every 5 seconds
}

// Update the example prompts shown in the UI
function updateExamplesGrid() {
    const examplesGrid = document.getElementById('examplesGrid');
    if (!examplesGrid || !examples || examples.length === 0) return;

    // Show up to 3 random examples
    const shuffledExamples = [...examples].sort(() => 0.5 - Math.random());
    const displayExamples = shuffledExamples.slice(0, 3);
    
    examplesGrid.innerHTML = displayExamples.map(example => `
        <div class="example-item" onclick="useExample('${example.replace(/'/g, "\\'")}')">
            ${example}
        </div>
    `).join('');
}

// Refresh examples manually (button click)
function refreshExamples() {
    updateExamplesGrid();
}

// Use an example prompt when clicked
function useExample(exampleText) {
    if (isWaitingForConfirmation) return; // Don't allow during clarification
    document.getElementById('messageInput').value = exampleText;
    document.getElementById('messageInput').focus(); // Focus input field
}

// Add a message (user or bot) to the chat display
function addMessage(text, isUser = false, language = 'en') {
    const container = document.getElementById('chatContainer');
    if (!container) return;
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isUser ? 'user-message' : 'bot-message'}`;
    messageDiv.dir = language === 'ar' ? 'rtl' : 'ltr';
    messageDiv.lang = language;
    // Basic sanitization: replace < and > to prevent HTML injection
    messageDiv.textContent = text; 
    
    container.appendChild(messageDiv);
    container.scrollTop = container.scrollHeight; // Auto-scroll to bottom
    
    // Store last bot message for TTS
    if (!isUser) {
        lastBotMessage = text;
    }
}

// Add AI clarification request to the chat display
function addClarification(message, questions, language = 'en') {
    const container = document.getElementById('chatContainer');
    if (!container) return;

    const messageDiv = document.createElement('div');
    messageDiv.className = 'message bot-message clarification-message'; // Added class for potential styling
    messageDiv.dir = language === 'ar' ? 'rtl' : 'ltr';
    messageDiv.lang = language;
    
    // Sanitize message before adding to innerHTML
    const safeMessage = message.replace(/</g, "&lt;").replace(/>/g, "&gt;");
    let html = `<strong>${safeMessage}</strong>`;
    
    if (questions && questions.length > 0) {
        html += '<ul>';
        questions.forEach(q => {
            const safeQ = q.replace(/</g, "&lt;").replace(/>/g, "&gt;");
            html += `<li>${safeQ}</li>`;
        });
        html += '</ul>';
    }
    
    messageDiv.innerHTML = html;
    container.appendChild(messageDiv);
    container.scrollTop = container.scrollHeight;
    lastBotMessage = message; // Store main question for TTS
    isWaitingForConfirmation = true; // Set flag: waiting for user's clarifying response
    console.log("Clarification requested.");
}


// Show the "Thinking..." indicator
function showThinking(thinkingMessage) {
    const thinkingIndicator = document.getElementById('thinkingIndicator');
    const thinkingText = document.getElementById('thinkingText');
    if (!thinkingIndicator || !thinkingText) return;
    
    thinkingText.textContent = thinkingMessage;
    thinkingIndicator.style.display = 'flex';
}

// Hide the "Thinking..." indicator
function hideThinking() {
    const thinkingIndicator = document.getElementById('thinkingIndicator');
    if (thinkingIndicator) thinkingIndicator.style.display = 'none';
}

// --- Main function to send message to backend ---
async function sendMessage() {
    const input = document.getElementById('messageInput');
    const message = input.value.trim();
    
    if (!message) return; // Don't send empty messages
    
    // If waiting for clarification, this message is the clarification
    isWaitingForConfirmation = false; 
    
    addMessage(message, true, currentLanguage);
    input.value = ''; // Clear input field
    
    // Show thinking indicator using a relevant message
    // Note: AI handler also detects intent, could potentially pass intent here later
    showThinking(currentLanguage === 'ar' ? 'جاري المعالجة...' : 'Processing...'); 
    
    // Disable send button during processing
    const sendButton = document.getElementById('sendButton');
    const sendText = document.getElementById('sendText');
    const sendLoader = document.getElementById('sendLoader');
    sendText.style.display = 'none';
    sendLoader.style.display = 'block';
    sendButton.disabled = true;
    input.disabled = true; // Disable input field too
    
    try {
        // Send message and wait for SYNCHRONOUS response
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message }) // Send only the message for now
        });
        
        hideThinking(); // Hide indicator once response starts coming back
        
        if (!response.ok) {
            // Handle HTTP errors (e.g., 500 Internal Server Error)
            let errorMsg = `HTTP error ${response.status}: ${response.statusText}`;
             try {
                 const errorData = await response.json();
                 errorMsg = errorData.message || errorMsg;
             } catch (e) { /* Ignore if response is not JSON */ }
            throw new Error(errorMsg);
        }

        const data = await response.json();
        
        if (data.status === 'completed' && data.result) {
            const result = data.result;
            const responseLang = result.language || currentLanguage; // Use language from response if available

            // --- Handle AI Response ---
            if (result.requires_clarification) {
                // AI needs more info - display questions
                addClarification(result.response_message, result.clarification_questions, responseLang);
                // isWaitingForConfirmation is set within addClarification
            } else {
                // Normal AI response
                addMessage(result.response_message, false, responseLang);
                // Check if tasks/notes were created/updated and refresh list
                if (result.tasks?.length > 0 || result.notes?.length > 0) {
                     console.log("Tasks/Notes received in response, updating UI.");
                     await updateItems(); // Refresh lists to show new/updated items
                } else if (result.ai_metadata?.response_type?.includes('delete')) {
                     console.log("Delete action confirmed, updating UI.");
                     await updateItems(); // Refresh lists after deletion
                }
            }
            
            // Log processing time
            if (data.processing_time) {
                console.log(`Request processed in: ${data.processing_time}s`);
            }
        } else if (data.status === 'error') {
             // Handle errors reported by the backend's JSON response
             console.error("Backend reported error:", data.message);
             addMessage(data.message || (currentLanguage === 'ar' ? 'حدث خطأ' : 'An error occurred'), false, currentLanguage);
        } else {
             // Handle unexpected response structure
             console.error("Unexpected response structure:", data);
             throw new Error("Received an unexpected response from the server.");
        }
        
    } catch (error) {
        hideThinking(); // Ensure thinking is hidden on error
        console.error('Send message failed:', error);
        const errorMsg = currentLanguage === 'ar' 
            ? 'فشل الاتصال بالخادم. حاول مرة أخرى.' 
            : 'Failed to connect to the server. Please try again.';
        addMessage(errorMsg + ` (${error.message})`, false, currentLanguage); // Show error detail
    } finally {
        // Re-enable send button and input field
        sendText.style.display = 'block';
        sendLoader.style.display = 'none';
        sendButton.disabled = false;
        input.disabled = false;
        input.focus(); // Focus input field after processing
    }
}

// Handle Enter key press in the input field
function handleKeyPress(event) {
    // Check if Enter key was pressed and Shift key was not held (allows multiline input if needed later)
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault(); // Prevent default form submission/newline
        sendMessage();
    }
}

// --- Function to fetch and update Tasks, Notes, and Analytics ---
async function updateItems() {
    console.log('Fetching latest tasks, notes, and analytics...');
    try {
        const [tasksRes, notesRes, analyticsRes] = await Promise.all([
            fetch('/api/tasks').catch(e => ({ ok: false, error: e })), // Add catch for individual fetch errors
            fetch('/api/notes').catch(e => ({ ok: false, error: e })),
            fetch('/api/analytics').catch(e => ({ ok: false, error: e }))
        ]);
        
        // --- Update Tasks ---
        const tasksContainer = document.getElementById('tasksContainer');
        const tasksCount = document.getElementById('tasksCount');
        if (tasksRes.ok) {
            const tasks = await tasksRes.json();
            tasksCount.textContent = tasks.length;
            if (tasks.length === 0) {
                tasksContainer.innerHTML = `<div class="empty-state" dir="${currentLanguage === 'ar' ? 'rtl' : 'ltr'}">${currentLanguage === 'ar' ? 'لا توجد مهام حالياً' : 'No tasks yet'}</div>`;
            } else {
                tasksContainer.innerHTML = tasks.map(task => renderTaskCard(task)).join('');
            }
        } else {
            console.error("Failed to fetch tasks:", tasksRes.error || tasksRes.status);
            tasksContainer.innerHTML = `<div class="empty-state error">Failed to load tasks.</div>`;
            tasksCount.textContent = '?';
        }

        // --- Update Notes ---
        const notesContainer = document.getElementById('notesContainer');
        const notesCount = document.getElementById('notesCount');
         if (notesRes.ok) {
            const notes = await notesRes.json();
            notesCount.textContent = notes.length;
            if (notes.length === 0) {
                notesContainer.innerHTML = `<div class="empty-state" dir="${currentLanguage === 'ar' ? 'rtl' : 'ltr'}">${currentLanguage === 'ar' ? 'لا توجد ملاحظات حالياً' : 'No notes yet'}</div>`;
            } else {
                notesContainer.innerHTML = notes.map(note => renderNoteCard(note)).join('');
            }
         } else {
            console.error("Failed to fetch notes:", notesRes.error || notesRes.status);
            notesContainer.innerHTML = `<div class="empty-state error">Failed to load notes.</div>`;
            notesCount.textContent = '?';
         }

        // --- Update Analytics (FR-16) ---
        if(analyticsRes.ok) {
            const analytics = await analyticsRes.json();
            document.getElementById('totalTasks').textContent = analytics.total_tasks ?? 0; // Use current total
            document.getElementById('totalNotes').textContent = analytics.total_notes ?? 0; // Use current total
            document.getElementById('completedTasks').textContent = analytics.completed_tasks ?? 0;
            // Optionally display other analytics like total_tasks_created if needed
        } else {
             console.error("Failed to fetch analytics:", analyticsRes.error || analyticsRes.status);
             document.getElementById('totalTasks').textContent = '?';
             document.getElementById('totalNotes').textContent = '?';
             document.getElementById('completedTasks').textContent = '?';
        }
        
        console.log('UI update complete.');
        
    } catch (error) {
        // Catch errors from Promise.all or json parsing
        console.error('Error updating items:', error);
        // Display error state in UI panels
        document.getElementById('tasksContainer').innerHTML = `<div class="empty-state error">Error loading data.</div>`;
        document.getElementById('notesContainer').innerHTML = `<div class="empty-state error">Error loading data.</div>`;
    }
}

// --- Helper function to render a single Task Card ---
function renderTaskCard(task) {
    const taskLang = task.language || currentLanguage; // Use task's language or default
    const taskDir = taskLang === 'ar' ? 'rtl' : 'ltr';

    // Date/Time formatting
    let displayDate = '';
    try {
        if (task.start_date && task.end_date) {
            displayDate = `${new Date(task.start_date).toLocaleDateString()} - ${new Date(task.end_date).toLocaleDateString()}`;
        } else if (task.due_date) {
            // Check if date is valid before formatting
            const dateObj = new Date(task.due_date);
            if (!isNaN(dateObj)) {
                 displayDate = dateObj.toLocaleDateString();
            } else {
                 displayDate = task.due_date; // Show raw string if invalid
            }
        }
    } catch (e) {
         console.warn("Error formatting date for task", task.id, e);
         displayDate = task.due_date || ''; // Fallback
    }

    const timeInfo = [task.due_time, task.duration].filter(Boolean).join(' • '); // Join time and duration if both exist

    // Priority translation
    let priorityText = task.priority || 'medium';
    if (taskLang === 'ar') {
        if (priorityText === 'high') priorityText = 'عالي';
        else if (priorityText === 'medium') priorityText = 'متوسط';
        else if (priorityText === 'low') priorityText = 'منخفض';
    } else {
         // Capitalize English priority
         priorityText = priorityText.charAt(0).toUpperCase() + priorityText.slice(1);
    }

    return `
    <div class="task-card" dir="${taskDir}">
        <div class="task-header">
            <h3 class="task-title">${task.title || (taskLang === 'ar' ? 'مهمة بدون عنوان' : 'Untitled Task')}</h3>
            <div class="task-actions">
                <span class="priority-badge priority-${task.priority || 'medium'}">
                    ${priorityText}
                </span>
                <span class="delete-btn" onclick="deleteTask(${task.id})" title="${taskLang === 'ar' ? 'حذف' : 'Delete'}">×</span>
            </div>
        </div>
        ${task.description ? `<p class="task-description">${task.description}</p>` : ''}
        <div class="task-details">
            ${timeInfo ? `<div class="task-time"><span class="time-icon">🕒</span> ${timeInfo}</div>` : ''}
            <div class="task-date">
                ${displayDate}
                ${task.category ? ` • ${task.category}` : ''}
            </div>
        </div>
    </div>
    `;
}

// --- Helper function to render a single Note Card ---
function renderNoteCard(note) {
     const noteLang = note.language || currentLanguage;
     const noteDir = noteLang === 'ar' ? 'rtl' : 'ltr';

    const stats = [];
    if (note.word_count) stats.push(`📊 ${note.word_count} ${noteLang === 'ar' ? 'كلمات' : 'words'}`);
    if (note.paragraph_count) stats.push(`📝 ${note.paragraph_count} ${noteLang === 'ar' ? 'فقرات' : 'paragraphs'}`);
    // if (note.character_count) stats.push(`🔤 ${note.character_count} chars`); // Optional

    return `
    <div class="note-card" dir="${noteDir}">
        <div class="note-header">
            <h3 class="note-title">${note.title || (noteLang === 'ar' ? 'ملاحظة بدون عنوان' : 'Untitled Note')}</h3>
            <span class="delete-btn" onclick="deleteNote(${note.id})" title="${noteLang === 'ar' ? 'حذف' : 'Delete'}">×</span>
        </div>
        ${note.content ? `<div class="note-content">${note.content.replace(/\n/g, '<br>')}</div>` : ''} 
        <div class="note-footer">
             ${note.category ? `<div class="note-category">${note.category}</div>` : ''}
             ${stats.length > 0 ? `<div class="note-stats">${stats.map(stat => `<span class="stat-badge">${stat}</span>`).join('')}</div>` : ''}
        </div>
    </div>
    `;
}


// --- Action Functions (Delete, Clear) ---

async function deleteTask(taskId) {
    if (confirm(currentLanguage === 'ar' ? 'هل تريد بالتأكيد حذف هذه المهمة؟' : 'Are you sure you want to delete this task?')) {
        console.log("Deleting task:", taskId);
        try {
            const response = await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
            if (!response.ok) {
                 const errorData = await response.json();
                 throw new Error(errorData.error || `Failed to delete task ${taskId}`);
            }
            await updateItems(); // Refresh UI after successful deletion
        } catch (error) {
             console.error("Error deleting task:", error);
             alert(currentLanguage === 'ar' ? 'فشل حذف المهمة.' : 'Failed to delete task.');
        }
    }
}

async function deleteNote(noteId) {
    if (confirm(currentLanguage === 'ar' ? 'هل تريد بالتأكيد حذف هذه الملاحظة؟' : 'Are you sure you want to delete this note?')) {
        console.log("Deleting note:", noteId);
        try {
            const response = await fetch(`/api/notes/${noteId}`, { method: 'DELETE' });
             if (!response.ok) {
                 const errorData = await response.json();
                 throw new Error(errorData.error || `Failed to delete note ${noteId}`);
             }
            await updateItems(); // Refresh UI
        } catch (error) {
             console.error("Error deleting note:", error);
             alert(currentLanguage === 'ar' ? 'فشل حذف الملاحظة.' : 'Failed to delete note.');
        }
    }
}

async function clearAll() {
    if (confirm(currentLanguage === 'ar' ? 'تحذير: سيتم حذف جميع المهام والملاحظات نهائياً. هل أنت متأكد؟' : 'Warning: This will permanently delete all tasks and notes. Are you sure?')) {
        console.log("Clearing all data...");
        try {
             const response = await fetch('/api/clear', { method: 'POST' });
             if (!response.ok) {
                 const errorData = await response.json();
                 throw new Error(errorData.error || 'Failed to clear data');
             }
            await updateItems(); // Refresh UI
            // Optionally clear chat messages too
            // document.getElementById('chatContainer').innerHTML = ''; 
            addMessage(
                currentLanguage === 'ar' ? 'تم مسح جميع البيانات بنجاح.' : 'All data cleared successfully.', 
                false, 
                currentLanguage
            );
        } catch (error) {
             console.error("Error clearing data:", error);
             alert(currentLanguage === 'ar' ? 'فشل مسح البيانات.' : 'Failed to clear data.');
        }
    }
}

// --- Initialize App on Page Load ---
document.addEventListener('DOMContentLoaded', initializeApp);