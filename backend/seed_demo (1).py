"""
iGenda Demo Seeder v2 — Analytics Edition
==========================================
Seeds realistic data with proper timestamps so ALL analytics panels
show meaningful patterns without needing any API calls.

What this creates:
- 4 workspaces with different productivity rates
- ~80 tasks spread across 20 days with realistic hourly patterns
  (evening peak at 9-11pm matching study habits)
- Overdue tasks to trigger alerts
- Recurring tasks (daily workout streak)
- Notes with varied word counts
- Memory entries for personalised welcome message

Usage:
    cd backend
    py seed_demo.py
    py app.py
"""
import sys, os, sqlite3, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Database
from datetime import datetime, timedelta

db = Database()
db.clear_all()
print("🌱 Seeding iGenda demo data (Analytics Edition)...\n")

now = datetime.now()

def d(offset):
    return (now + timedelta(days=offset)).strftime('%Y-%m-%d')

# =====================================================================
# 1. MEMORY
# =====================================================================
memories = {
    "name":                 "Yahya",
    "university":           "Mansoura University, Computer Science",
    "graduation_year":      "2026",
    "goal":                 "Graduate with distinction",
    "current_project":      "iGenda — AI productivity agent (graduation project)",
    "preferred_study_time": "evenings 9pm-11pm",
    "study_style":          "Pomodoro technique, 25min focus sessions",
    "weakness":             "tends to procrastinate on study tasks",
    "strength":             "very consistent with health and workout tasks",
    "exam_season":          "May 2026",
}
for k, v in memories.items():
    db.save_memory(k, v)
    print(f"  💾 {k}: {v}")
print()

# =====================================================================
# 2. WORKSPACES
# =====================================================================
ws_grad     = db.create_workspace("Graduation Project", "iGenda AI agent tasks and research", "#8A2BE2")
ws_study    = db.create_workspace("Study Plan",         "Exam prep, lectures, assignments",    "#3b82f6")
ws_personal = db.create_workspace("Personal",           "Health, habits, daily routines",      "#10b981")
ws_work     = db.create_workspace("Freelance Work",     "Client projects and deliverables",    "#f59e0b")
print("  📁 Created 4 workspaces\n")

# =====================================================================
# 3. DIRECT SQLITE TASK INSERTER (full timestamp control)
# =====================================================================
def insert_task(title, description="", due_date=None, due_time=None,
                priority="medium", category="personal", workspace_id=None,
                recurrence=None, completed=False,
                created_day_ago=0, created_hour=21,
                completed_day_ago=None, completed_hour=22):
    today = now.strftime('%Y-%m-%d')
    if not due_date:
        due_date = today

    created_at = (now - timedelta(days=created_day_ago)).replace(
        hour=created_hour, minute=random.randint(0, 59),
        second=0, microsecond=0
    ).isoformat()

    completed_at = None
    if completed and completed_day_ago is not None:
        completed_at = (now - timedelta(days=completed_day_ago)).replace(
            hour=completed_hour, minute=random.randint(0, 59),
            second=0, microsecond=0
        ).isoformat()

    conn = sqlite3.connect(db.db_file)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        INSERT INTO tasks (title, description, due_date, due_time, priority,
            category, language, workspace_id, completed, completed_at,
            recurrence, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'en', ?, ?, ?, ?, ?)
    """, (title, description, due_date, due_time, priority, category,
          int(workspace_id) if workspace_id else None,
          1 if completed else 0, completed_at, recurrence, created_at))
    conn.execute("UPDATE analytics SET total_tasks_created = total_tasks_created + 1 WHERE id=1")
    conn.commit()
    conn.close()

# =====================================================================
# 4. GRADUATION PROJECT — ~75% completion (productive workspace)
# =====================================================================
print("  ✅ Graduation Project tasks...")
grad_tasks = [
    ("Set up Flask project structure",       "high",   True,  30, 29, 20, 22),
    ("Design SQLite database schema",         "high",   True,  28, 27, 21, 23),
    ("Implement ADK agent integration",       "high",   True,  25, 23, 22, 23),
    ("Build RAG offline fallback",            "medium", True,  22, 20, 21, 22),
    ("Add bilingual Arabic/English support",  "medium", True,  18, 16, 20, 21),
    ("Implement persistent memory system",    "high",   True,  14, 12, 22, 23),
    ("Add task recurrence feature",           "medium", True,  10, 9,  21, 22),
    ("Add smart analytics engine",            "high",   True,  5,  4,  22, 23),
    ("Write project documentation",           "medium", False, 3,  None, 20, 0),
    ("Finalize graduation report",            "high",   False, 2,  None, 21, 0),
    ("Prepare demo presentation slides",      "high",   False, 1,  None, 22, 0),
    ("Practice demo walkthrough",             "high",   False, 0,  None, 21, 0),
]
for title, pri, done, c_ago, cp_ago, c_hr, cp_hr in grad_tasks:
    insert_task(title, priority=pri, category="work", workspace_id=ws_grad['id'],
                completed=done, created_day_ago=c_ago, created_hour=c_hr,
                completed_day_ago=cp_ago, completed_hour=cp_hr,
                due_date=d(3) if not done else None)

# =====================================================================
# 5. STUDY TASKS — ~40% completion (procrastination visible)
# =====================================================================
print("  📚 Study Plan tasks...")
study_tasks = [
    ("Review Networks lectures 1-3",      "high",   True,  20, 18, 21, 23, None),
    ("Complete Algorithms assignment 1",   "high",   True,  18, 17, 20, 22, None),
    ("Review Database Systems chapter 4",  "medium", True,  15, 14, 22, 23, None),
    ("Study for OS midterm",               "high",   True,  12, 11, 21, 23, None),
    ("Complete Algorithms assignment 2",   "high",   False, 8,  None, 22, 0, d(-2)),  # overdue
    ("Review Networks lectures 4-7",       "high",   False, 7,  None, 21, 0, d(-1)),  # overdue
    ("Submit project proposal draft",      "high",   False, 6,  None, 20, 0, d(-3)),  # overdue
    ("Read AI research paper",             "low",    False, 5,  None, 23, 0, d(1)),
    ("Study for Database final",           "high",   False, 2,  None, 21, 0, d(7)),
    ("Complete Security assignment",       "medium", False, 1,  None, 22, 0, d(3)),
]
for title, pri, done, c_ago, cp_ago, c_hr, cp_hr, due in study_tasks:
    insert_task(title, priority=pri, category="study", workspace_id=ws_study['id'],
                completed=done, created_day_ago=c_ago, created_hour=c_hr,
                completed_day_ago=cp_ago, completed_hour=cp_hr,
                due_date=due or (d(0) if not done else None))

# =====================================================================
# 6. PERSONAL / HEALTH — ~85% completion (strong streak)
# =====================================================================
print("  🏃 Personal & Health tasks...")
# 14 days of daily workouts with 85% completion for streak
for i in range(14, 0, -1):
    done = random.random() < 0.85
    insert_task(
        "Morning workout", "30 min cardio + stretching",
        priority="medium", category="health", workspace_id=ws_personal['id'],
        recurrence="daily", completed=done,
        due_date=(now - timedelta(days=i)).strftime('%Y-%m-%d'),
        created_day_ago=i, created_hour=random.choice([7, 8, 21, 22]),
        completed_day_ago=i if done else None,
        completed_hour=random.choice([8, 9])
    )
# Today's workout (pending)
insert_task("Morning workout", "30 min cardio + stretching",
            priority="medium", category="health", workspace_id=ws_personal['id'],
            recurrence="daily", completed=False, due_date=d(0),
            created_day_ago=0, created_hour=7)

personal_tasks = [
    ("Drink 8 glasses of water", "low",    True,  5,  5,  8,  21),
    ("Cook healthy meal",         "low",    True,  4,  4,  17, 19),
    ("Weekly progress review",    "medium", True,  7,  7,  20, 21),
    ("Weekly progress review",    "medium", False, 0,  None, 20, 0),
    ("Call family",               "medium", True,  3,  3,  19, 20),
    ("Read book chapter",         "low",    False, 2,  None, 22, 0),
]
for title, pri, done, c_ago, cp_ago, c_hr, cp_hr in personal_tasks:
    insert_task(title, priority=pri, category="personal", workspace_id=ws_personal['id'],
                completed=done, created_day_ago=c_ago, created_hour=c_hr,
                completed_day_ago=cp_ago, completed_hour=cp_hr,
                due_date=d(1) if not done else None)

# =====================================================================
# 7. FREELANCE WORK — ~60% completion
# =====================================================================
print("  💼 Freelance Work tasks...")
work_tasks = [
    ("Design landing page mockup",   "high",   True,  15, 13, 10, 16),
    ("Build responsive navbar",       "high",   True,  12, 11, 11, 15),
    ("Client feedback revisions",     "high",   True,  10, 9,  10, 14),
    ("Write API documentation",       "medium", False, 6,  None, 11, 0),
    ("Deliver final project files",   "high",   False, 3,  None, 10, 0),
    ("Send invoice to client",        "medium", False, 1,  None, 11, 0),
]
for title, pri, done, c_ago, cp_ago, c_hr, cp_hr in work_tasks:
    insert_task(title, priority=pri, category="work", workspace_id=ws_work['id'],
                completed=done, created_day_ago=c_ago, created_hour=c_hr,
                completed_day_ago=cp_ago, completed_hour=cp_hr,
                due_date=d(-1) if (not done and c_ago > 3) else d(2))

# =====================================================================
# 8. HOURLY PATTERN TASKS — bulk insert to create realistic time distribution
#    Peak: 9pm-11pm (study hours), secondary: 10am-11am
# =====================================================================
print("  🕐 Generating hourly activity patterns...")
hour_weights = {
    7:2, 8:3, 9:2, 10:5, 11:4,
    12:2, 13:2, 14:3, 15:3,
    16:2, 17:3, 18:2,
    19:4, 20:6, 21:9, 22:8, 23:5
}
cats = ['study', 'work', 'personal', 'health']
pris = ['high', 'high', 'medium', 'medium', 'low']

for day in range(20, 1, -1):
    for hour, weight in hour_weights.items():
        for _ in range(max(1, weight // 3)):
            if random.random() < 0.25:
                cat = random.choice(cats)
                pri = random.choice(pris)
                done = random.random() < (0.7 if pri == 'high' else 0.45)
                insert_task(
                    f"Task ({cat})", priority=pri, category=cat,
                    completed=done,
                    due_date=(now - timedelta(days=day)).strftime('%Y-%m-%d'),
                    created_day_ago=day, created_hour=hour,
                    completed_day_ago=day if done else None,
                    completed_hour=min(hour + random.randint(1, 3), 23)
                )

# =====================================================================
# 9. NOTES
# =====================================================================
print("\n  📝 Creating notes...")

def insert_note(title, content, category="General", workspace_id=None, created_day_ago=0):
    created_at = (now - timedelta(days=created_day_ago)).replace(
        hour=random.randint(19, 23), minute=random.randint(0, 59)
    ).isoformat()
    conn = sqlite3.connect(db.db_file)
    conn.execute("""
        INSERT INTO notes (title, content, category, language, workspace_id, word_count, created_at)
        VALUES (?, ?, ?, 'en', ?, ?, ?)
    """, (title, content, category,
          int(workspace_id) if workspace_id else None,
          len(content.split()), created_at))
    conn.execute("UPDATE analytics SET total_notes_created = total_notes_created + 1 WHERE id=1")
    conn.commit()
    conn.close()

insert_note(
    "iGenda Architecture Overview",
    "Tech Stack:\n- Backend: Flask + SQLite (WAL mode)\n- AI: Google ADK + Gemini 2.0 Flash\n- Offline fallback: SentenceTransformers RAG\n- Frontend: Vanilla JS + CSS\n\nKey Features:\n- 18 agent tools\n- Persistent memory across sessions\n- Conversation history replay after restarts\n- Task recurrence (daily/weekly/monthly)\n- Task dependencies (blocked tasks)\n- Note-task linking\n- Document processing (PDF, DOCX, TXT)\n- Bilingual Arabic + English\n- Proactive overdue alerts\n- Smart analytics engine\n- Daily briefing panel\n- PDF export for notes, workspaces, and daily plan",
    category="Work", workspace_id=ws_grad['id'], created_day_ago=15
)
insert_note(
    "Networks Exam Topics",
    "Chapter 4: Transport Layer\n- TCP vs UDP differences\n- Flow control and congestion control\n- TCP three-way handshake: SYN, SYN-ACK, ACK\n\nChapter 5: Network Layer\n- IP addressing and subnetting (CIDR notation)\n- Routing algorithms: Dijkstra (OSPF), Bellman-Ford (RIP)\n- NAT, DHCP, ICMP\n\nChapter 6: Data Link Layer\n- MAC addresses and ARP protocol\n- Ethernet frame structure\n- CSMA/CD and CSMA/CA\n\nChapter 7: Application Layer\n- HTTP/HTTPS request/response cycle\n- DNS resolution steps\n- SMTP for email",
    category="Study", workspace_id=ws_study['id'], created_day_ago=10
)
insert_note(
    "AI Agents Research Summary",
    "Definition: An AI agent perceives its environment, makes decisions, and takes actions to achieve goals autonomously.\n\nTypes of Agents:\n1. Reactive — respond to current state only\n2. Deliberative — maintain internal world model\n3. Hybrid — combine both approaches\n\nGoogle ADK Architecture:\n- Agent: LLM with instructions and tools\n- Tools: Python functions the agent calls\n- Runner: manages execution and event streaming\n- SessionService: maintains conversation state\n\nKey Challenge in iGenda: Multi-step reasoning requires the agent to maintain context across tool calls. Solved via short-term context injection — appending recently created item IDs to every message.",
    category="Study", workspace_id=ws_grad['id'], created_day_ago=7
)
insert_note(
    "Personal Productivity Observations",
    "What's working:\n- Pomodoro technique: 25min focus, 5min break\n- Planning tasks the night before saves morning decision fatigue\n- Categorising tasks helps spot where time goes\n\nWhat needs work:\n- Study tasks keep getting pushed to the next day\n- Late-night task creation (10-11pm) means executing while tired\n- Too many high-priority tags dilute what's actually urgent\n\nPlan for improvement:\n- Complete at least 1 study task per day before 9pm\n- Hard limit: max 3 high-priority tasks per day\n- Block 9pm-11pm strictly for study — no freelance work",
    category="Personal", workspace_id=ws_personal['id'], created_day_ago=5
)
insert_note(
    "Freelance Client — Project Brief",
    "Client: TechStartup XYZ\nProject: Landing page redesign\nDeadline: End of month\n\nRequirements:\n- Modern, clean design\n- Mobile-first responsive layout\n- Page load under 2 seconds\n- Contact form with validation\n- SEO-friendly HTML structure\n\nDeliverables:\n1. Figma design mockup\n2. HTML/CSS/JS implementation\n3. Technical documentation\n4. Source files delivery",
    category="Work", workspace_id=ws_work['id'], created_day_ago=12
)
insert_note(
    "Machine Learning Study Notes",
    "Supervised Learning Algorithms:\n- Linear Regression: continuous prediction, MSE loss\n- Logistic Regression: binary classification, cross-entropy loss\n- Decision Trees: interpretable, prone to overfitting\n- Random Forest: ensemble reduces variance\n- SVM: optimal hyperplane, kernel trick for non-linear\n- Neural Networks: universal approximators\n\nUnsupervised:\n- K-Means: centroid-based clustering\n- PCA: dimensionality reduction via eigenvectors\n\nKey Formulas:\n- MSE = (1/n) * sum((y - y_hat)^2)\n- Cross-entropy = -sum(y * log(y_hat))\n- Accuracy = correct / total * 100",
    category="Study", workspace_id=ws_study['id'], created_day_ago=3
)
print("  📝 Created 6 notes")

# =====================================================================
# 10. PRINT ANALYTICS PREVIEW
# =====================================================================
analytics = db.get_smart_analytics()
print(f"""
✅ Seeding complete!

📊 Analytics Preview:
   Total tasks:      {analytics['total_tasks']}
   Completed:        {analytics['completed_tasks']} ({analytics['completion_rate']}%)
   Overdue:          {analytics['overdue_tasks']}
   Streak:           {analytics['current_streak_days']} day(s) 🔥
   Peak hour:        {analytics['peak_creation_hour']}
   Busiest day:      {analytics['busiest_day_of_week']}
   Total notes:      {analytics['total_notes']}
   Avg note length:  {analytics['avg_note_words']} words

Category breakdown:""")
for cat in analytics.get('category_breakdown', []):
    bar = '█' * int(cat['rate'] / 5)
    print(f"   {cat['category']:12} {bar:20} {cat['rate']}% ({cat['completed']}/{cat['total']})")

print(f"""
Now start the app:
   py app.py

Then open: http://127.0.0.1:5000

Things to check:
   📊 Click 'Analytics' button — full dashboard with charts
   📋 Click 'Briefing' button — today's schedule + overdue
   🧠 Click 'Memory' button — all saved facts about Yahya
   ⚠️  Overdue counter in header should show red number
   ↻   Recurring workout tasks show green recurrence badge
   🔒  Check task cards for dependency badges
""")
