// ==========================================
// STATE
// ==========================================
let currentLanguage = 'en';
let examples = [];
let currentExampleIndex = 0;
let exampleInterval;
let recognition = null;
let isListening = false;
let sendTimeout = null;
let allTasks = [];
let allNotes = [];
let allWorkspaces = [];
let allSpaces = [];   

// ==========================================
// SECURITY
// ==========================================
function escapeHtml(text) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(String(text || '')));
    return div.innerHTML;
}

// ==========================================
// UI TEXT
// ==========================================
const uiText = {
    'en': {
        'tasksTitle': 'Tasks', 'notesTitle': 'Notes', 'workspacesTitle': 'Workspaces',
        'sendBtn': 'Send', 'placeholder': 'Type a task, note, or query... (Shift+Enter for new line)',
        'modelOnline': 'Online', 'modelOffline': 'Offline Mode', 'clearBtnText': 'Clear',
        'deleteConfirm': 'Are you sure you want to delete this?',
        'clearConfirm': 'Warning: This will permanently delete all data. Are you sure?',
        'labelWorkspaces': 'Workspaces', 'labelTasks': 'Tasks', 'labelNotes': 'Notes',
        'labelCompleted': 'Completed', 'labelOverdue': 'Overdue',
        'aiThinking': 'Agent is thinking...', 'aiSlowWarning': 'Still working — complex requests take 20-30 seconds...',
        'noTasks': '✨ No tasks yet — ask me to plan your day!',
        'noNotes': '📝 No notes yet — ask me to research something!',
        'noWorkspaces': '📁 No workspaces yet — ask me to create a project!',
        'taskSearch': '🔍 Search tasks...', 'noteSearch': '🔍 Search notes...',
    },
    'ar': {
        'tasksTitle': 'المهام', 'notesTitle': 'ملاحظات', 'workspacesTitle': 'مساحات العمل',
        'sendBtn': 'إرسال', 'placeholder': 'اكتب مهمة، ملاحظة، أو استفسار...',
        'modelOnline': 'متصل', 'modelOffline': 'وضع عدم الاتصال', 'clearBtnText': 'مسح',
        'deleteConfirm': 'هل أنت متأكد من حذف هذا العنصر؟',
        'clearConfirm': 'تحذير: سيتم حذف جميع البيانات نهائياً. هل أنت متأكد؟',
        'labelWorkspaces': 'المساحات', 'labelTasks': 'المهام', 'labelNotes': 'الملاحظات',
        'labelCompleted': 'المكتملة', 'labelOverdue': 'المتأخرة',
        'aiThinking': 'العميل يفكر...', 'aiSlowWarning': 'لا يزال يعمل...',
        'noTasks': '✨ لا مهام بعد — اطلب مني تخطيط يومك!',
        'noNotes': '📝 لا ملاحظات بعد — اطلب مني البحث عن شيء!',
        'noWorkspaces': '📁 لا مساحات بعد — اطلب مني إنشاء مشروع!',
        'taskSearch': '🔍 بحث في المهام...', 'noteSearch': '🔍 بحث في الملاحظات...',
    }
};

const TOOL_LABELS = {
    'db_create_task':            { icon: '✅', label: 'Creating task' },
    'db_create_subtask':         { icon: '🔹', label: 'Creating subtask' },
    'db_get_subtasks':           { icon: '📋', label: 'Loading subtasks' },
    'db_complete_all_subtasks':  { icon: '🏁', label: 'Completing all subtasks' },
    'db_complete_task':          { icon: '🏁', label: 'Completing task' },
    'db_update_task':            { icon: '✏️', label: 'Updating task' },
    'db_delete_item':            { icon: '🗑️', label: 'Deleting item' },
    'db_create_note':            { icon: '📝', label: 'Saving note' },
    'db_update_note':            { icon: '✏️', label: 'Updating note' },
    'db_create_workspace':       { icon: '📁', label: 'Creating workspace' },
    'db_create_space':           { icon: '🗂️', label: 'Creating space' },
    'db_update_workspace_color': { icon: '🎨', label: 'Setting workspace color' },
    'db_link_note_to_task':      { icon: '🔗', label: 'Linking note to task' },
    'db_check_task_blocked':     { icon: '🔒', label: 'Checking dependencies' },
    'db_create_project_plan':    { icon: '🗺️', label: 'Building complex plan' },
    'db_find_task_id':           { icon: '🎯', label: 'Finding specific task' },
    'tool_web_search':           { icon: '🌐', label: 'Searching web' },
    'tool_search_my_data':       { icon: '🔍', label: 'Searching your data' },
    'tool_check_schedule':       { icon: '📅', label: 'Checking schedule' },
    'tool_get_context':          { icon: '🧠', label: 'Loading context' },
    'tool_daily_briefing':       { icon: '☀️', label: 'Generating briefing' },
    'tool_save_memory':          { icon: '💾', label: 'Saving to memory' },
    'tool_get_memory':           { icon: '🧩', label: 'Reading memory' },
    'tool_analyze_productivity': { icon: '📊', label: 'Analyzing productivity' },
};

function getWorkspaceName(id) {
    if (!id) return null;
    const ws = allWorkspaces.find(w => w.id === id);
    return ws ? ws.name : `WS#${id}`;
}

function getSpaceName(id) {
    if (!id) return null;
    const sp = allSpaces.find(s => s.id === id);
    return sp ? sp.name : `Space#${id}`;
}

async function initializeApp() {
    await checkModelStatus();
    await setLanguage('en');
    startExampleRotation();
    initializeVoiceRecognition();
    document.getElementById('welcomeTime').innerText = formatTime(new Date());
    await loadWelcomeMessage();
    await updateItems();
    setInterval(checkModelStatus, 30000);

    const fileInput = document.getElementById('fileInput');
    if (fileInput) {
        fileInput.addEventListener('change', async function (e) {
            const file = e.target.files[0];
            if (!file) return;
            addMessage(`📂 Uploading: ${escapeHtml(file.name)}...`, true, currentLanguage);
            showThinking();
            const formData = new FormData();
            formData.append('file', file);
            const instruction = document.getElementById('messageInput').value;
            if (instruction) formData.append('message', instruction);
            try {
                const response = await fetch('/api/upload', { method: 'POST', body: formData });
                const data = await response.json();
                hideThinking();
                if (data.success) {
                    renderAgentResponse(data.data);
                    await updateItems();
                } else {
                    addMessage('❌ Error: ' + escapeHtml(data.error?.message || 'Unknown'), false, 'en');
                }
            } catch (err) {
                hideThinking();
                addMessage('❌ Network error uploading file.', false, 'en');
            }
            fileInput.value = '';
        });
    }
}

function formatTime(date) {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

async function loadWelcomeMessage() {
    try {
        const res = await fetch('/api/welcome');
        const data = await res.json();
        const msg = data.data?.message || data.message || '';
        const el = document.getElementById('welcomeMessage');
        if (el && msg) {
            el.innerHTML = escapeHtml(msg)
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                .replace(/\*(.*?)\*/g, '<em>$1</em>')
                .replace(/\n/g, '<br>');
        }
    } catch (e) { console.warn("Welcome load failed:", e); }
}

async function setLanguage(lang) {
    currentLanguage = lang;
    document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
    document.getElementById('englishBtn').classList.toggle('active', lang === 'en');
    document.getElementById('arabicBtn').classList.toggle('active', lang === 'ar');
    const t = uiText[lang];
    document.getElementById('tasksTitle').innerText = t.tasksTitle;
    document.getElementById('notesTitle').innerText = t.notesTitle;
    document.getElementById('workspacesTitle').innerText = t.workspacesTitle;
    document.getElementById('sendText').innerText = t.sendBtn;
    document.getElementById('messageInput').placeholder = t.placeholder;
    document.getElementById('clearBtnText').innerText = t.clearBtnText;
    document.getElementById('labelWorkspaces').innerText = t.labelWorkspaces;
    document.getElementById('labelTasks').innerText = t.labelTasks;
    document.getElementById('labelNotes').innerText = t.labelNotes;
    document.getElementById('labelCompleted').innerText = t.labelCompleted;
    document.getElementById('labelOverdue').innerText = t.labelOverdue;
    document.getElementById('typingLabel').innerText = t.aiThinking;
    document.getElementById('taskSearch').placeholder = t.taskSearch;
    document.getElementById('noteSearch').placeholder = t.noteSearch;
    if (recognition) {
        recognition.lang = lang === 'ar' ? 'ar' : 'en-US';
    }
    try {
        const response = await fetch(`/api/config?lang=${lang}`);
        const config = await response.json();
        const configData = config.data || config;
        examples = configData.examples || [];
        if (examples.length > 0) document.getElementById('exampleChip').innerText = examples[0];
    } catch (e) { console.error("Config load failed:", e); }
}

async function updateItems() {
    await fetchTasks();
    await Promise.all([fetchWorkspaces(), fetchNotes(), fetchAnalytics()]);
}

async function fetchWorkspaces() {
    try {
        const [wsRes, spRes] = await Promise.all([
            fetch('/api/workspaces'),
            fetch('/api/spaces')
        ]);
        allWorkspaces = await wsRes.json();
        const spacesRaw = await spRes.json();
        allWorkspaces = allWorkspaces.data || allWorkspaces;
        allSpaces = spacesRaw.data || spacesRaw;

        const container = document.getElementById('workspacesContainer');
        document.getElementById('workspacesCount').innerText = allWorkspaces.length;
        container.innerHTML = '';

        if (!allWorkspaces.length) {
            container.innerHTML = `<div class="empty-state">${uiText[currentLanguage].noWorkspaces}</div>`;
            return;
        }

        allWorkspaces.forEach(ws => {
            const wsSpaces = allSpaces.filter(s => s.workspace_id === ws.id);
            const wsEl = document.createElement('div');
            wsEl.className = 'workspace-card';
            wsEl.style.borderLeftColor = ws.color || 'var(--accent-color)';

            const spacesHtml = wsSpaces.map(sp => {
                const spaceTasks = allTasks.filter(t => t.space_id === sp.id && !t.parent_id);
                const tasksHtml = spaceTasks.map(t => renderTaskTreeItem(t)).join('');
                const taskCount = spaceTasks.length;
                return `
                <div class="space-row">
                    <div class="space-header" onclick="toggleAccordion('space-${sp.id}')">
                        <span class="space-dot" style="background:${sp.color || ws.color || 'var(--accent-color)'}"></span>
                        <span class="space-name">${escapeHtml(sp.name)}</span>
                        <span class="space-count">${taskCount} task${taskCount !== 1 ? 's' : ''}</span>
                        <span class="accordion-arrow" id="arrow-space-${sp.id}">▶</span>
                    </div>
                    <div class="accordion-body" id="space-${sp.id}" style="display:none;">
                        ${tasksHtml || '<div class="empty-space-msg">No tasks in this space yet</div>'}
                    </div>
                </div>`;
            }).join('');

            const unspacedTasks = allTasks.filter(t => t.workspace_id === ws.id && !t.space_id && !t.parent_id);
            const unspacedHtml = unspacedTasks.map(t => renderTaskTreeItem(t)).join('');

            const totalTasks = allTasks.filter(t => t.workspace_id === ws.id && !t.parent_id).length;

            wsEl.innerHTML = `
                <div class="workspace-header" onclick="toggleAccordion('ws-${ws.id}')">
                    <div class="workspace-left">
                        <span class="accordion-arrow" id="arrow-ws-${ws.id}">▶</span>
                        <span class="workspace-title">${escapeHtml(ws.name)}</span>
                        <span class="ws-counts">${wsSpaces.length} space${wsSpaces.length !== 1 ? 's' : ''} · ${totalTasks} task${totalTasks !== 1 ? 's' : ''}</span>
                    </div>
                    <div class="workspace-actions" onclick="event.stopPropagation()">
                        <input type="color" class="color-picker" value="${escapeHtml(ws.color || '#8A2BE2')}"
                               onchange="updateWorkspaceColor(${ws.id}, this.value)" title="Change color">
                        <button class="delete-btn" onclick="deleteItem('workspaces',${ws.id})" title="Delete workspace">×</button>
                    </div>
                </div>
                ${ws.description ? `<div class="workspace-desc">${escapeHtml(ws.description)}</div>` : ''}
                <div class="accordion-body" id="ws-${ws.id}" style="display:none;">
                    ${spacesHtml}
                    ${unspacedHtml ? `<div class="unspaced-tasks">${unspacedHtml}</div>` : ''}
                    ${!wsSpaces.length && !unspacedTasks.length ? '<div class="empty-space-msg">No spaces or tasks yet</div>' : ''}
                </div>
            `;
            container.appendChild(wsEl);
        });
    } catch (e) { console.error("fetchWorkspaces:", e); }
}

function toggleAccordion(id) {
    const body = document.getElementById(id);
    const arrow = document.getElementById('arrow-' + id);
    if (!body) return;
    const isOpen = body.style.display !== 'none';
    body.style.display = isOpen ? 'none' : 'block';
    if (arrow) arrow.textContent = isOpen ? '▶' : '▼';
}

function renderTaskTreeItem(task) {
    const today = new Date().toISOString().split('T')[0];
    const isCompleted = task.completed;
    const isOverdue = !isCompleted && task.due_date && task.due_date < today;
    const isToday = !isCompleted && task.due_date === today;

    const subtasks = allTasks.filter(t => t.parent_id === task.id);
    const doneSubtasks = subtasks.filter(t => t.completed).length;
    const progressHtml = subtasks.length > 0 ? `
        <div class="subtask-progress-bar">
            <div class="subtask-progress-fill" style="width:${Math.round(doneSubtasks/subtasks.length*100)}%"></div>
        </div>
        <span class="subtask-count">${doneSubtasks}/${subtasks.length} subtasks</span>` : '';

    const subtasksHtml = subtasks.map(st => `
        <div class="subtask-item ${st.completed ? 'subtask-done' : ''}">
            <input type="checkbox" ${st.completed ? 'checked' : ''}
                   onchange="toggleTaskComplete(${st.id}, this.checked)">
            <span class="subtask-title">${escapeHtml(st.title)}</span>
        </div>`).join('');

    const hasSubtasks = subtasks.length > 0;

    return `
    <div class="task-tree-item ${isCompleted ? 'task-done' : ''} ${isOverdue ? 'task-overdue' : ''}">
        <div class="task-tree-header">
            <div class="task-tree-left">
                ${hasSubtasks ? `<span class="task-expand-btn" id="arrow-task-sub-${task.id}" onclick="toggleAccordion('task-sub-${task.id}')">▶</span>` : '<span class="task-expand-spacer"></span>'}
                <input type="checkbox" class="task-checkbox" ${isCompleted ? 'checked' : ''}
                       onchange="toggleTaskComplete(${task.id}, this.checked)">
                <span class="task-tree-title ${isCompleted ? 'task-title-done' : ''}">
                    ${escapeHtml(task.title)}
                </span>
            </div>
            <div class="task-tree-badges">
                ${isOverdue ? '<span class="urgency-badge overdue-badge">OVERDUE</span>' : ''}
                ${isToday ? '<span class="urgency-badge today-badge">TODAY</span>' : ''}
                ${task.recurrence ? `<span class="recurrence-badge">↻ ${escapeHtml(task.recurrence)}</span>` : ''}
                ${task.priority === 'high' && !isCompleted ? '<span class="priority-badge high-badge">HIGH</span>' : ''}
                <button class="delete-btn-sm" onclick="deleteItem('tasks',${task.id})">×</button>
            </div>
        </div>
        ${task.due_date ? `<div class="task-tree-meta">📅 ${escapeHtml(task.due_date)}${task.due_time ? ' ' + escapeHtml(task.due_time) : ''}</div>` : ''}
        ${progressHtml}
        ${hasSubtasks ? `
        <div class="accordion-body subtask-list" id="task-sub-${task.id}" style="display:none;">
            ${subtasksHtml}
        </div>` : ''}
    </div>`;
}

async function updateWorkspaceColor(wsId, color) {
    try {
        await fetch(`/api/workspaces/${wsId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ color })
        });
        await fetchWorkspaces();
    } catch (e) { console.error("updateWorkspaceColor:", e); }
}

async function fetchTasks() {
    try {
        const raw = await (await fetch('/api/tasks?include_subtasks=true')).json();
        allTasks = raw.data || raw;
        renderTasks(allTasks.filter(t => !t.parent_id));
    } catch (e) { console.error("fetchTasks:", e); }
}

function renderTasks(tasks) {
    const container = document.getElementById('tasksContainer');
    document.getElementById('tasksCount').innerText = tasks.filter(t => !t.parent_id).length;
    container.innerHTML = '';
    const topLevel = tasks.filter(t => !t.parent_id);
    if (!topLevel.length) {
        container.innerHTML = `<div class="empty-state">${uiText[currentLanguage].noTasks}</div>`;
        return;
    }
    const today = new Date().toISOString().split('T')[0];
    topLevel.forEach(task => {
        const isCompleted = task.completed;
        const isOverdue = !isCompleted && task.due_date && task.due_date < today;
        const isToday = !isCompleted && task.due_date === today;

        const el = document.createElement('div');
        el.className = `task-card ${task.priority || 'medium'}-priority${isCompleted ? ' completed-task' : ''}${isOverdue ? ' overdue-task' : ''}`;

        const wsName = getWorkspaceName(task.workspace_id);
        const spName = getSpaceName(task.space_id);
        const wsBadge = wsName ? `<span class="workspace-tag" title="Workspace">${escapeHtml(wsName)}</span>` : '';
        const spBadge = spName ? `<span class="space-tag" title="Space">${escapeHtml(spName)}</span>` : '';

        const urgencyBadge = isOverdue ? `<span class="urgency-badge overdue-badge">OVERDUE</span>`
                           : isToday  ? `<span class="urgency-badge today-badge">TODAY</span>` : '';
        const recurrenceBadge = task.recurrence ? `<span class="recurrence-badge">↻ ${escapeHtml(task.recurrence)}</span>` : '';
        const blockedBadge = task.depends_on && !isCompleted ? `<span class="blocked-badge">🔒 Blocked</span>` : '';
        const linkedNote = task.linked_note_id ? `<span class="linked-badge">📝 Note linked</span>` : '';

        // Added full subtask integration
        const subtasks = allTasks.filter(t => t.parent_id === task.id);
        const doneSubtasks = subtasks.filter(t => t.completed).length;
        
        const subtaskBadge = subtasks.length > 0
            ? `<span class="subtask-badge" style="cursor:pointer;" onclick="toggleAccordion('flat-sub-${task.id}')">
                ${doneSubtasks}/${subtasks.length} steps ▼
               </span>` 
            : '';

        const subtasksHtml = subtasks.length > 0 ? `
            <div class="accordion-body subtask-list" id="flat-sub-${task.id}" style="display:none; border-top: 1px solid var(--border-color); margin-top: 10px; padding-top: 10px;">
                ${subtasks.map(st => `
                    <div class="subtask-item ${st.completed ? 'subtask-done' : ''}">
                        <input type="checkbox" ${st.completed ? 'checked' : ''} onchange="toggleTaskComplete(${st.id}, this.checked)">
                        <span class="subtask-title">${escapeHtml(st.title)}</span>
                        <button class="delete-btn-sm" onclick="deleteItem('tasks',${st.id})">×</button>
                    </div>
                `).join('')}
            </div>` : '';

        el.innerHTML = `
            <div class="task-header">
                <div class="task-left">
                    <input type="checkbox" class="task-checkbox" ${isCompleted ? 'checked' : ''}
                           onchange="toggleTaskComplete(${task.id}, this.checked)">
                    <span class="task-title ${isCompleted ? 'task-title-done' : ''}">
                        ${escapeHtml(task.title)}
                    </span>
                </div>
                <button class="delete-btn" onclick="deleteItem('tasks',${task.id})">×</button>
            </div>
            <div class="task-badges">
                ${wsBadge}${spBadge}${urgencyBadge}${recurrenceBadge}${blockedBadge}${linkedNote}${subtaskBadge}
            </div>
            ${task.description ? `<div class="task-desc">${escapeHtml(task.description)}</div>` : ''}
            <div class="task-meta">
                ${task.due_date ? `<div class="meta-item">📅 ${escapeHtml(task.due_date)}</div>` : ''}
                ${task.due_time ? `<div class="meta-item">⏰ ${escapeHtml(task.due_time)}</div>` : ''}
                ${isCompleted ? `<div class="meta-item completed-meta">✅ Done</div>` : ''}
            </div>
            ${subtasksHtml}
        `;
        container.appendChild(el);
    });
}

async function fetchNotes() {
    try {
        const raw = await (await fetch('/api/notes')).json();
        allNotes = raw.data || raw;
        renderNotes(allNotes);
    } catch (e) { console.error("fetchNotes:", e); }
}

function renderNotes(notes) {
    const container = document.getElementById('notesContainer');
    document.getElementById('notesCount').innerText = notes.length;
    container.innerHTML = '';
    if (!notes.length) {
        container.innerHTML = `<div class="empty-state">${uiText[currentLanguage].noNotes}</div>`;
        return;
    }
    notes.forEach(note => {
        const el = document.createElement('div');
        el.className = 'note-card';

        const wsName = getWorkspaceName(note.workspace_id);
        const spName = getSpaceName(note.space_id);
        const wsBadge = wsName ? `<span class="workspace-tag">${escapeHtml(wsName)}</span>` : '';
        const spBadge = spName ? `<span class="space-tag">${escapeHtml(spName)}</span>` : '';
        const linkedTask = note.linked_task_id ? `<span class="linked-badge">✅ Task linked</span>` : '';

        el.innerHTML = `
            <div class="note-header">
                <span class="note-title">${escapeHtml(note.title)}</span>
                <div class="note-actions">
                    <a href="/api/export/pdf/${note.id}" class="export-btn" title="Export PDF">📄</a>
                    <button class="delete-btn" onclick="deleteItem('notes',${note.id})">×</button>
                </div>
            </div>
            <div class="note-badges">${wsBadge}${spBadge}${linkedTask}</div>
            <div class="note-content">${escapeHtml(note.content)}</div>
            <div class="note-footer">
                <span class="note-category">${escapeHtml(note.category || 'General')}</span>
                <span>Words: ${note.word_count || 0}</span>
                <span>${note.created_at ? note.created_at.slice(0,10) : ''}</span>
            </div>
        `;
        container.appendChild(el);
    });
}

async function fetchAnalytics() {
    try {
        const raw = await (await fetch('/api/analytics')).json();
        const stats = raw.data || raw;
        document.getElementById('totalWorkspaces').innerText = stats.total_workspaces || 0;
        document.getElementById('totalTasks').innerText = stats.total_tasks || 0;
        document.getElementById('totalNotes').innerText = stats.total_notes || 0;
        document.getElementById('completedTasks').innerText = stats.completed_tasks || 0;
        const overdueEl = document.getElementById('overdueTasks');
        overdueEl.innerText = stats.overdue_tasks || 0;
        overdueEl.style.color = (stats.overdue_tasks > 0) ? 'var(--danger-color)' : 'var(--text-main)';
    } catch (e) { console.error("fetchAnalytics:", e); }
}

function filterItems(type) {
    if (type === 'tasks') {
        const q = document.getElementById('taskSearch').value.toLowerCase();
        const filtered = q ? allTasks.filter(t =>
            !t.parent_id && (
                t.title.toLowerCase().includes(q) ||
                (t.description || '').toLowerCase().includes(q)
            )
        ) : allTasks.filter(t => !t.parent_id);
        renderTasks(filtered);
    } else {
        const q = document.getElementById('noteSearch').value.toLowerCase();
        const filtered = q ? allNotes.filter(n =>
            n.title.toLowerCase().includes(q) ||
            (n.content || '').toLowerCase().includes(q)
        ) : allNotes;
        renderNotes(filtered);
    }
}

async function toggleTaskComplete(taskId, completed) {
    try {
        const res = await fetch(`/api/tasks/${taskId}/complete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ completed })
        });
        const data = await res.json();
        if (data.success || data.data) {
            const analytics = data.data?.analytics || data.analytics;
            if (analytics) {
                document.getElementById('completedTasks').innerText = analytics.completed_tasks || 0;
                const ov = document.getElementById('overdueTasks');
                ov.innerText = analytics.overdue_tasks || 0;
                ov.style.color = (analytics.overdue_tasks > 0) ? 'var(--danger-color)' : 'var(--text-main)';
            }
            await updateItems();
        }
    } catch (e) { console.error("toggleTaskComplete:", e); }
}

async function toggleMemoryPanel() {
    const panel = document.getElementById('memoryPanel');
    const overlay = document.getElementById('memoryOverlay');
    const isVisible = panel.style.display !== 'none';
    panel.style.display = isVisible ? 'none' : 'flex';
    overlay.style.display = isVisible ? 'none' : 'block';
    if (!isVisible) await loadMemoryPanel();
}

async function loadMemoryPanel() {
    try {
        const raw = await (await fetch('/api/memory')).json();
        const memory = raw.data || raw;
        const list = document.getElementById('memoryList');
        list.innerHTML = '';
        if (!Object.keys(memory).length) {
            list.innerHTML = '<p style="color:var(--text-muted);font-size:0.9rem;">No memories yet.</p>';
            return;
        }
        Object.entries(memory).forEach(([key, value]) => {
            const row = document.createElement('div');
            row.className = 'memory-row';
            row.innerHTML = `
                <div class="memory-kv">
                    <span class="memory-key">${escapeHtml(key)}</span>
                    <span class="memory-value">${escapeHtml(value)}</span>
                </div>
                <button class="delete-btn" onclick="deleteMemoryEntry('${escapeHtml(key)}')">×</button>
            `;
            list.appendChild(row);
        });
    } catch (e) { console.error("loadMemoryPanel:", e); }
}

async function addMemoryEntry() {
    const key = document.getElementById('memoryKeyInput').value.trim();
    const value = document.getElementById('memoryValueInput').value.trim();
    if (!key || !value) return;
    await fetch('/api/memory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key, value })
    });
    document.getElementById('memoryKeyInput').value = '';
    document.getElementById('memoryValueInput').value = '';
    await loadMemoryPanel();
}

async function deleteMemoryEntry(key) {
    await fetch(`/api/memory/${encodeURIComponent(key)}`, { method: 'DELETE' });
    await loadMemoryPanel();
}

async function toggleAnalytics() {
    const panel = document.getElementById('analyticsPanel');
    const overlay = document.getElementById('analyticsOverlay');
    const isVisible = panel.style.display !== 'none';
    panel.style.display = isVisible ? 'none' : 'flex';
    overlay.style.display = isVisible ? 'none' : 'block';
    if (!isVisible) await loadAnalytics();
}

async function loadAnalytics() {
    const content = document.getElementById('analyticsContent');
    content.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:30px;">Loading analytics...</p>';
    try {
        const raw = await (await fetch('/api/smart-analytics')).json();
        const data = raw.data || raw;

        if (!data.total_tasks) {
            content.innerHTML = '<div class="analytics-empty">📊 No data yet — start creating tasks to see your productivity patterns.</div>';
            return;
        }

        const maxHour = Math.max(...(data.hourly_activity || []).map(h => h.count), 1);
        const hourBars = Array.from({length: 24}, (_, h) => {
            const found = (data.hourly_activity || []).find(x => x.hour === h);
            const count = found ? found.count : 0;
            const height = Math.round((count / maxHour) * 40);
            return `<div class="hour-bar-wrap" title="${h}:00 — ${count} tasks">
                <div class="hour-bar" style="height:${height}px;background:${count > 0 ? 'var(--accent-color)' : '#e5e7eb'}"></div>
                <span class="hour-label">${h % 6 === 0 ? h : ''}</span>
            </div>`;
        }).join('');

        const maxWeek = Math.max(...(data.weekly_trend || []).map(d => d.created), 1);
        const weekBars = (data.weekly_trend || []).map(d => {
            const createdH = Math.round((d.created / maxWeek) * 50);
            const doneH = Math.round((d.completed / maxWeek) * 50);
            return `<div class="week-bar-wrap" title="${d.day}: ${d.created} created, ${d.completed} done">
                <div style="display:flex;align-items:flex-end;gap:2px;height:50px;">
                    <div style="width:10px;height:${createdH}px;background:#c4b5fd;border-radius:2px 2px 0 0;"></div>
                    <div style="width:10px;height:${doneH}px;background:var(--accent-color);border-radius:2px 2px 0 0;"></div>
                </div>
                <span class="hour-label">${d.day ? d.day.slice(5) : ''}</span>
            </div>`;
        }).join('');

        const catBars = (data.category_breakdown || []).map(c => {
            const color = c.rate >= 70 ? '#10b981' : c.rate >= 40 ? '#f59e0b' : '#ef4444';
            return `<div class="cat-row">
                <span class="cat-label">${escapeHtml(c.category)}</span>
                <div class="cat-bar-bg"><div class="cat-bar-fill" style="width:${c.rate}%;background:${color}"></div></div>
                <span class="cat-rate">${c.rate}%</span>
                <span class="cat-count">(${c.completed}/${c.total})</span>
            </div>`;
        }).join('');

        const priRows = ['high','medium','low'].map(p => {
            const s = data.priority_breakdown?.[p] || {total:0,completed:0,rate:0};
            const color = p === 'high' ? '#ef4444' : p === 'medium' ? '#f59e0b' : '#10b981';
            return `<div class="cat-row">
                <span class="cat-label" style="color:${color};font-weight:700;">${p}</span>
                <div class="cat-bar-bg"><div class="cat-bar-fill" style="width:${s.rate}%;background:${color}"></div></div>
                <span class="cat-rate">${s.rate}%</span>
                <span class="cat-count">(${s.completed}/${s.total})</span>
            </div>`;
        }).join('');

        const procRows = (data.procrastination_by_category || []).length
            ? data.procrastination_by_category.map(p =>
                `<div class="proc-row"><span>${escapeHtml(p.category)}</span><span class="proc-count">${p.overdue} overdue</span></div>`
              ).join('')
            : '<div style="color:var(--success-color);font-size:0.9rem;">🎉 No overdue tasks by category!</div>';

        const wsRows = (data.workspace_productivity || []).filter(w => w.total > 0).map(w =>
            `<div class="cat-row">
                <span class="cat-label">${escapeHtml(w.name)}</span>
                <div class="cat-bar-bg"><div class="cat-bar-fill" style="width:${w.rate}%;background:var(--accent-color)"></div></div>
                <span class="cat-rate">${w.rate}%</span>
                <span class="cat-count">(${w.completed}/${w.total})</span>
            </div>`
        ).join('') || '<div style="color:var(--text-muted);font-size:0.9rem;">No workspace data yet.</div>';

        const avgTime = data.avg_completion_time_hours != null
            ? (data.avg_completion_time_hours < 24 ? `${data.avg_completion_time_hours}h` : `${Math.round(data.avg_completion_time_hours/24)}d`)
            : 'N/A';

        const subtaskRow = data.subtask_total > 0 ? `
            <div class="an-card">
                <div class="an-value">${data.subtask_completion_rate || 0}%</div>
                <div class="an-label">Subtask Rate</div>
            </div>` : '';

        content.innerHTML = `
            <div class="an-grid">
                <div class="an-card accent"><div class="an-value">${data.completion_rate}%</div><div class="an-label">Completion Rate</div></div>
                <div class="an-card ${data.current_streak_days > 0 ? 'success' : ''}"><div class="an-value">${data.current_streak_days}🔥</div><div class="an-label">Day Streak</div></div>
                <div class="an-card"><div class="an-value">${data.completed_tasks}/${data.total_tasks}</div><div class="an-label">Tasks Done</div></div>
                <div class="an-card ${data.overdue_tasks > 0 ? 'danger' : 'success'}"><div class="an-value">${data.overdue_tasks}</div><div class="an-label">Overdue</div></div>
                <div class="an-card"><div class="an-value">${avgTime}</div><div class="an-label">Avg. Completion</div></div>
                <div class="an-card"><div class="an-value">${data.total_notes}</div><div class="an-label">Notes</div></div>
                ${subtaskRow}
            </div>
            <div class="an-insights">
                <div class="an-insight">⏰ <strong>Most active:</strong> ${escapeHtml(data.peak_creation_hour)}</div>
                <div class="an-insight">📅 <strong>Busiest day:</strong> ${escapeHtml(data.busiest_day_of_week)}</div>
                <div class="an-insight">📝 <strong>Top note category:</strong> ${escapeHtml(data.top_note_category)}</div>
                <div class="an-insight">✍️ <strong>Avg note length:</strong> ${data.avg_note_words} words</div>
            </div>
            <div class="an-section">
                <div class="an-section-title">🕐 Task Creation by Hour</div>
                <div class="hour-chart">${hourBars}</div>
                <div class="an-hint">Tallest bars = when you create most tasks</div>
            </div>
            ${data.weekly_trend?.length ? `
            <div class="an-section">
                <div class="an-section-title">📆 Last 7 Days — Created vs Completed</div>
                <div class="week-legend">
                    <span><span style="background:#c4b5fd" class="legend-dot"></span>Created</span>
                    <span><span style="background:var(--accent-color)" class="legend-dot"></span>Completed</span>
                </div>
                <div class="hour-chart">${weekBars}</div>
            </div>` : ''}
            ${catBars ? `<div class="an-section"><div class="an-section-title">🏷️ Completion by Category</div><div class="cat-list">${catBars}</div></div>` : ''}
            <div class="an-section"><div class="an-section-title">🎯 Completion by Priority</div><div class="cat-list">${priRows}</div></div>
            ${wsRows ? `<div class="an-section"><div class="an-section-title">📁 Workspace Productivity</div><div class="cat-list">${wsRows}</div></div>` : ''}
            <div class="an-section"><div class="an-section-title">😬 Procrastination Index</div><div class="proc-list">${procRows}</div></div>
            <div class="an-hint" style="text-align:center;margin-top:8px;">💡 Ask the agent: "Analyze my productivity" for AI insight</div>
        `;
    } catch (e) {
        content.innerHTML = '<p style="color:var(--danger-color);">Could not load analytics.</p>';
        console.error(e);
    }
}

async function toggleBriefing() {
    const panel = document.getElementById('briefingPanel');
    const overlay = document.getElementById('briefingOverlay');
    const isVisible = panel.style.display !== 'none';
    panel.style.display = isVisible ? 'none' : 'flex';
    overlay.style.display = isVisible ? 'none' : 'block';
    if (!isVisible) await loadBriefing();
}

async function loadBriefing() {
    const content = document.getElementById('briefingContent');
    content.innerHTML = '<p style="color:var(--text-muted);">Loading...</p>';
    try {
        const raw = await (await fetch('/api/briefing')).json();
        const data = raw.data || raw;
        const today = data.today || [];
        const overdue = data.overdue || [];
        const upcoming = data.upcoming || [];
        const memory = data.memory || {};

        let html = `<div class="briefing-date">${escapeHtml(data.day || '')}</div>`;

        if (overdue.length) {
            html += `<div class="briefing-section overdue-section">
                <h4>⚠️ Overdue (${overdue.length})</h4>
                ${overdue.map(t => `<div class="briefing-task overdue-item">• ${escapeHtml(t.title)} <span class="briefing-date-tag">${t.due_date}</span></div>`).join('')}
            </div>`;
        }

        html += `<div class="briefing-section"><h4>📅 Today (${today.length})</h4>`;
        if (today.length) {
            html += today.map(t => {
                const time = t.due_time ? `<span class="briefing-time">${t.due_time}</span>` : '';
                const rec = t.recurrence ? `<span class="recurrence-badge">↻</span>` : '';
                return `<div class="briefing-task">☐ ${escapeHtml(t.title)} ${time}${rec}</div>`;
            }).join('');
        } else {
            html += '<div style="color:var(--text-muted);font-size:0.9rem;padding:8px 0;">Clear! Great day to get ahead.</div>';
        }
        html += '</div>';

        if (upcoming.length) {
            html += `<div class="briefing-section">
                <h4>🔜 Next 3 Days (${upcoming.length})</h4>
                ${upcoming.map(t => `<div class="briefing-task">◦ ${escapeHtml(t.title)} <span class="briefing-date-tag">${t.due_date}</span></div>`).join('')}
            </div>`;
        }

        const highlights = ['goal', 'goal_2026', 'exam_date', 'current_project'];
        const memHighlights = highlights.filter(k => memory[k]);
        if (memHighlights.length) {
            html += `<div class="briefing-section">
                <h4>💡 Your Focus</h4>
                ${memHighlights.map(k => `<div class="briefing-task">• <strong>${escapeHtml(k)}:</strong> ${escapeHtml(memory[k])}</div>`).join('')}
            </div>`;
        }

        content.innerHTML = html;
    } catch (e) {
        content.innerHTML = '<p style="color:var(--danger-color);">Could not load briefing.</p>';
    }
}

function exportTodayPDF() {
    window.open('/api/export/tasks/today', '_blank');
}

function autoResize(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 150) + 'px';
}

function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

function useExample() {
    document.getElementById('messageInput').value = document.getElementById('exampleChip').innerText;
    sendMessage();
}

function startExampleRotation() {
    if (exampleInterval) clearInterval(exampleInterval);
    exampleInterval = setInterval(() => {
        if (examples.length > 0) {
            currentExampleIndex = (currentExampleIndex + 1) % examples.length;
            document.getElementById('exampleChip').innerText = examples[currentExampleIndex];
        }
    }, 4000);
}

function addMessage(text, isUser, lang) {
    const history = document.getElementById('chatHistory');
    const typingEl = document.getElementById('typingIndicator');
    const wrapper = document.createElement('div');
    wrapper.className = `message-wrapper ${isUser ? 'user-wrapper' : 'bot-wrapper'}`;

    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${isUser ? 'user-message' : 'bot-message'}`;
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.dir = lang === 'ar' ? 'rtl' : 'ltr';
    contentDiv.innerHTML = escapeHtml(text)
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/\n/g, '<br>');
    msgDiv.appendChild(contentDiv);

    const timeEl = document.createElement('span');
    timeEl.className = 'msg-time';
    timeEl.innerText = formatTime(new Date());

    wrapper.appendChild(msgDiv);
    wrapper.appendChild(timeEl);
    history.insertBefore(wrapper, typingEl);
    history.scrollTop = history.scrollHeight;
}

function renderAgentResponse(result) {
    const history = document.getElementById('chatHistory');
    const typingEl = document.getElementById('typingIndicator');

    const toolCalls = (result.tool_events || []).filter(e => e.type === 'tool_call');
    if (toolCalls.length > 0) {
        const thinkingDiv = document.createElement('div');
        thinkingDiv.className = 'message bot-message agent-thinking';
        const steps = toolCalls.map(e => {
            const info = TOOL_LABELS[e.name] || { icon: '⚙️', label: e.name };
            const keyArg = e.args.title || e.args.query || e.args.name || e.args.key || '';
            return `<div class="tool-step">
                <span class="tool-icon">${info.icon}</span>
                <span class="tool-label">${escapeHtml(info.label)}</span>
                ${keyArg ? `<span class="tool-arg">"${escapeHtml(String(keyArg))}"</span>` : ''}
            </div>`;
        }).join('');
        thinkingDiv.innerHTML = `<div class="agent-steps">${steps}</div>`;
        history.insertBefore(thinkingDiv, typingEl);
    }

    if (result.response_message || result.message) {
        addMessage(result.response_message || result.message, false, currentLanguage);
    }
    history.scrollTop = history.scrollHeight;
}

function showThinking() {
    document.getElementById('sendText').style.display = 'none';
    document.getElementById('sendLoader').style.display = 'block';
    document.getElementById('sendButton').disabled = true;
    const typingEl = document.getElementById('typingIndicator');
    typingEl.style.display = 'flex';
    document.getElementById('chatHistory').scrollTop = document.getElementById('chatHistory').scrollHeight;
    sendTimeout = setTimeout(() => {
        document.getElementById('typingLabel').innerText = uiText[currentLanguage].aiSlowWarning;
    }, 15000);
}

function hideThinking() {
    document.getElementById('sendText').style.display = 'inline';
    document.getElementById('sendLoader').style.display = 'none';
    document.getElementById('sendButton').disabled = false;
    document.getElementById('typingIndicator').style.display = 'none';
    document.getElementById('typingLabel').innerText = uiText[currentLanguage].aiThinking;
    if (sendTimeout) { clearTimeout(sendTimeout); sendTimeout = null; }
}

async function sendMessage() {
    const input = document.getElementById('messageInput');
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    input.style.height = 'auto';
    addMessage(text, true, currentLanguage);
    showThinking();
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, language: currentLanguage })
        });
        const data = await response.json();
        hideThinking();
        const result = data.data || data.result;
        if (result) {
            renderAgentResponse(result);
            await updateItems();
        } else {
            addMessage(currentLanguage === 'ar' ? 'عذرا، حدث خطأ.' : 'Sorry, an error occurred.', false, currentLanguage);
        }
    } catch (err) {
        hideThinking();
        addMessage(currentLanguage === 'ar' ? 'خطأ في الاتصال.' : 'Server connection error.', false, currentLanguage);
    }
}

async function deleteItem(type, id) {
    if (confirm(uiText[currentLanguage].deleteConfirm)) {
        try {
            await fetch(`/api/${type}/${id}`, { method: 'DELETE' });
            await updateItems();
        } catch (e) { alert('Failed to delete.'); }
    }
}

async function clearAll() {
    if (confirm(uiText[currentLanguage].clearConfirm)) {
        try {
            await fetch('/api/clear', { method: 'POST' });
            await updateItems();
            addMessage(currentLanguage === 'ar' ? 'تم مسح جميع البيانات.' : 'All data cleared.', false, currentLanguage);
        } catch (e) { alert('Failed to clear.'); }
    }
}

async function checkModelStatus() {
    try {
        const raw = await (await fetch('/api/status')).json();
        const data = raw.data || raw;
        const indicator = document.getElementById('statusIndicator');
        const text = document.getElementById('modelStatus');
        if (data.status === 'healthy') {
            indicator.className = 'status-indicator online';
            text.innerText = uiText[currentLanguage].modelOnline + ` (${data.model || 'AI'})`;
        } else {
            indicator.className = 'status-indicator';
            text.innerText = uiText[currentLanguage].modelOffline;
        }
    } catch (e) {
        document.getElementById('statusIndicator').className = 'status-indicator';
        document.getElementById('modelStatus').innerText = 'Disconnected';
    }
}

function initializeVoiceRecognition() {
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SR();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = 'en-US';
        recognition.onstart = () => { isListening = true; document.getElementById('voiceBtn').classList.add('recording'); };
        recognition.onresult = (e) => { document.getElementById('messageInput').value = e.results[0][0].transcript; sendMessage(); };
        recognition.onerror = () => stopVoice();
        recognition.onend = () => stopVoice();
    } else {
        document.getElementById('voiceBtn').style.display = 'none';
    }
}

function toggleVoice() {
    if (!recognition) return;
    if (isListening) {
        stopVoice();
    } else {
        recognition.lang = currentLanguage === 'ar' ? 'ar' : 'en-US';
        recognition.start();
    } 
}

function stopVoice() {
    if (recognition && isListening) {
        recognition.stop();
        isListening = false;
        document.getElementById('voiceBtn').classList.remove('recording');
    }
}

window.onload = initializeApp;