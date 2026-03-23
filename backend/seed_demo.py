"""
iGenda Demo Seeder — run this once before testing
Usage: cd backend && py seed_demo.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Database
from datetime import datetime, timedelta

db = Database()
today = datetime.now()

def d(offset):
    return (today + timedelta(days=offset)).strftime('%Y-%m-%d')

print("🌱 Seeding iGenda...\n")

# --- MEMORY ---
memories = {
    "name": "Yahya",
    "university": "Mansoura University, Computer Science",
    "graduation_year": "2026",
    "goal": "Graduate with distinction",
    "current_project": "iGenda — AI productivity agent (graduation project)",
    "preferred_study_time": "evenings 9pm-11pm",
    "exam_season": "May 2026",
}
for k, v in memories.items():
    db.save_memory(k, v)
    print(f"  💾 {k}: {v}")

# --- WORKSPACES ---
ws_grad = db.create_workspace("Graduation Project", "iGenda AI agent tasks", "#8A2BE2")
ws_study = db.create_workspace("Study Plan", "Exam prep and lectures", "#3b82f6")
ws_personal = db.create_workspace("Personal", "Health and habits", "#10b981")
print(f"\n  📁 Created 3 workspaces")

# --- TASKS ---
tasks_data = [
    dict(title="Finalize project report", description="Complete written report for submission",
         due_date=d(3), due_time="21:00", priority="high", workspace_id=ws_grad['id'], category="work"),
    dict(title="Prepare demo presentation", description="15-minute demo for the committee",
         due_date=d(5), due_time="14:00", priority="high", workspace_id=ws_grad['id'], category="work"),
    dict(title="Run full app testing session", description="Test all agent features end to end",
         due_date=d(0), due_time="20:00", priority="high", workspace_id=ws_grad['id'], category="work"),
    dict(title="Review Networks lecture notes", description="Chapters 4-7, TCP/IP and routing",
         due_date=d(0), due_time="21:00", priority="high", workspace_id=ws_study['id'], category="study"),
    dict(title="Complete Algorithms assignment", description="Dynamic programming problems",
         due_date=d(2), due_time="23:59", priority="high", workspace_id=ws_study['id'], category="study"),
    dict(title="Submit project proposal draft", description="Was due last week — still pending",
         due_date=d(-3), due_time="17:00", priority="high", workspace_id=ws_grad['id'], category="work"),
    dict(title="Morning workout", description="30 min cardio + stretching",
         due_date=d(0), due_time="07:00", priority="medium", workspace_id=ws_personal['id'],
         category="health", recurrence="daily"),
    dict(title="Weekly progress review", description="Review week, plan next week",
         due_date=d(6), due_time="20:00", priority="medium", workspace_id=ws_personal['id'],
         category="personal", recurrence="weekly"),
]
for t in tasks_data:
    db.create_task(**t)
print(f"  ✅ Created {len(tasks_data)} tasks (1 overdue, 2 recurring)")

# --- NOTES ---
db.create_note(
    title="iGenda Architecture Overview",
    content="Tech Stack:\n- Backend: Flask + SQLite\n- AI: Google ADK + Gemini 2.0 Flash\n- Offline fallback: SentenceTransformers RAG\n- Frontend: Vanilla JS + CSS\n\nKey Features:\n- 17 agent tools\n- Persistent memory across sessions\n- Task recurrence & dependencies\n- Document processing (PDF, DOCX, TXT)\n- Bilingual (Arabic + English)\n- Proactive overdue alerts",
    category="Work", workspace_id=ws_grad['id']
)
db.create_note(
    title="Networks Exam Topics",
    content="Chapter 4: Transport Layer\n- TCP vs UDP\n- Flow control, congestion control\n- Three-way handshake\n\nChapter 5: Network Layer\n- IP addressing, subnetting\n- Routing algorithms (Dijkstra, Bellman-Ford)\n\nChapter 6: Data Link Layer\n- MAC addresses, ARP\n- Ethernet, CSMA/CD",
    category="Study", workspace_id=ws_study['id']
)
print(f"  📝 Created 2 notes")

print("\n✅ Seeding complete! Start your app and test away.\n")
