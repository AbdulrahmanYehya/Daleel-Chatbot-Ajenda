import os
import json
import re
import time
import asyncio
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from rag_handler import EnhancedRAGHandler
from nlp_handler import LocalSummarizer

try:
    from google.adk.agents import Agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types
    ADK_AVAILABLE = True
except ImportError:
    ADK_AVAILABLE = False
    logging.warning("google-adk not found. Run: pip install google-adk google-genai")


def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result(timeout=60)
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


class AdkAgentHandler:
    def __init__(self, database):
        self.db = database
        self.session_service = InMemorySessionService()
        self.session_id = "yahya_igenda_session"
        self._last_memory = None

        try:
            _run_async(self.session_service.create_session(
                app_name="iGenda_App",
                user_id="yahya",
                session_id=self.session_id
            ))
            logging.info("ADK session created.")
        except Exception as e:
            logging.warning(f"Session init warning: {e}")

        self._register_tools()
        self._build_agent()

    def _register_tools(self):
        db = self.db

        # ----------------------------------------------------------------
        # CONTEXT & MEMORY TOOLS
        # ----------------------------------------------------------------
        def tool_get_context() -> str:
            """
            Get full situational awareness: today's date/time, today's tasks,
            overdue tasks, upcoming tasks, and all persistent memory.
            Call this at the start of any planning, summary, or scheduling request.
            """
            return json.dumps({
                "now": datetime.now().strftime('%Y-%m-%d %H:%M'),
                "day_of_week": datetime.now().strftime('%A'),
                "todays_tasks": db.get_todays_tasks(),
                "overdue_tasks": db.get_overdue_tasks(),
                "upcoming_tasks": db.get_upcoming_tasks(days=3),
                "user_memory": db.get_all_memory(),
            }, ensure_ascii=False)

        def tool_daily_briefing() -> str:
            """
            Generate a full daily briefing for Yahya.
            Call this when Yahya says 'daily briefing', 'good morning', 'what's my day like',
            'what should I do', or any morning/planning request.
            Returns overdue tasks, today's schedule, upcoming deadlines, and memory context.
            """
            return json.dumps(db.get_daily_briefing(), ensure_ascii=False)

        def tool_save_memory(key: str, value: str) -> str:
            """
            Permanently remember something about Yahya across all sessions.
            Call whenever Yahya shares preferences, goals, habits, or personal facts.
            Examples: key='study_hours', value='9pm-11pm'
                      key='exam_date', value='May 15 2026 — Networks final'
                      key='goal', value='Graduate with distinction'
            """
            db.save_memory(key, value)
            return f"Remembered: {key} = {value}"

        def tool_get_memory(key: str) -> str:
            """Retrieve a specific memory value by key."""
            val = db.get_memory(key)
            return val if val else f"No memory for key '{key}'"

        def tool_web_search(query: str) -> str:
            """Search the live internet for up-to-date facts, news, or research."""
            try:
                from ddgs import DDGS
                results = DDGS().text(query, max_results=3)
                if not results:
                    return "No results found."
                return "\n\n".join([f"Title: {r['title']}\nSnippet: {r['body']}" for r in results])
            except ImportError:
                try:
                    from duckduckgo_search import DDGS as DDGS2
                    results = DDGS2().text(query, max_results=3)
                    if not results:
                        return "No results found."
                    return "\n\n".join([f"Title: {r['title']}\nSnippet: {r['body']}" for r in results])
                except ImportError:
                    return "Error: run pip install ddgs"
            except Exception as e:
                return f"Web search failed: {e}"

        def tool_search_my_data(query: str, item_type: str = "all") -> str:
            """Search Yahya's tasks, notes, or workspaces by keyword."""
            return json.dumps(db.search_data(query, item_type), ensure_ascii=False)

        def tool_check_schedule(date: str, time: str) -> str:
            """ALWAYS call before creating a timed task to check for conflicts."""
            return db.check_schedule_conflict(date, time)

        # ----------------------------------------------------------------
        # TASK TOOLS
        # ----------------------------------------------------------------
        def db_create_task(title: str, description: str = "", due_date: str = "",
                           due_time: str = "", priority: str = "medium",
                           workspace_id: int = None, recurrence: str = None,
                           depends_on: int = None) -> str:
            """
            Create a new task.
            - priority: MUST be 'high' for anything urgent, important, or time-sensitive.
                        Use 'medium' for normal tasks. Use 'low' for optional tasks.
            - recurrence: 'daily', 'weekly', 'biweekly', 'monthly', or None
            - depends_on: task_id of a prerequisite task
            Always call tool_check_schedule first if a due_time is given.
            """
            task = db.create_task(
                title=title, description=description, due_date=due_date,
                due_time=due_time, priority=priority, workspace_id=workspace_id,
                recurrence=recurrence, depends_on=depends_on
            )
            todays_count = len(db.get_todays_tasks())
            return json.dumps({
                "status": "created", "task_id": task['id'], "title": task['title'],
                "tasks_today": todays_count,
                "recurrence": recurrence,
                "tip": "Warn if tasks_today > 6 — heavy schedule."
            })

        def db_complete_task(task_id: int) -> str:
            """
            Mark a task as completed. If it's recurring, the next occurrence is created automatically.
            Use when Yahya says he finished, completed, or is done with something.
            Search for the task first to confirm the correct task_id.
            """
            task = db.complete_task(task_id)
            if not task:
                return f"Task ID {task_id} not found."
            msg = f"✅ Task '{task['title']}' marked as complete!"
            if task.get('recurrence'):
                msg += f" Next occurrence created ({task['recurrence']})."
            return msg

        def db_update_task(task_id: int, title: str = None, description: str = None,
                           due_date: str = None, due_time: str = None,
                           priority: str = None, recurrence: str = None,
                           depends_on: int = None, workspace_id: int = None) -> str:
            """Update any field of an existing task including priority and workspace."""
            updates = {k: v for k, v in [
                ('title', title), ('description', description), ('due_date', due_date),
                ('due_time', due_time), ('priority', priority),
                ('recurrence', recurrence), ('depends_on', depends_on),
                ('workspace_id', workspace_id)
            ] if v is not None}
            if not updates:
                return "No valid fields to update."
            task = db.update_task(task_id, updates)
            return f"Task updated: {task['title']}" if task else f"Task ID {task_id} not found."

        def db_link_note_to_task(task_id: int, note_id: int) -> str:
            """
            Link a research note to a task as reference material.
            Use when Yahya says 'this note is for my X task' or after researching a topic
            that relates to a specific task.
            """
            task = db.update_task(task_id, {'linked_note_id': note_id})
            note = db.update_note(note_id, {'linked_task_id': task_id})
            if task and note:
                return f"Linked note '{note['title']}' to task '{task['title']}'."
            return "Could not link — check task_id and note_id."

        def db_check_task_blocked(task_id: int) -> str:
            """Check if a task is blocked by an incomplete dependency."""
            blocked = db.is_task_blocked(task_id)
            return f"Task {task_id} is {'BLOCKED — dependency not yet complete' if blocked else 'not blocked — ready to work on'}."

        # ----------------------------------------------------------------
        # NOTE TOOLS
        # ----------------------------------------------------------------
        def db_create_note(title: str, content: str, workspace_id: int = None,
                           linked_task_id: int = None) -> str:
            """
            Create a note. Use for research findings, summaries, or anything to save.
            linked_task_id: optionally link this note to a related task.
            """
            note = db.create_note(title=title, content=content,
                                   workspace_id=workspace_id, linked_task_id=linked_task_id)
            return json.dumps({"status": "created", "note_id": note['id'], "title": note['title']})

        def db_update_note(note_id: int, title: str = None, content: str = None,
                           workspace_id: int = None, category: str = None) -> str:
            """Update a note's title, content, workspace, or category."""
            updates = {k: v for k, v in [
                ('title', title), ('content', content),
                ('workspace_id', workspace_id), ('category', category)
            ] if v is not None}
            if not updates:
                return "No valid fields to update."
            note = db.update_note(note_id, updates)
            return f"Note updated: {note['title']}" if note else f"Note ID {note_id} not found."

        # ----------------------------------------------------------------
        # WORKSPACE TOOLS
        # ----------------------------------------------------------------
        def db_create_workspace(name: str, description: str = "",
                                color: str = "#8A2BE2") -> str:
            """
            Create a workspace to group related tasks and notes.
            color: hex color string e.g. '#8A2BE2', '#ef4444', '#10b981', '#f59e0b', '#3b82f6'
            """
            ws = db.create_workspace(name=name, description=description, color=color)
            return json.dumps({"status": "created", "workspace_id": ws['id'], "name": ws['name']})

        def db_update_workspace_color(workspace_id: int, color: str) -> str:
            """Change a workspace's color. Use hex colors like '#ef4444' for red, '#10b981' for green."""
            ws = db.update_workspace(workspace_id, {'color': color})
            return f"Workspace color updated." if ws else f"Workspace ID {workspace_id} not found."

        def db_delete_item(item_type: str, item_id: int) -> str:
            """Delete a task, note, or workspace by ID."""
            item_type = item_type.lower()
            if item_type == 'task':
                success = db.delete_task(item_id)
            elif item_type == 'note':
                success = db.delete_note(item_id)
            elif item_type == 'workspace':
                success = db.delete_workspace(item_id)
            else:
                return "item_type must be 'task', 'note', or 'workspace'."
            return "Deleted successfully." if success else f"ID {item_id} not found."

        def tool_analyze_productivity() -> str:
            """
            Run a deep behavioral analysis of Yahya's productivity patterns.
            Call this when Yahya asks ANY of the following (or similar):
            - "analyze me", "how productive am I", "what's my completion rate"
            - "what time am I most active", "when do I create most tasks"
            - "what day is my busiest", "which day has the most tasks"
            - "what do I procrastinate on", "what category do I avoid"
            - "how long does it take me to complete tasks"
            - "which workspace am I most productive in"
            - "give me insights", "analyze my habits", "productivity report"
            - "how many tasks did I complete this week"
            - Any question about patterns, trends, statistics, or behavior
            Returns full analytics including completion rates, time patterns,
            category breakdowns, procrastination index, streaks, and weekly trends.
            """
            data = db.get_smart_analytics()
            return json.dumps(data, ensure_ascii=False)

        self._tools = [
            # Context & intelligence
            tool_get_context, tool_daily_briefing, tool_save_memory, tool_get_memory,
            tool_web_search, tool_search_my_data, tool_check_schedule,
            tool_analyze_productivity,
            # Tasks
            db_create_task, db_complete_task, db_update_task,
            db_link_note_to_task, db_check_task_blocked,
            # Notes
            db_create_note, db_update_note,
            # Workspaces
            db_create_workspace, db_update_workspace_color, db_delete_item,
        ]

    # ----------------------------------------------------------------
    # FIX 1: SHORT-TERM CONTEXT — what was created in this conversation
    # ----------------------------------------------------------------
    def _build_short_term_context(self) -> str:
        """
        Builds a summary of items created/modified in the last 30 minutes.
        Injected into every message so the agent always knows which IDs
        it just created — prevents 'which note did you mean?' confusion.
        """
        try:
            from datetime import timedelta
            cutoff = (datetime.now() - timedelta(minutes=30)).isoformat()
            tasks = [t for t in self.db.get_tasks() if t.get('created_at', '') > cutoff]
            notes = [n for n in self.db.get_notes() if n.get('created_at', '') > cutoff]
            workspaces = [w for w in self.db.get_workspaces() if w.get('created_at', '') > cutoff]
            if not tasks and not notes and not workspaces:
                return ""
            lines = ["\n=== ITEMS CREATED IN THIS SESSION (last 30 min) ==="]
            for w in workspaces:
                lines.append(f"- Workspace '{w['name']}' id:{w['id']} color:{w.get('color','')}")
            for t in tasks:
                lines.append(f"- Task '{t['title']}' id:{t['id']} workspace_id:{t.get('workspace_id') or 'none'} priority:{t.get('priority','medium')}")
            for n in notes:
                lines.append(f"- Note '{n['title']}' id:{n['id']} workspace_id:{n.get('workspace_id') or 'none'}")
            lines.append("When Yahya says 'that note', 'the workspace I just made', etc — use these IDs.")
            return "\n".join(lines)
        except Exception:
            return ""

    # ----------------------------------------------------------------
    # FIX 3: URGENCY DETECTION — inject priority hint before sending
    # ----------------------------------------------------------------
    def _detect_urgency_hint(self, message: str) -> str:
        """
        Scans for urgency keywords and returns a hint string to append
        to the message. Gemini reads this and sets priority='high'.
        """
        urgent_words = [
            'urgent', 'asap', 'emergency', 'immediately', 'right now',
            'critical', 'important', 'crucial', 'rush', 'today', 'now',
            'عاجل', 'مهم', 'ضروري', 'فوري', 'الآن', 'اليوم'
        ]
        if any(w in message.lower() for w in urgent_words):
            return "\n[AGENT HINT: urgency detected — use priority='high' for any tasks created from this request]"
        return ""

    def _build_agent(self):
        """
        Build the Agent with fresh memory context.
        Runner is created ONCE — never recreated — to preserve the session.
        """
        memory_context = self._build_memory_context()
        instruction = (
            "You are iGenda — an elite, proactive AI productivity agent. "
            "The user is Yahya, a Computer Science student at Mansoura University (Class of 2026).\n\n"

            f"=== PERSISTENT MEMORY ABOUT YAHYA ===\n{memory_context}\n\n"

            "=== YOUR CORE DIRECTIVES ===\n"
            "1. CONTEXT FIRST: For planning, scheduling, or 'what should I do' — call tool_get_context() first.\n"
            "2. DAILY BRIEFING: When Yahya says 'daily briefing', 'good morning', 'what's my day', "
            "or 'what should I do' — call tool_daily_briefing() and give a structured, warm morning report.\n"
            "3. MEMORY: When Yahya shares anything personal — preferences, goals, habits, deadlines — "
            "call tool_save_memory() immediately. These persist forever.\n"
            "4. PROJECT PLANNER: Break large goals into tasks. Create a workspace first with a meaningful "
            "color, then add logically sequenced tasks with dependencies where appropriate.\n"
            "5. RECURRENCE: When a task repeats (daily workout, weekly review), set recurrence. "
            "Completing a recurring task automatically creates the next one.\n"
            "6. DEPENDENCIES: When task B requires task A to be done first, set depends_on. "
            "Tell Yahya which tasks are blocked by incomplete prerequisites.\n"
            "7. RESEARCH & NOTES: For research — web search, synthesize, save as a note, "
            "then offer to link the note to a related task.\n"
            "8. SCHEDULER: Check conflicts before creating timed tasks. Warn if schedule is overloaded.\n"
            "9. COMPLETION: When Yahya says he finished something — search for it, complete it. "
            "If recurring, tell him the next occurrence was created.\n"
            "10. HONEST & CARING: Think like a personal assistant who genuinely cares about Yahya's success.\n"
            # FIX 2: self-correction directive
            "11. SELF-CORRECT: If a tool call doesn't produce the expected result, try a different "
            "approach immediately — search for the item's ID first, then retry. NEVER tell Yahya to "
            "delete and recreate something just because an update failed. Never give up after one attempt.\n"
            # FIX 2: completion summary directive
            "12. COMPLETION SUMMARY: After finishing a multi-step request, always end with a clear "
            "summary of exactly what was done: item names, IDs, which workspace they belong to, "
            "and anything still pending. Be specific — never just say 'Done!'.\n"
            "13. PRIORITY: The [AGENT HINT] tag in messages signals urgency — always honour it by "
            "setting priority='high' on any tasks created in that request.\n"
            "14. CONTEXT: The [ITEMS CREATED IN THIS SESSION] block shows recent IDs — always "
            "use these when Yahya refers to 'that note', 'the workspace I just made', etc.\n"
            "15. ANALYTICS & INSIGHTS: When Yahya asks about his productivity, habits, patterns, "
            "statistics, completion rate, most active time, busiest day, procrastination, or ANY "
            "analysis question — call tool_analyze_productivity() immediately. Then interpret the "
            "numbers in plain language with specific insights and honest observations. Don't just "
            "repeat the numbers — tell Yahya what they mean. For example: if completion rate is 40%, "
            "say 'You complete 2 out of every 5 tasks — there's room to improve, especially in [category]'. "
            "If peak hour is 11pm, say 'You create most tasks late at night — consider planning earlier'. "
            "Be a productivity coach, not a spreadsheet."
        )

        self.agent = Agent(
            name="iGenda_Core_Agent",
            model="gemini-2.0-flash",
            description="Elite AI productivity agent for iGenda.",
            instruction=instruction,
            tools=self._tools
        )

        # Patch existing runner's agent — never create a new Runner (would lose the session)
        if hasattr(self, 'runner') and self.runner is not None:
            self.runner._agent = self.agent
        else:
            self.runner = Runner(
                agent=self.agent,
                app_name="iGenda_App",
                session_service=self.session_service
            )

    def _build_memory_context(self) -> str:
        try:
            memory = self.db.get_all_memory()
            if not memory:
                return "No persistent memory yet. Learn about Yahya and save key facts."
            return "\n".join(f"- {k}: {v}" for k, v in memory.items())
        except Exception:
            return "Memory unavailable."

    def _ensure_session(self):
        try:
            _run_async(self.session_service.get_session(
                app_name="iGenda_App", user_id="yahya", session_id=self.session_id
            ))
        except Exception:
            logging.info("Recreating ADK session.")
            _run_async(self.session_service.create_session(
                app_name="iGenda_App", user_id="yahya", session_id=self.session_id
            ))

    def process_message(self, user_message: str, message_type: str = 'text',
                        context_data: str = None) -> dict:
        start_time = time.time()
        tool_events = []

        try:
            self._ensure_session()

            # Only rebuild agent when memory actually changed — saves quota
            current_memory = self.db.get_all_memory()
            if current_memory != self._last_memory:
                self._build_agent()
                self._last_memory = current_memory

            if message_type == 'document_text' and context_data:
                max_chars = 12000
                if len(context_data) > max_chars:
                    context_data = context_data[:max_chars] + "\n\n[Document truncated]"
                user_message = (
                    f"I have uploaded a document. My instruction: {user_message}\n\n"
                    f"--- DOCUMENT CONTENT ---\n{context_data}\n--- END DOCUMENT ---"
                )

            # FIX 1: inject short-term context (recently created item IDs)
            short_term = self._build_short_term_context()
            if short_term:
                user_message = user_message + short_term

            # FIX 3: inject urgency hint if keywords detected
            urgency_hint = self._detect_urgency_hint(user_message)
            if urgency_hint:
                user_message = user_message + urgency_hint

            self.db.save_message('user', user_message)

            content = types.Content(
                role='user',
                parts=[types.Part.from_text(text=user_message)]
            )

            final_text = "I couldn't generate a response."

            for event in self.runner.run(
                user_id="yahya",
                session_id=self.session_id,
                new_message=content
            ):
                if hasattr(event, 'content') and event.content:
                    for part in getattr(event.content, 'parts', []):
                        if hasattr(part, 'function_call') and part.function_call:
                            fn = part.function_call
                            tool_events.append({
                                "type": "tool_call",
                                "name": fn.name,
                                "args": dict(fn.args) if fn.args else {}
                            })
                        elif hasattr(part, 'function_response') and part.function_response:
                            fr = part.function_response
                            tool_events.append({
                                "type": "tool_result",
                                "name": fr.name,
                                "result": str(fr.response)[:300]
                            })
                        elif hasattr(part, 'text') and part.text:
                            final_text = part.text

            self.db.save_message('model', final_text)

            # Proactive overdue warning
            overdue = self.db.get_overdue_tasks()
            if overdue and 'overdue' not in user_message.lower() and len(tool_events) < 2:
                titles = ', '.join(t['title'] for t in overdue[:3])
                final_text += f"\n\n⚠️ **Heads up:** You have {len(overdue)} overdue task(s): {titles}."

            return {
                "response_message": final_text,
                "tool_events": tool_events,
                "tasks": self.db.get_tasks(),
                "notes": self.db.get_notes(),
                "workspaces": self.db.get_workspaces(),
                "processing_time": round(time.time() - start_time, 2),
                "ai_metadata": {"model_used": "gemini-adk"}
            }

        except Exception as e:
            logging.error(f"ADK Agent Error: {e}", exc_info=True)
            raise e


class EnhancedAIHandler:
    def __init__(self):
        self.enhanced_rag = EnhancedRAGHandler()
        self.summarizer = LocalSummarizer()
        self.api_key = os.environ.get("GEMINI_API_KEY")
        self.use_adk = ADK_AVAILABLE and bool(self.api_key)
        self.adk_agent = None
        logging.info(f"AI Handler initialized. ADK active: {self.use_adk}")

    def process_multimodal_message(self, user_message, message_type='text',
                                   context_data=None, database=None, language='en'):
        if self.use_adk and database:
            if not self.adk_agent:
                self.adk_agent = AdkAgentHandler(database)
            try:
                return self.adk_agent.process_message(user_message, message_type, context_data)
            except Exception as e:
                logging.warning(f"ADK failed, falling back. Error: {e}")

        # --- OFFLINE RAG FALLBACK ---
        if message_type == 'document_text':
            text_to_process = context_data if context_data else user_message
            summary, title = self.summarizer.summarize(text_to_process)
            if database:
                database.create_note(title=f"Summary: {title}", content=summary,
                                     category="Documents", language="en")
                return {
                    "response_message": "Document summarized and saved as a note (Offline Mode).",
                    "tool_events": [],
                    "tasks": database.get_tasks(),
                    "notes": database.get_notes(),
                    "workspaces": database.get_workspaces()
                }
            return {"response_message": "Database not provided.", "tool_events": [],
                    "tasks": [], "notes": [], "workspaces": []}

        detected_lang = 'ar' if self._is_arabic(user_message) else language
        rag_result = self.enhanced_rag.get_fallback_response(user_message, detected_lang)

        if database and 'tasks' in rag_result:
            for t in rag_result['tasks']:
                database.create_task(title=t.get('title'), description=t.get('description'),
                                     due_date=t.get('due_date'))
        if database and 'notes' in rag_result:
            for n in rag_result['notes']:
                database.create_note(title=n.get('title'), content=n.get('content'))

        rag_result.setdefault('tool_events', [])
        rag_result['ai_metadata'] = {"model_used": "local-rag-fallback"}
        if database:
            rag_result['workspaces'] = database.get_workspaces()
        return rag_result

    def _is_arabic(self, text):
        return bool(re.search(r'[\u0600-\u06FF]', text))

    def check_model_health(self):
        if self.use_adk:
            return {'status': 'healthy', 'model': 'gemini-adk-primary'}
        return {'status': 'healthy', 'model': 'local-rag-fallback'}