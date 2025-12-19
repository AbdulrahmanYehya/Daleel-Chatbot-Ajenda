let currentLanguage = 'en';
let examples = [];
let currentExampleIndex = 0;
let exampleInterval;
let isWaitingForConfirmation = false; 
let currentMessageId = null;
let recognition = null;
let isListening = false;
let lastBotMessage = '';
let manualStop = false;
let silenceTimer = null; // Timer to detect silence

// Initialize the application
async function initializeApp() {
    console.log("Initializing App...");
    await checkModelStatus();
    await setLanguage('en'); // Default to English
    startExampleRotation();
    initializeVoiceRecognition();
    
    // Periodically check model status
    setInterval(checkModelStatus, 30000); 
    console.log("App Initialized.");
    
    // Handle File Upload
    const fileInput = document.getElementById('fileInput');
    if (fileInput) {
        fileInput.addEventListener('change', async function(e) {
            const file = e.target.files[0];
            if (!file) return;

            addMessage(`📂 Uploading & Summarizing: ${file.name}...`, true, currentLanguage);
            showThinking("Reading document...");

            const formData = new FormData();
            formData.append('file', file);

            try {
                const response = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                });
                const data = await response.json();
                
                hideThinking();
                if(data.error) {
                    addMessage("Error: " + data.error, false);
                } else {
                    addMessage(data.result.response_message, false);
                    await updateItems();
                }
            } catch (err) {
                hideThinking();
                console.error(err);
                addMessage("Upload failed.", false);
            }
            // Reset input so same file can be selected again if needed
            this.value = '';
        });
    }
}

// Initialize voice recognition
function initializeVoiceRecognition() {
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        
        // Settings to keep voice active longer
        recognition.continuous = true; 
        recognition.interimResults = true; 
        recognition.lang = currentLanguage === 'ar' ? 'ar-SA' : 'en-US';
        console.log("Voice Recognition Initialized. Lang:", recognition.lang);

        recognition.onstart = function() {
            console.log("Voice Recognition Started.");
            isListening = true;
            manualStop = false;
            updateVoiceUI(true);
            resetSilenceTimer();
        };

        recognition.onresult = function(event) {
            resetSilenceTimer();
            
            let interimTranscript = '';
            let finalTranscript = '';

            for (let i = event.resultIndex; i < event.results.length; ++i) {
                if (event.results[i].isFinal) {
                    finalTranscript += event.results[i][0].transcript;
                } else {
                    interimTranscript += event.results[i][0].transcript;
                }
            }

            const inputField = document.getElementById('messageInput');
            if (finalTranscript || interimTranscript) {
                 inputField.value = finalTranscript + interimTranscript;
            }
        };

        recognition.onerror = function(event) {
            console.error('Speech recognition error:', event.error);
            if (event.error === 'no-speech') {
                 console.warn("No speech detected.");
                 return; // Don't stop immediately on no-speech errors
            }
            stopVoice();
        };

        recognition.onend = function() {
            console.log("Voice Recognition Ended.");
            clearTimeout(silenceTimer); 
            isListening = false;
            updateVoiceUI(false);
            manualStop = false; 
        };
    } else {
        console.warn('Speech recognition not supported by this browser.');
        const vBtn = document.getElementById('voiceButton');
        if(vBtn) vBtn.style.display = 'none';
    }
}

function resetSilenceTimer() {
    clearTimeout(silenceTimer);
    // Stop listening after 3 seconds of silence
    silenceTimer = setTimeout(() => {
        console.log("Silence detected, stopping recognition.");
        stopVoice();
    }, 3000); 
}

function stopVoice() {
    if (recognition && isListening) {
        manualStop = true;
        recognition.stop();
    }
}

function toggleVoiceRecognition() {
    if (!recognition) {
        console.error("Recognition not initialized.");
        return;
    }

    if (isListening) {
        stopVoice();
    } else {
        console.log("Starting voice recognition.");
        recognition.lang = currentLanguage === 'ar' ? 'ar-SA' : 'en-US'; 
        try {
            recognition.start();
        } catch (e) {
             console.error("Error starting recognition:", e);
             isListening = false;
             updateVoiceUI(false);
        }
    }
}

function updateVoiceUI(listening) {
    const voiceButton = document.getElementById('voiceButton');
    const voiceStatus = document.getElementById('voiceStatus');
    const voiceStatusText = document.getElementById('voiceStatusText');
    
    if (voiceButton) {
        if (listening) {
            voiceButton.classList.add('listening');
            if(voiceStatus) voiceStatus.style.display = 'flex';
            if(voiceStatusText) voiceStatusText.textContent = currentLanguage === 'ar' ? 'جاري الاستماع...' : 'Listening...';
        } else {
            voiceButton.classList.remove('listening');
            if(voiceStatus) voiceStatus.style.display = 'none';
        }
    }
}

function speakText(text) {
    if ('speechSynthesis' in window) {
        speechSynthesis.cancel(); 
        
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = currentLanguage === 'ar' ? 'ar-SA' : 'en-US';
        utterance.rate = 1.0; 
        utterance.pitch = 1; 
        
        speechSynthesis.speak(utterance);
    } else {
         console.warn("Speech synthesis not supported.");
    }
}

function speakLastMessage() {
    if (lastBotMessage) {
        speakText(lastBotMessage);
    }
}

async function checkModelStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        const statusIndicator = document.getElementById('statusIndicator');
        const modelStatus = document.getElementById('modelStatus');
        
        if (statusIndicator && modelStatus) {
            if (data.status === 'healthy' || data.status === 'online') { 
                statusIndicator.className = 'status-indicator online';
                let statusText = `AI Online`;
                modelStatus.textContent = statusText;
            } else {
                statusIndicator.className = 'status-indicator'; 
                modelStatus.textContent = 'AI Offline';
            }
        }
    } catch (error) {
        console.error('Error checking model status:', error);
        const statusIndicator = document.getElementById('statusIndicator');
        if(statusIndicator) statusIndicator.className = 'status-indicator';
    }
}

async function setLanguage(lang) {
    if(lang !== 'en' && lang !== 'ar') return;
    
    currentLanguage = lang;
    isWaitingForConfirmation = false;
    
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
    
    document.getElementById('arabicBtn').classList.toggle('active', lang === 'ar');
    document.getElementById('englishBtn').classList.toggle('active', lang === 'en');
    
    if (recognition) {
        recognition.lang = lang === 'ar' ? 'ar-SA' : 'en-US';
    }
    
    try {
        const response = await fetch(`/api/config?lang=${lang}`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const config = await response.json();
        
        // Safety checks for DOM elements
        const input = document.getElementById('messageInput');
        if(input) input.placeholder = config.input_placeholder;
        
        const sendText = document.getElementById('sendText');
        if(sendText) sendText.textContent = config.send_button;
        
        const tTitle = document.getElementById('tasksTitle');
        if(tTitle) tTitle.textContent = config.tasks_title;
        
        const nTitle = document.getElementById('notesTitle');
        if(nTitle) nTitle.textContent = config.notes_title;
        
        const cBtn = document.getElementById('clearButton');
        if(cBtn) cBtn.textContent = config.clear_button;
        
        const exTitle = document.getElementById('examplesTitle');
        if(exTitle) exTitle.textContent = config.examples_title || (lang === 'ar' ? 'أمثلة للمحاولة' : 'Try These Examples'); 
        
        const welcomeElement = document.getElementById('welcomeMessage');
        if (welcomeElement) {
             welcomeElement.innerHTML = config.welcome.replace(/\n/g, '<br>');
        }
        
        // Populate examples from Config
        examples = config.examples || []; 
        updateExamplesGrid();
        
    } catch (error) {
        console.error('Error loading config:', error);
    }
    
    await updateItems(); 
}

function startExampleRotation() {
    if (exampleInterval) clearInterval(exampleInterval);
    exampleInterval = setInterval(() => {
        if (examples.length > 0) {
             currentExampleIndex = (currentExampleIndex + 1) % examples.length;
             // We randomize the rotation slightly by re-shuffling implicitly in updateExamplesGrid
             updateExamplesGrid();
        }
    }, 8000); // Rotates every 8 seconds
}

function updateExamplesGrid() {
    const examplesGrid = document.getElementById('examplesGrid');
    if (!examplesGrid || !examples || examples.length === 0) return;

    // Pick 3 random examples
    const shuffledExamples = [...examples].sort(() => 0.5 - Math.random());
    const displayExamples = shuffledExamples.slice(0, 3);
    
    examplesGrid.innerHTML = displayExamples.map(example => `
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
    const input = document.getElementById('messageInput');
    if(input) {
        input.value = exampleText;
        input.focus(); 
    }
}

function addMessage(text, isUser = false, language = 'en') {
    const container = document.getElementById('chatContainer');
    if (!container) return;
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isUser ? 'user-message' : 'bot-message'}`;
    messageDiv.dir = language === 'ar' ? 'rtl' : 'ltr';
    messageDiv.lang = language;
    messageDiv.textContent = text; 
    
    container.appendChild(messageDiv);
    container.scrollTop = container.scrollHeight; 
    
    if (!isUser) {
        lastBotMessage = text;
    }
}

function showThinking(thinkingMessage) {
    const thinkingIndicator = document.getElementById('thinkingIndicator');
    const thinkingText = document.getElementById('thinkingText');
    if (!thinkingIndicator || !thinkingText) return;
    
    thinkingText.textContent = thinkingMessage;
    thinkingIndicator.style.display = 'flex';
}

function hideThinking() {
    const thinkingIndicator = document.getElementById('thinkingIndicator');
    if (thinkingIndicator) thinkingIndicator.style.display = 'none';
}

async function sendMessage() {
    const input = document.getElementById('messageInput');
    const message = input.value.trim();
    
    if (!message) return; 
    
    isWaitingForConfirmation = false; 
    
    addMessage(message, true, currentLanguage);
    input.value = ''; 
    
    showThinking(currentLanguage === 'ar' ? 'جاري المعالجة...' : 'Processing...'); 
    
    const sendButton = document.getElementById('sendButton');
    const sendText = document.getElementById('sendText');
    const sendLoader = document.getElementById('sendLoader');
    if(sendText) sendText.style.display = 'none';
    if(sendLoader) sendLoader.style.display = 'block';
    if(sendButton) sendButton.disabled = true;
    input.disabled = true; 
    
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message }) 
        });
        
        hideThinking(); 
        
        if (!response.ok) {
            let errorMsg = `HTTP error ${response.status}: ${response.statusText}`;
             try {
                 const errorData = await response.json();
                 errorMsg = errorData.message || errorMsg;
             } catch (e) { }
            throw new Error(errorMsg);
        }

        const data = await response.json();
        
        if (data.status === 'completed' && data.result) {
            const result = data.result;
            const responseLang = result.language || currentLanguage; 

            addMessage(result.response_message, false, responseLang);
            
            // Refresh items if creation/deletion occurred
            if ((result.tasks && result.tasks.length > 0) || (result.notes && result.notes.length > 0) || result.ai_metadata) {
                 await updateItems(); 
            }
            
        } else if (data.status === 'error') {
             console.error("Backend reported error:", data.message);
             addMessage(data.message || (currentLanguage === 'ar' ? 'حدث خطأ' : 'An error occurred'), false, currentLanguage);
        }
        
    } catch (error) {
        hideThinking(); 
        console.error('Send message failed:', error);
        const errorMsg = currentLanguage === 'ar' 
            ? 'فشل الاتصال بالخادم.' 
            : 'Failed to connect to the server.';
        addMessage(errorMsg, false, currentLanguage);
    } finally {
        if(sendText) sendText.style.display = 'block';
        if(sendLoader) sendLoader.style.display = 'none';
        if(sendButton) sendButton.disabled = false;
        input.disabled = false;
        input.focus(); 
    }
}

function handleKeyPress(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault(); 
        sendMessage();
    }
}

async function updateItems() {
    console.log('Fetching latest tasks, notes...');
    try {
        const [tasksRes, notesRes, analyticsRes] = await Promise.all([
            fetch('/api/tasks').catch(e => ({ ok: false, error: e })), 
            fetch('/api/notes').catch(e => ({ ok: false, error: e })),
            fetch('/api/analytics').catch(e => ({ ok: false, error: e }))
        ]);
        
        const tasksContainer = document.getElementById('tasksContainer');
        const tasksCount = document.getElementById('tasksCount');
        
        if (tasksRes.ok && tasksContainer) {
            const tasks = await tasksRes.json();
            if(tasksCount) tasksCount.textContent = tasks.length;
            if (tasks.length === 0) {
                tasksContainer.innerHTML = `<div class="empty-state" dir="${currentLanguage === 'ar' ? 'rtl' : 'ltr'}">${currentLanguage === 'ar' ? 'لا توجد مهام حالياً' : 'No tasks yet'}</div>`;
            } else {
                tasksContainer.innerHTML = tasks.map(task => renderTaskCard(task)).join('');
            }
        }

        const notesContainer = document.getElementById('notesContainer');
        const notesCount = document.getElementById('notesCount');
         if (notesRes.ok && notesContainer) {
            const notes = await notesRes.json();
            if(notesCount) notesCount.textContent = notes.length;
            if (notes.length === 0) {
                notesContainer.innerHTML = `<div class="empty-state" dir="${currentLanguage === 'ar' ? 'rtl' : 'ltr'}">${currentLanguage === 'ar' ? 'لا توجد ملاحظات حالياً' : 'No notes yet'}</div>`;
            } else {
                notesContainer.innerHTML = notes.map(note => renderNoteCard(note)).join('');
            }
         }

        if(analyticsRes.ok) {
            const analytics = await analyticsRes.json();
            const tTasks = document.getElementById('totalTasks');
            const tNotes = document.getElementById('totalNotes');
            const cTasks = document.getElementById('completedTasks');
            
            if(tTasks) tTasks.textContent = analytics.total_tasks ?? 0; 
            if(tNotes) tNotes.textContent = analytics.total_notes ?? 0; 
            if(cTasks) cTasks.textContent = analytics.completed_tasks ?? 0;
        }
        
    } catch (error) {
        console.error('Error updating items:', error);
    }
}

// Convert 24h to AM/PM
function formatTimeAMPM(time24) {
    if (!time24) return '';
    try {
        if (time24.toLowerCase().includes('m')) return time24;
        
        const [hours, minutes] = time24.split(':');
        let h = parseInt(hours);
        const m = minutes || '00';
        const ampm = h >= 12 ? 'PM' : 'AM';
        
        h = h % 12;
        h = h ? h : 12; 
        return `${h}:${m} ${ampm}`;
    } catch (e) {
        return time24;
    }
}

function renderTaskCard(task) {
    const taskLang = task.language || currentLanguage; 
    const taskDir = taskLang === 'ar' ? 'rtl' : 'ltr';

    let displayDate = '';
    try {
        if (task.start_date && task.end_date) {
            displayDate = `${new Date(task.start_date).toLocaleDateString()} - ${new Date(task.end_date).toLocaleDateString()}`;
        } else if (task.due_date) {
            const dateObj = new Date(task.due_date);
            if (!isNaN(dateObj)) {
                 displayDate = dateObj.toLocaleDateString();
            } else {
                 displayDate = task.due_date; 
            }
        }
    } catch (e) {
         displayDate = task.due_date || ''; 
    }

    let displayTime = '';
    if (task.due_time) {
        displayTime = formatTimeAMPM(task.due_time);
    }

    const timeInfo = [displayTime, task.duration].filter(Boolean).join(' • '); 

    let priorityText = task.priority || 'medium';
    if (taskLang === 'ar') {
        if (priorityText === 'high') priorityText = 'عالي';
        else if (priorityText === 'medium') priorityText = 'متوسط';
        else if (priorityText === 'low') priorityText = 'منخفض';
    } else {
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

function renderNoteCard(note) {
     const noteLang = note.language || currentLanguage;
     const noteDir = noteLang === 'ar' ? 'rtl' : 'ltr';

    const stats = [];
    if (note.word_count) stats.push(`📊 ${note.word_count} ${noteLang === 'ar' ? 'كلمات' : 'words'}`);

    return `
    <div class="note-card" dir="${noteDir}">
        <div class="note-header">
            <h3 class="note-title">${note.title || (noteLang === 'ar' ? 'ملاحظة بدون عنوان' : 'Untitled Note')}</h3>
            <div class="note-actions">
                <a href="/api/export/pdf/${note.id}" target="_blank" class="export-btn" title="Export PDF">⬇</a>
                <span class="delete-btn" onclick="deleteNote(${note.id})" title="${noteLang === 'ar' ? 'حذف' : 'Delete'}">×</span>
            </div>
        </div>
        ${note.content ? `<div class="note-content">${note.content.replace(/\n/g, '<br>')}</div>` : ''} 
        <div class="note-footer">
             ${note.category ? `<div class="note-category">${note.category}</div>` : ''}
             ${stats.length > 0 ? `<div class="note-stats">${stats.map(stat => `<span class="stat-badge">${stat}</span>`).join('')}</div>` : ''}
        </div>
    </div>
    `;
}

async function deleteTask(taskId) {
    if (confirm(currentLanguage === 'ar' ? 'هل تريد بالتأكيد حذف هذه المهمة؟' : 'Are you sure you want to delete this task?')) {
        try {
            const response = await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
            if (!response.ok) throw new Error();
            await updateItems(); 
        } catch (error) {
             alert(currentLanguage === 'ar' ? 'فشل حذف المهمة.' : 'Failed to delete task.');
        }
    }
}

async function deleteNote(noteId) {
    if (confirm(currentLanguage === 'ar' ? 'هل تريد بالتأكيد حذف هذه الملاحظة؟' : 'Are you sure you want to delete this note?')) {
        try {
            const response = await fetch(`/api/notes/${noteId}`, { method: 'DELETE' });
             if (!response.ok) throw new Error();
            await updateItems(); 
        } catch (error) {
             alert(currentLanguage === 'ar' ? 'فشل حذف الملاحظة.' : 'Failed to delete note.');
        }
    }
}

async function clearAll() {
    if (confirm(currentLanguage === 'ar' ? 'تحذير: سيتم حذف جميع المهام والملاحظات نهائياً. هل أنت متأكد؟' : 'Warning: This will permanently delete all tasks and notes. Are you sure?')) {
        try {
             const response = await fetch('/api/clear', { method: 'POST' });
             if (!response.ok) throw new Error();
            await updateItems(); 
            addMessage(
                currentLanguage === 'ar' ? 'تم مسح جميع البيانات بنجاح.' : 'All data cleared successfully.', 
                false, 
                currentLanguage
            );
        } catch (error) {
             alert(currentLanguage === 'ar' ? 'فشل مسح البيانات.' : 'Failed to clear data.');
        }
    }
}

document.addEventListener('DOMContentLoaded', initializeApp);