import os
import json
import re
import time
import asyncio
import logging
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

from nlp_handler import LocalSummarizer
from sentence_transformers import SentenceTransformer
import backend_client
import requests

BACKEND_URL = os.getenv("BACKEND_URL")


def _aggregate_state(user_id: str) -> dict:
    """
    Reconstructs {tasks, notes, workspaces, spaces} for the frontend's
    post-turn state refresh. No flat "all tasks/notes" endpoint exists
    (confirmed gap — see backend_client.py), so this walks every
    workspace/space via the documented GET endpoints. Costs
    O(workspaces x spaces) HTTP calls; ask the backend team for a flat
    listing endpoint if this becomes a bottleneck.
    """
    try:
        workspaces = backend_client.get_workspaces(user_id)
        all_spaces, all_tasks, all_notes = [], [], []
        for ws in workspaces:
            ws_id = backend_client._field(ws, "id")
            spaces = backend_client.get_spaces(user_id, ws_id)
            all_spaces.extend(spaces)
            for sp in spaces:
                sp_id = backend_client._field(sp, "id")
                all_tasks.extend(backend_client.get_tasks(user_id, ws_id, sp_id))
                all_notes.extend(backend_client.get_notes(user_id, ws_id, sp_id))
        return {"tasks": all_tasks, "notes": all_notes, "workspaces": workspaces, "spaces": all_spaces}
    except backend_client.BackendError as e:
        logging.error(f"State aggregation failed: {e}")
        return {"tasks": [], "notes": [], "workspaces": [], "spaces": []}

# ======================================================================================
# CHANGE NOTE (AI-backend integration doc v2 + Technical Addendum, 2026-07-03):
# The offline Sentence-Transformer RAG fallback (rag_handler.EnhancedRAGHandler) is
# deprecated per the doc ("Offline Vector Indexing... completely removed from the
# execution environment"). It is no longer imported here. The embedder below is used
# ONLY for dynamic tool retrieval (picking the top-K relevant tools per prompt) — that
# mechanism was never listed as deprecated, and Action Item 3 (WSGI --preload for
# "shared tokenizers") only makes sense if something here still loads a transformer
# model, so it's kept as a direct SentenceTransformer instance instead of going through
# the old RAG class (which also built an unused example-matching index on every boot).
# rag_handler.py and rag_examples.py are no longer imported anywhere and can be
# removed from the project once the backend team confirms nothing else depends on them.
# ======================================================================================

try:
    from google.adk.agents import Agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types
    from google import genai 
    from pydantic import BaseModel, Field
    from typing import List, Optional
    ADK_AVAILABLE = True
except ImportError:
    ADK_AVAILABLE = False
    logging.warning("google-adk or pydantic not found. Run: pip install google-adk google-genai pydantic")


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


# ======================================================================================
# PYDANTIC MODELS FOR STRUCTURED OUTPUTS
# ======================================================================================
class SubtaskPlan(BaseModel):
    title: str = Field(description="Title of the subtask")

class TaskPlan(BaseModel):
    title: str = Field(description="Title of the task")
    description: str = Field(default="", description="Optional description")
    due_date: str = Field(default="", description="YYYY-MM-DD")
    due_time: str = Field(default="", description="HH:MM")
    priority: str = Field(default="medium", description="high, medium, or low")
    subtasks: List[SubtaskPlan] = Field(default_factory=list)

class SpacePlan(BaseModel):
    name: str = Field(description="Name of the space, phase, or day")
    tasks: List[TaskPlan] = Field(description="Tasks belonging to this space")

class WorkspacePlan(BaseModel):
    name: str = Field(description="Name of the overall project or workspace")
    description: str = Field(default="")
    color: str = Field(default="#8A2BE2")

class ProjectPlan(BaseModel):
    workspace: WorkspacePlan
    spaces: List[SpacePlan]


# ======================================================================================
# HEAVY AGENT: Handles Complex Planning, Workspaces, and Analytics
# ======================================================================================
class AdkComplexHandler:
    def __init__(self, database):
        self.db = database
        self.session_service = InMemorySessionService()
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
        self._precompute_tool_embeddings()

    def _precompute_tool_embeddings(self):
        logging.info("Precomputing tool embeddings for Dynamic Retrieval...")
        # Precompute using a dummy user to grab metadata (tool names and docstrings don't change per user)
        dummy_tools = self._register_tools("dummy_user")
        self._tool_metadata = [{"name": f.__name__, "doc": f.__doc__ or ""} for f in dummy_tools]
        
        self.tool_docs = []
        for meta in self._tool_metadata:
            search_text = f"{meta['name'].replace('_', ' ')}: {meta['doc']}"
            self.tool_docs.append(search_text)
            
        self.tool_vectors = self.embedder.encode(self.tool_docs)

    # CHANGE NOTE: _get_semantic_memory() removed. The integration doc explicitly
    # deprecates Python-side semantic memory retrieval ("removed: semantic memory
    # retrieval... embedding comparisons computed natively in-memory within the .NET
    # service layer"). Proactive memory-context injection into the agent's system
    # prompt is gone; memory is now only reachable on-demand via tool_get_memory /
    # tool_save_memory (still local-SQLite-backed — see backend_client.py header for
    # why those weren't migrated yet).

    def _retrieve_tools(self, user_id: str, user_message: str, top_k: int = 8, user_token: str = "") -> list:
        query_vector = self.embedder.encode([user_message])
        similarities = cosine_similarity(query_vector, self.tool_vectors)[0]
        top_indices = np.argsort(similarities)[::-1]
        
        # Instantiate actual tools strictly scoped to this user_id
        actual_tools = self._register_tools(user_id, user_token)
        tools_by_name = {f.__name__: f for f in actual_tools}
        
        selected_tools = []
        mandatory_tools = ['tool_get_context', 'db_create_project_plan'] 
        
        for idx in top_indices:
            tool_name = self._tool_metadata[idx]['name']
            func = tools_by_name[tool_name]
            if func not in selected_tools:
                selected_tools.append(func)
            if len(selected_tools) >= top_k:
                break
                
        for func_name in mandatory_tools:
            func = tools_by_name[func_name]
            if func not in selected_tools:
                selected_tools.append(func)
                
        logging.info(f"Dynamically retrieved {len(selected_tools)} tools for this prompt.")
        return selected_tools

    def _register_tools(self, user_id: str, user_token: str = ""):
        db = self.db

        def tool_get_context() -> str:
            """Get the user's daily schedule, overdue tasks, and upcoming tasks."""
            return json.dumps(backend_client.get_briefing(user_id), ensure_ascii=False)

        def tool_daily_briefing() -> str:
            """Generate a daily briefing, morning report, or daily summary."""
            return json.dumps(backend_client.get_briefing(user_id), ensure_ascii=False)

        def tool_save_memory(key: str, value: str) -> str:
            """Remember facts, user preferences, habits, or personal data permanently."""
            try:
                backend_client.save_memory(user_id, key, value)
                return f"Remembered: {key} = {value}"
            except backend_client.BackendError as e:
                return f"FAILED: Could not save memory. Error: {e}"

        def tool_get_memory(key: str) -> str:
            """Retrieve specific saved memories or preferences about the user."""
            try:
                mem = backend_client.get_memory(user_id)
                val = backend_client._field(mem, key) or mem.get(key)
                return val if val else f"FAILED: No memory found for key '{key}'"
            except backend_client.BackendError as e:
                return f"FAILED: Could not retrieve memory. Error: {e}"

        def tool_web_search(query: str) -> str:
            """Search the internet for external facts, news, or research."""
            try:
                from ddgs import DDGS
                results = DDGS().text(query, max_results=3)
                if not results: return "FAILED: No results found on the web."
                return "\n\n".join([f"Title: {r['title']}\nSnippet: {r['body']}" for r in results])
            except Exception as e:
                return f"FAILED: Web search error: {e}"

        # REMOVED (confirmed permanently out of MVP scope, not just "not built yet"):
        #   tool_search_my_data — no cross-item search endpoint exists or is planned.
        #   tool_check_schedule — no schedule-conflict endpoint exists or is planned.
        # These are intentionally not registered below so the model never attempts them.

        def tool_analyze_productivity() -> str:
            """Get statistics and analytics about tasks and notes."""
            # NOTE: only the general /api/analytics endpoint is confirmed available to
            # the AI. "Smart" analytics (procrastination index, streaks, etc.) is still
            # listed as not-yet-built per doc section 7.1 — no confirmed AI-facing path.
            try:
                data = backend_client.get_analytics(user_id)
                return json.dumps(data, ensure_ascii=False)
            except backend_client.BackendError as e:
                return f"FAILED: Could not analyze productivity. Error: {e}"

        def db_create_project_plan(plan_data: ProjectPlan) -> str:
            """
            CRITICAL: USE THIS TOOL FOR ANY REQUEST TO PLAN A TRIP, STUDY SCHEDULE, OR COMPLEX PROJECT.
            Creates a full workspace, spaces, tasks, and subtasks in one atomic call.
            """
            # CHANGE NOTE: now targets the CONFIRMED POST /api/ai/tree endpoint
            # (doc v2 section 6.4, "PersistAgentTreeAsync", status DONE) instead of
            # the earlier assumed /api/ai/projects/persist path. The tree schema does
            # NOT carry priority or a separate due_time field — only a single
            # combined ISO `dueDate`. Both are best-effort combined below; if that
            # combination turns out wrong, ask the backend team for the exact
            # expected datetime format.
            try:
                tree = {
                    "workspace": {
                        "name": plan_data.workspace.name,
                        "description": plan_data.workspace.description,
                        "spaces": [
                            {
                                "name": space.name,
                                "description": "",
                                "iconCode": "",
                                "tasks": [
                                    {
                                        "title": task.title,
                                        "description": task.description,
                                        "dueDate": (f"{task.due_date}T{task.due_time or '00:00'}:00Z"
                                                    if task.due_date else None),
                                        "subtasks": [{"title": st.title, "isCompleted": False} for st in task.subtasks],
                                    }
                                    for task in space.tasks
                                ],
                            }
                            for space in plan_data.spaces
                        ],
                    }
                }
                result = backend_client.persist_tree(user_id, tree)
                tasks_created = sum(len(s.tasks) for s in plan_data.spaces)
                subtasks_created = sum(len(t.subtasks) for s in plan_data.spaces for t in s.tasks)
                return json.dumps({
                    "status": "created", "workspace": plan_data.workspace.name,
                    "tasks_created": tasks_created, "subtasks_created": subtasks_created,
                    "backend_result": result,
                }, ensure_ascii=False)
            except backend_client.BackendError as e:
                return f"FAILED: Error creating project plan: {e}"

        def db_create_workspace(name: str, description: str = "", color: str = "#8A2BE2") -> str:
            """Create a standalone workspace."""
            try:
                ws = backend_client.create_workspace(user_id, name, description, color)
                ws_id = backend_client._field(ws, "id")
                return json.dumps({"status": "created", "workspace_id": ws_id, "name": name})
            except backend_client.BackendError as e:
                return f"FAILED: Error creating workspace: {e}"

        def db_create_space(name: str, workspace_id: int, description: str = "", icon_code: str = "") -> str:
            """Create a single space (sub-folder) inside an existing workspace."""
            try:
                space = backend_client.create_space(user_id, workspace_id, name, description, icon_code)
                sp_id = backend_client._field(space, "id")
                return json.dumps({"status": "created", "space_id": sp_id, "name": name, "workspace_id": workspace_id})
            except backend_client.BackendError as e:
                return f"FAILED: Error creating space. Ensure workspace_id {workspace_id} is valid. Error: {e}"

        def db_delete_item(item_type: str, item_id: int) -> str:
            """Delete a task, note, or workspace. (Space deletion has no confirmed endpoint yet.)"""
            try:
                item_type = item_type.lower()
                if item_type == 'task':
                    wid, sid = backend_client.resolve_task_location(user_id, item_id)
                    backend_client.delete_task(user_id, wid, sid, item_id)
                elif item_type == 'note':
                    wid, sid = backend_client.resolve_note_location(user_id, item_id)
                    backend_client.delete_note(user_id, wid, sid, item_id)
                elif item_type == 'workspace':
                    backend_client.delete_workspace(user_id, item_id)
                else:
                    return "FAILED: No confirmed delete endpoint for this type. Must be task, note, or workspace."
                return "Deleted successfully."
            except backend_client.BackendError as e:
                return f"FAILED: Error deleting item: {e}"

        def db_create_task(title: str, description: str = "", due_date: str = "", priority: str = "medium") -> str:
            """
            Create a single task. NOTE: the only confirmed task-creation path is the
            quick-task endpoint — it always lands in the user's default container and
            does not accept workspace_id/space_id/recurrence/depends_on. For tasks
            that must live inside a specific project, use db_create_project_plan
            instead (with a single task/space) once that structure is confirmed.
            """
            try:
                task = backend_client.create_quick_task(user_id, title=title, description=description, due_date=due_date, priority=priority)
                task_id = backend_client._field(task, "id")
                return json.dumps({"status": "created", "task_id": task_id, "title": title})
            except backend_client.BackendError as e:
                return f"FAILED: Error creating task: {e}"

        def db_create_subtask(title: str, parent_task_id: int) -> str:
            """Create a subtask (child step) for an existing task. Requires resolving the parent task's location first."""
            try:
                wid, sid = backend_client.resolve_task_location(user_id, parent_task_id)
                subtask = backend_client.create_subtask(user_id, wid, sid, parent_task_id, title)
                st_id = backend_client._field(subtask, "id")
                return json.dumps({"status": "created", "subtask_id": st_id, "title": title, "parent_task_id": parent_task_id})
            except backend_client.BackendError as e:
                return f"FAILED: Error creating subtask: {e}"

        def db_get_subtasks(parent_task_id: int) -> str:
            """Retrieve the list of subtasks for a given parent task."""
            try:
                wid, sid = backend_client.resolve_task_location(user_id, parent_task_id)
                task = backend_client.get_task(user_id, wid, sid, parent_task_id)
                return json.dumps(task, ensure_ascii=False) if task else f"FAILED: Task ID {parent_task_id} not found."
            except backend_client.BackendError as e:
                return f"FAILED: Error getting subtasks: {e}"

        def db_complete_all_subtasks(parent_task_id: int) -> str:
            """Mark all subtasks of a specific parent task as completed."""
            try:
                wid, sid = backend_client.resolve_task_location(user_id, parent_task_id)
                task = backend_client.get_task(user_id, wid, sid, parent_task_id)
                subtasks = backend_client._field(task, "subtasks", default=[]) or []
                count = 0
                for st in subtasks:
                    st_id = backend_client._field(st, "id")
                    if not backend_client._field(st, "completed", "isCompleted", default=False):
                        backend_client.set_subtask_status(user_id, wid, sid, parent_task_id, st_id, "Completed")
                        count += 1
                return f"Marked {count} subtask(s) complete."
            except backend_client.BackendError as e:
                return f"FAILED: Error completing subtasks: {e}"

        def db_complete_task(task_id: int) -> str:
            """Mark a specific task as completed."""
            try:
                wid, sid = backend_client.resolve_task_location(user_id, task_id)
                task = backend_client.set_task_status(user_id, wid, sid, task_id, "Completed")
                title = backend_client._field(task, "title") or str(task_id)
                return f"Task '{title}' completed!"
            except backend_client.BackendError as e:
                return f"FAILED: Error completing task: {e}"

        # REMOVED: db_update_task, db_check_task_blocked, db_create_note, db_update_note.
        # CONFIRMED (backend spec, this pass): there is no update-task endpoint in the
        # AI controller at all; no dependency/"blocked" model exists in the database;
        # and notes are owned entirely by the frontend/general backend — the AI's only
        # note-related capability is linking an EXISTING note to an EXISTING task.

        def db_link_note_to_task(task_id: int, note_id: int) -> str:
            """Link an existing note to an existing task. Cannot create or edit notes — both must already exist."""
            try:
                backend_client.link_note_to_task(user_id, task_id, note_id)
                return "Linked note to task."
            except backend_client.BackendError as e:
                return f"FAILED: Error linking note to task: {e}"

        # ── GitHub Tools ──────────────────────────────────────────

        def tool_github_get_issues(repo: str, state: str = "open") -> str:
            """Get open or closed issues from a GitHub repository."""
            try:
                response = requests.get(
                    f"{BACKEND_URL}/github/issues",
                    params={"repo": repo, "state": state, "user_id": user_id},
                    headers={"Authorization": f"Bearer {user_token}"},
                    timeout=10
                )
                data = response.json()
                if data.get("status") == "error":
                    return f"FAILED: {data.get('message')}"
                return json.dumps(data.get("data", {}), ensure_ascii=False)
            except Exception as e:
                return f"FAILED: GitHub error: {e}"

        def tool_github_get_prs(repo: str, state: str = "open") -> str:
            """Get open or closed pull requests from a GitHub repository."""
            try:
                response = requests.get(
                    f"{BACKEND_URL}/github/prs",
                    params={"repo": repo, "state": state, "user_id": user_id},
                    headers={"Authorization": f"Bearer {user_token}"},
                    timeout=10
                )
                data = response.json()
                if data.get("status") == "error":
                    return f"FAILED: {data.get('message')}"
                return json.dumps(data.get("data", {}), ensure_ascii=False)
            except Exception as e:
                return f"FAILED: GitHub PRs error: {e}"

        def tool_github_create_issue(repo: str, title: str, body: str = "", labels: str = "") -> str:
            """Create a new issue in a GitHub repository."""
            try:
                response = requests.post(
                    f"{BACKEND_URL}/github/issues",
                    json={"repo": repo, "title": title, "body": body, "labels": labels, "user_id": user_id},
                    headers={"Authorization": f"Bearer {user_token}"},
                    timeout=10
                )
                data = response.json()
                if data.get("status") == "error":
                    return f"FAILED: {data.get('message')}"
                return f"SUCCESS: Issue created. {json.dumps(data.get('data', {}), ensure_ascii=False)}"
            except Exception as e:
                return f"FAILED: Create issue error: {e}"

        def tool_github_close_issue(repo: str, issue_number: int) -> str:
            """Close an existing issue in a GitHub repository."""
            try:
                response = requests.post(
                    f"{BACKEND_URL}/github/issues/close",
                    json={"repo": repo, "issue_number": issue_number, "user_id": user_id},
                    headers={"Authorization": f"Bearer {user_token}"},
                    timeout=10
                )
                data = response.json()
                if data.get("status") == "error":
                    return f"FAILED: {data.get('message')}"
                return f"SUCCESS: Issue #{issue_number} closed."
            except Exception as e:
                return f"FAILED: Close issue error: {e}"

        def tool_github_get_repos() -> str:
            """Get all GitHub repositories connected to the user's account."""
            try:
                response = requests.get(
                    f"{BACKEND_URL}/github/repos",
                    params={"user_id": user_id},
                    headers={"Authorization": f"Bearer {user_token}"},
                    timeout=10
                )
                data = response.json()
                if data.get("status") == "error":
                    return f"FAILED: {data.get('message')}"
                return json.dumps(data.get("data", {}), ensure_ascii=False)
            except Exception as e:
                return f"FAILED: Get repos error: {e}"

        # ── Gmail Tools ───────────────────────────────────────────

        def tool_gmail_send(to: str, subject: str, body: str, cc: str = "") -> str:
            """Send an email via the user's connected Gmail account."""
            try:
                response = requests.post(
                    f"{BACKEND_URL}/gmail/send",
                    json={"to": to, "subject": subject, "body": body, "cc": cc, "user_id": user_id},
                    headers={"Authorization": f"Bearer {user_token}"},
                    timeout=10
                )
                data = response.json()
                if data.get("status") == "error":
                    return f"FAILED: {data.get('message')}"
                return "SUCCESS: Email sent."
            except Exception as e:
                return f"FAILED: Gmail send error: {e}"

        def tool_gmail_get_inbox(max_results: int = 10, query: str = "") -> str:
            """Get emails from the user's Gmail inbox. Optionally filter with a search query."""
            try:
                response = requests.get(
                    f"{BACKEND_URL}/gmail/inbox",
                    params={"max_results": max_results, "query": query, "user_id": user_id},
                    headers={"Authorization": f"Bearer {user_token}"},
                    timeout=10
                )
                data = response.json()
                if data.get("status") == "error":
                    return f"FAILED: {data.get('message')}"
                return json.dumps(data.get("data", {}), ensure_ascii=False)
            except Exception as e:
                return f"FAILED: Gmail inbox error: {e}"

        def tool_gmail_get_message(message_id: str) -> str:
            """Get the full details of a specific Gmail message by its ID."""
            try:
                response = requests.get(
                    f"{BACKEND_URL}/gmail/message",
                    params={"message_id": message_id, "user_id": user_id},
                    headers={"Authorization": f"Bearer {user_token}"},
                    timeout=10
                )
                data = response.json()
                if data.get("status") == "error":
                    return f"FAILED: {data.get('message')}"
                return json.dumps(data.get("data", {}), ensure_ascii=False)
            except Exception as e:
                return f"FAILED: Get message error: {e}"

        def tool_gmail_reply(message_id: str, body: str) -> str:
            """Reply to an existing Gmail email thread."""
            try:
                response = requests.post(
                    f"{BACKEND_URL}/gmail/reply",
                    json={"message_id": message_id, "body": body, "user_id": user_id},
                    headers={"Authorization": f"Bearer {user_token}"},
                    timeout=10
                )
                data = response.json()
                if data.get("status") == "error":
                    return f"FAILED: {data.get('message')}"
                return "SUCCESS: Reply sent."
            except Exception as e:
                return f"FAILED: Gmail reply error: {e}"

        def tool_gmail_save_draft(to: str, subject: str, body: str) -> str:
            """Save an email as a draft in Gmail without sending it."""
            try:
                response = requests.post(
                    f"{BACKEND_URL}/gmail/draft",
                    json={"to": to, "subject": subject, "body": body, "user_id": user_id},
                    headers={"Authorization": f"Bearer {user_token}"},
                    timeout=10
                )
                data = response.json()
                if data.get("status") == "error":
                    return f"FAILED: {data.get('message')}"
                return "SUCCESS: Draft saved."
            except Exception as e:
                return f"FAILED: Save draft error: {e}"

        # ── Google Calendar Tools ─────────────────────────────────

        def tool_calendar_get_events(date_from: str, date_to: str) -> str:
            """Get Google Calendar events between two dates. Format: YYYY-MM-DD."""
            try:
                response = requests.get(
                    f"{BACKEND_URL}/calendar/events",
                    params={"date_from": date_from, "date_to": date_to, "user_id": user_id},
                    headers={"Authorization": f"Bearer {user_token}"},
                    timeout=10
                )
                data = response.json()
                if data.get("status") == "error":
                    return f"FAILED: {data.get('message')}"
                return json.dumps(data.get("data", {}), ensure_ascii=False)
            except Exception as e:
                return f"FAILED: Calendar get events error: {e}"

        def tool_calendar_create_event(title: str, start: str, end: str, description: str = "", location: str = "") -> str:
            """Create a new event in Google Calendar. start/end format: YYYY-MM-DDTHH:MM."""
            try:
                response = requests.post(
                    f"{BACKEND_URL}/calendar/events",
                    json={"title": title, "start": start, "end": end,
                          "description": description, "location": location, "user_id": user_id},
                    headers={"Authorization": f"Bearer {user_token}"},
                    timeout=10
                )
                data = response.json()
                if data.get("status") == "error":
                    return f"FAILED: {data.get('message')}"
                return f"SUCCESS: Event created. {json.dumps(data.get('data', {}), ensure_ascii=False)}"
            except Exception as e:
                return f"FAILED: Create event error: {e}"

        def tool_calendar_update_event(event_id: str, title: str = "", start: str = "", end: str = "") -> str:
            """Update an existing Google Calendar event by its ID."""
            try:
                updates = {k: v for k, v in [("title", title), ("start", start), ("end", end)] if v}
                response = requests.put(
                    f"{BACKEND_URL}/calendar/events",
                    json={"event_id": event_id, **updates, "user_id": user_id},
                    headers={"Authorization": f"Bearer {user_token}"},
                    timeout=10
                )
                data = response.json()
                if data.get("status") == "error":
                    return f"FAILED: {data.get('message')}"
                return "SUCCESS: Event updated."
            except Exception as e:
                return f"FAILED: Update event error: {e}"

        def tool_calendar_delete_event(event_id: str) -> str:
            """Delete a Google Calendar event by its ID."""
            try:
                response = requests.delete(
                    f"{BACKEND_URL}/calendar/events",
                    json={"event_id": event_id, "user_id": user_id},
                    headers={"Authorization": f"Bearer {user_token}"},
                    timeout=10
                )
                data = response.json()
                if data.get("status") == "error":
                    return f"FAILED: {data.get('message')}"
                return "SUCCESS: Event deleted."
            except Exception as e:
                return f"FAILED: Delete event error: {e}"

        # ── Integration Status ────────────────────────────────────

        def tool_check_integrations() -> str:
            """Check which external integrations (GitHub, Gmail, Calendar) are connected for the user."""
            try:
                response = requests.get(
                    f"{BACKEND_URL}/status",
                    params={"user_id": user_id},
                    headers={"Authorization": f"Bearer {user_token}"},
                    timeout=10
                )
                data = response.json()
                if data.get("status") == "error":
                    return f"FAILED: {data.get('message')}"
                return json.dumps(data.get("data", {}), ensure_ascii=False)
            except Exception as e:
                return f"FAILED: Check integrations error: {e}"

        return [
            # ── Original tools ────────────────────────────────────
            tool_get_context, tool_daily_briefing, tool_save_memory, tool_get_memory,
            tool_web_search, tool_analyze_productivity,
            db_create_project_plan, db_create_workspace, db_create_space, db_delete_item,
            db_create_task, db_create_subtask, db_get_subtasks, db_complete_all_subtasks,
            db_complete_task, db_link_note_to_task,
            # ── GitHub ────────────────────────────────────────────
            tool_github_get_issues, tool_github_get_prs, tool_github_create_issue,
            tool_github_close_issue, tool_github_get_repos,
            # ── Gmail ─────────────────────────────────────────────
            tool_gmail_send, tool_gmail_get_inbox, tool_gmail_get_message,
            tool_gmail_reply, tool_gmail_save_draft,
            # ── Google Calendar ───────────────────────────────────
            tool_calendar_get_events, tool_calendar_create_event,
            tool_calendar_update_event, tool_calendar_delete_event,
            # ── Integrations Status ───────────────────────────────
            tool_check_integrations,
        ]

    def _build_short_term_context(self, user_id: str) -> str:
        # REMOVED: this used to filter self.db.get_tasks/workspaces/spaces by a
        # local `created_at` timestamp to remind the agent of IDs it just created.
        # There's no flat listing endpoint anymore (see _aggregate_state), so doing
        # this via backend_client would mean a full O(workspaces x spaces) walk on
        # every single turn just to build a hint string — and `created_at` was never
        # confirmed as a field the .NET responses actually include. Rather than ship
        # an expensive call that may silently always return nothing, this is disabled
        # until the backend confirms a cheap way to get "recently created" items.
        return ""

    def _detect_urgency_hint(self, message: str) -> str:
        urgent_words = ['urgent', 'asap', 'emergency', 'immediately', 'right now', 'critical', 'important', 'crucial', 'today', 'now', 'عاجل', 'مهم', 'ضروري', 'فوري', 'الآن', 'اليوم']
        if any(w in message.lower() for w in urgent_words):
            return "\n[AGENT HINT: urgency detected — use priority='high' for any tasks created from this request]"
        return ""

    def _build_agent(self, selected_tools, user_id, user_message):
        # CHANGE NOTE: proactive semantic-memory injection removed (see note above
        # _retrieve_tools). Also removed the hardcoded "the user is Yahya..." bio —
        # the multi-tenant identity model in the addendum means this agent now serves
        # many distinct users scoped by X-User-Id, so a single user's bio can't be
        # baked into the shared system prompt.
        instruction = (
            "You are iGenda — an elite, proactive AI productivity agent.\n\n"
            "=== YOUR CORE DIRECTIVES ===\n"
            "1. CONTEXT FIRST: For planning, scheduling, or 'what should I do' — call tool_get_context() first.\n"
            "2. DAILY BRIEFING: When Yahya says 'daily briefing' or 'good morning' — call tool_daily_briefing().\n"
            "3. BULK PROJECT CREATION: For trips, study plans, or complex projects, you MUST use `db_create_project_plan`. NEVER use individual tools (`db_create_workspace`, `db_create_space`, `db_create_task`) for a new project because you cannot chain newly created IDs in parallel. The bulk tool handles everything perfectly.\n"
            "4. ISOLATION RULE: Single tasks belong to NO workspace (workspace_id=None). ONLY assign a single task to a workspace if explicitly commanded or fixing a failed tool.\n"
            "5. SELF-CORRECT: If a tool call doesn't produce expected results (returns FAILED), analyze your mistake, rewrite the parameters/JSON, and try again immediately.\n"
            "6. LANGUAGE: ALWAYS respond in the SAME language Yahya used. Never mix languages.\n"
        )

        self.agent = Agent(name="iGenda_Core_Agent", model="gemini-2.5-flash", description="Elite Planner for iGenda.", instruction=instruction, tools=selected_tools)
        self.runner = Runner(agent=self.agent, app_name="iGenda_App", session_service=self.session_service)

    def _ensure_session(self, user_id: str):
        session_id = f"{user_id}_complex_session"

        session = _run_async(
            self.session_service.get_session(
                app_name="iGenda_App",
                user_id=user_id,
                session_id=session_id,
            )
        )

        if session is None:
            print(f"Creating session {session_id}")

            _run_async(
                self.session_service.create_session(
                    app_name="iGenda_App",
                    user_id=user_id,
                    session_id=session_id,
                    state={}
                )
            )

        return session_id
    

    def process_message(self, user_id: str, user_message: str, language: str = 'en', message_type: str = 'text', context_data: str = None, user_token: str = "") -> dict:
        start_time = time.time()
        tool_events = []
        try:
            session_id = self._ensure_session(user_id)
            
            relevant_tools = self._retrieve_tools(user_id, user_message, top_k=8, user_token=user_token)
            self._build_agent(relevant_tools, user_id, user_message)

            if message_type == 'document_text' and context_data:
                max_chars = 12000
                if len(context_data) > max_chars: context_data = context_data[:max_chars] + "\n[Document truncated]"
                user_message = f"I uploaded a document. Instruction: {user_message}\n\n--- DOCUMENT ---\n{context_data}\n--- END DOCUMENT ---"

            lang_hint = "\n[LANGUAGE DIRECTIVE: Respond in Arabic. Create all task/note titles in Arabic.]" if bool(re.search(r'[\u0600-\u06FF]', user_message)) or language == 'ar' else "\n[LANGUAGE DIRECTIVE: Respond in English. Create all task/note titles in English.]"
            user_message = user_message + lang_hint + self._build_short_term_context(user_id) + self._detect_urgency_hint(user_message)

            self.db.save_message(user_id, 'user', user_message)
            content = types.Content(role='user', parts=[types.Part.from_text(text=user_message)])
            final_text = "I couldn't generate a response."

            max_retries = 3
            attempt = 0
            success = False
            
            while attempt < max_retries and not success:
                attempt += 1
                tool_failed = False
                
                for event in self.runner.run(user_id=user_id, session_id=session_id, new_message=content):
                    if hasattr(event, 'content') and event.content:
                        for part in getattr(event.content, 'parts', []):
                            if hasattr(part, 'function_call') and part.function_call:
                                tool_events.append({"type": "tool_call", "name": part.function_call.name, "args": dict(part.function_call.args)})
                            
                            elif hasattr(part, 'function_response') and part.function_response:
                                result_str = str(part.function_response.response)
                                tool_events.append({"type": "tool_result", "name": part.function_response.name, "result": result_str[:300]})
                                
                                result_lower = result_str.lower()
                                if "failed" in result_lower or "error" in result_lower or "not found" in result_lower:
                                    tool_failed = True
                                    logging.warning(f"Complex Agent tool failed on attempt {attempt}: {result_str}")
                                    correction_prompt = f"[SYSTEM: Your last tool call failed with error: {result_str}. Analyze your JSON/parameters, FIX the mistake, and execute again immediately.]"
                                    content = types.Content(role='user', parts=[types.Part.from_text(text=correction_prompt)])
                                    break 
                                    
                            elif hasattr(part, 'text') and part.text:
                                final_text = part.text
                    
                    if tool_failed:
                        break 
                
                if not tool_failed:
                    success = True

            self.db.save_message(user_id, 'model', final_text)
            state = _aggregate_state(user_id)
            return {
                "response_message": final_text, "tool_events": tool_events, **state,
                "processing_time": round(time.time() - start_time, 2),
                "ai_metadata": {"model_used": "gemini-adk-complex-structured", "retries": attempt - 1, "tools_in_context": len(relevant_tools)}
            }
        except Exception as e:
            logging.error(f"Complex Agent Error: {e}")
            raise e

# ======================================================================================
# LIGHTWEIGHT AGENT: The Fast Lane for simple CRUD & Subtasks
# ======================================================================================
class AdkActionHandler:
    def __init__(self, database):
        self.db = database
        self.session_service = InMemorySessionService()
        print("ComplexHandler", id(self))
        print("SessionService", id(self.session_service))

    def _register_tools(self, user_id: str):
        db = self.db

        def db_find_task_id(search_term: str) -> str:
            """Find the parent_id to create a subtask, or need to update/complete a task."""
            # NOTE: no flat task-listing endpoint exists, so this walks
            # workspaces/spaces (same cost tradeoff as _aggregate_state).
            try:
                state = _aggregate_state(user_id)
                matches = []
                for t in state["tasks"]:
                    title = backend_client._field(t, "title", default="")
                    desc = backend_client._field(t, "description", default="")
                    if search_term.lower() in title.lower() or search_term.lower() in (desc or "").lower():
                        matches.append(f"ID: {backend_client._field(t, 'id')} | Title: {title}")
                if not matches: return "FAILED: No matching tasks found. Create it as a new main task instead."
                return "MATCHES: " + " ; ".join(matches[:3])
            except backend_client.BackendError as e:
                return f"FAILED: Error searching for task: {e}"

        def db_create_task(title: str, description: str = "", due_date: str = "", priority: str = "medium") -> str:
            """Create a single, flat task with no explicit workspace/space."""
            try:
                data = backend_client.create_quick_task(user_id, title=title, description=description, due_date=due_date, priority=priority)
                task_id = backend_client._field(data, "id")
                return json.dumps({"status": "created", "task_id": task_id, "title": title})
            except backend_client.BackendError as e:
                return f"FAILED: Error creating task: {e}"

        def db_create_subtask(title: str, parent_task_id: int) -> str:
            """Break a task into a subtask. MUST call db_find_task_id FIRST to get the parent_task_id."""
            try:
                wid, sid = backend_client.resolve_task_location(user_id, parent_task_id)
                subtask = backend_client.create_subtask(user_id, wid, sid, parent_task_id, title)
                st_id = backend_client._field(subtask, "id")
                return json.dumps({"status": "created", "subtask_id": st_id, "title": title})
            except backend_client.BackendError as e:
                return f"FAILED: Error creating subtask: {e}"

        def db_complete_task(task_id: int) -> str:
            try:
                wid, sid = backend_client.resolve_task_location(user_id, task_id)
                task = backend_client.set_task_status(user_id, wid, sid, task_id, "Completed")
                title = backend_client._field(task, "title") or str(task_id)
                return f"Task '{title}' completed!"
            except backend_client.BackendError as e:
                return f"FAILED: Error completing task: {e}"

        # REMOVED: db_update_task — no confirmed update-task endpoint exists anywhere.

        def db_delete_item(item_type: str, item_id: int) -> str:
            try:
                if item_type.lower() == 'task':
                    wid, sid = backend_client.resolve_task_location(user_id, item_id)
                    backend_client.delete_task(user_id, wid, sid, item_id)
                elif item_type.lower() == 'note':
                    wid, sid = backend_client.resolve_note_location(user_id, item_id)
                    backend_client.delete_note(user_id, wid, sid, item_id)
                else:
                    return "FAILED: Invalid type. Must be task or note."
                return "Deleted."
            except backend_client.BackendError as e:
                return f"FAILED: Error deleting item: {e}"

        # REMOVED: db_create_note — confirmed no note-creation endpoint exists in
        # the AI controller. Notes are owned by the frontend/general backend; the
        # only AI-facing note capability is linking an existing note to a task.

        return [db_find_task_id, db_create_task, db_create_subtask, db_complete_task, db_delete_item]

    def _build_agent(self, tools):
        instruction = (
            "You are iGenda's Fast Action Agent. Your ONLY job is to execute quick commands.\n"
            "1. NO CHAT: Just execute the tool and confirm.\n"
            "2. SUBTASKS: If asked to add a subtask to an existing task, you MUST call `db_find_task_id(search_term)` FIRST to find the parent_task_id.\n"
            "3. EXECUTION: Once you have the parent_task_id, call `db_create_subtask`.\n"
            "4. NO EDITING: There is no way to update an existing task's fields or create/edit notes. If asked, say so honestly instead of attempting it.\n"
            "5. BILINGUAL: Reply in the same language as the user."
        )
        self.agent = Agent(name="iGenda_Action_Agent", model="gemini-2.5-flash", instruction=instruction, tools=tools)
        self.runner = Runner(agent=self.agent, app_name="iGenda_App", session_service=self.session_service)

    def process_message(self, user_id: str, user_message: str, language: str = 'en') -> dict:
        start_time = time.time()
        tool_events = []
        session_id = f"{user_id}_action_session"
        
        session = _run_async(self.session_service.get_session(app_name="iGenda_App", user_id=user_id, session_id=session_id))
        if session is None:
            _run_async(self.session_service.create_session(app_name="iGenda_App", user_id=user_id, session_id=session_id))
        
        tools = self._register_tools(user_id)
        self._build_agent(tools)
        
        lang_hint = "\n[LANGUAGE DIRECTIVE: Respond in Arabic.]" if bool(re.search(r'[\u0600-\u06FF]', user_message)) else "\n[LANGUAGE DIRECTIVE: Respond in English.]"
        content = types.Content(role='user', parts=[types.Part.from_text(text=user_message + lang_hint)])
        final_text = "Action completed."

        max_retries = 3
        attempt = 0
        success = False
        
        while attempt < max_retries and not success:
            attempt += 1
            tool_failed = False

            for event in self.runner.run(user_id=user_id, session_id=session_id, new_message=content):
                if hasattr(event, 'content') and event.content:
                    for part in getattr(event.content, 'parts', []):
                        if hasattr(part, 'function_call') and part.function_call:
                            tool_events.append({"type": "tool_call", "name": part.function_call.name, "args": dict(part.function_call.args)})
                        elif hasattr(part, 'function_response') and part.function_response:
                            result_str = str(part.function_response.response)
                            tool_events.append({"type": "tool_result", "name": part.function_response.name, "result": result_str[:300]})
                            
                            result_lower = result_str.lower()
                            if "not found" in result_lower or "error" in result_lower or "failed" in result_lower:
                                tool_failed = True
                                logging.warning(f"Action Agent tool failed on attempt {attempt}: {result_str}")
                                correction_prompt = f"[SYSTEM: Tool failed: {result_str}. Try a different ID or fix the parameters and execute again.]"
                                content = types.Content(role='user', parts=[types.Part.from_text(text=correction_prompt)])
                                break
                                
                        elif hasattr(part, 'text') and part.text:
                            final_text = part.text
                
                if tool_failed:
                    break
            
            if not tool_failed:
                success = True

        state = _aggregate_state(user_id)
        return {
            "response_message": final_text, "tool_events": tool_events, **state,
            "processing_time": round(time.time() - start_time, 2),
            "ai_metadata": {"model_used": "gemini-adk-action", "retries": attempt - 1}
        }

# ======================================================================================
# MASTER HANDLER & INTENT ROUTER
# ======================================================================================
class EnhancedAIHandler:
    def __init__(self):
        # CHANGE NOTE: EnhancedRAGHandler (offline fallback) removed per the
        # integration doc's "Offline Vector Indexing" deprecation. There is now no
        # fallback path if Gemini/ADK is unavailable — see process_multimodal_message.
        self.summarizer = LocalSummarizer()
        self.api_key = os.environ.get("GEMINI_API_KEY")
        self.use_adk = ADK_AVAILABLE and bool(self.api_key)
        self.heavy_core_agent = None
        self.light_action_agent = None
        logging.info(f"AI Handler initialized. ADK active: {self.use_adk}")

    def _route_intent(self, user_message: str) -> str:
        instruction = (
            "You are an intent classification router for an AI productivity app. "
            "The user may speak in English or Arabic. "
            "Classify the user's message into EXACTLY ONE of these categories:\n\n"
            "1. ACTION: Simple, self-contained CRUD operations where ALL needed information "
            "is already in the user's message. Creating, updating, deleting a single task, note, or reminder. "
            "(e.g., 'add a task to buy milk', 'remind me at 5pm', 'مهمة', 'ذكرني', 'احذف').\n"
            "2. COMPLEX: Anything requiring external data lookups (news, sports, weather, research), "
            "multi-step planning, workspaces, complex projects, OR saving a note/task whose content "
            "must first be fetched or generated. "
            "(e.g., 'summarize the match and save it', 'plan a trip', 'خطط', 'جدول', 'مشروع', 'ابحث').\n"
            "3. CHAT: Casual conversation, greetings, or general questions not related to database tasks. "
            "(e.g., 'hello', 'how are you', 'مرحبا', 'كيف حالك').\n\n"
            "RULE: If the request involves fetching or researching external information BEFORE saving, "
            "it is COMPLEX regardless of whether the final action is just creating a note or task.\n\n"
            "Reply with ONLY the category word: ACTION, COMPLEX, or CHAT."
        )
        try:
            client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=user_message,
                config=types.GenerateContentConfig(system_instruction=instruction, temperature=0.0)
            )
            intent = response.text.strip().upper()
            if intent in ["ACTION", "COMPLEX", "CHAT"]: return intent
            return "COMPLEX"
        except Exception as e:
            logging.error(f"Routing failed: {e}")
            return "COMPLEX"

    def process_multimodal_message(self, user_message, message_type='text', context_data=None, database=None, language='en', user_id=None, user_token=''):
        # CHANGE NOTE: default user_id changed from the hardcoded 'yahya' to None.
        # app.py now rejects requests with no verified X-User-Id before this is ever
        # called, but keeping a real-looking default here would silently mask that
        # bug in any other caller instead of failing loudly.
        if not user_id:
            return {
                "response_message": "Unable to identify the requesting user.",
                "tool_events": [], "tasks": [], "notes": [], "workspaces": [], "spaces": [],
                "ai_metadata": {"model_used": "none", "error": "missing_user_id"},
            }
        if self.use_adk and database:
            intent = self._route_intent(user_message)
            logging.info(f"Router classified intent as: {intent} for user {user_id}")
            
            if intent == "CHAT":
                try:
                    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
                    sys_inst = (
                        "You are AiGenda, an AI productivity assistant. "
                        "When a user asks what you can do, give a short but concrete list of your capabilities: "
                        "managing tasks and subtasks, notes, workspaces, reminders, web search, sports/news lookups, "
                        "GitHub issues, Gmail, complex project planning, and daily briefings. "
                        "Be warm and conversational. Reply in the user's exact language."
                    )
                    response = client.models.generate_content(
                        model='gemini-2.5-flash', contents=user_message,
                        config=types.GenerateContentConfig(system_instruction=sys_inst, temperature=0.5)
                    )
                    return {
                        "response_message": response.text, "tool_events": [], 
                        "tasks": database.get_tasks(user_id=user_id), "notes": database.get_notes(user_id=user_id),
                        "workspaces": database.get_workspaces(user_id=user_id), "spaces": database.get_spaces(user_id=user_id),
                        "ai_metadata": {"model_used": "gemini-chat-only"}
                    }
                except Exception:
                    pass

            if intent == "ACTION":
                if not self.light_action_agent: self.light_action_agent = AdkActionHandler(database)
                try: return self.light_action_agent.process_message(user_id=user_id, user_message=user_message, language=language)
                except Exception as e: logging.warning(f"Action Agent failed: {e}. Falling back to Complex.")

            if not self.heavy_core_agent: self.heavy_core_agent = AdkComplexHandler(database)
            try:
                return self.heavy_core_agent.process_message(
                    user_id=user_id, user_message=user_message, language=language,
                    message_type=message_type, context_data=context_data, user_token=user_token
                )
            except Exception as e:
                logging.warning(f"ADK Complex failed, falling back to offline. Error: {e}")

        if message_type == 'document_text':
            text_to_process = context_data if context_data else user_message
            summary, title = self.summarizer.summarize(text_to_process)
            if database:
                database.create_note(user_id=user_id, title=f"Summary: {title}", content=summary, category="Documents", language="en")
                return {"response_message": "Document summarized offline.", "tool_events": [], "tasks": database.get_tasks(user_id=user_id), "notes": database.get_notes(user_id=user_id), "workspaces": database.get_workspaces(user_id=user_id), "spaces": database.get_spaces(user_id=user_id)}
            return {"response_message": "Database not provided.", "tool_events": [], "tasks": [], "notes": [], "workspaces": [], "spaces": []}

        # CHANGE NOTE: the offline RAG fallback that used to run here
        # (self.enhanced_rag.get_fallback_response) is removed per the integration
        # doc — "the sidecar relies entirely on remote, cloud-hosted API execution
        # calls." That means there is now genuinely no fallback if ADK/Gemini is
        # unavailable (missing GEMINI_API_KEY, import failure, etc.) or if the request
        # doesn't hit the ADK path above for some other reason. This is a real
        # reduction in resilience versus the old behavior, not a neutral swap — surface
        # it to users as a clear error rather than pretending nothing changed.
        logging.error(
            "No fallback available: ADK/Gemini path did not handle this request "
            "(use_adk=%s, database_provided=%s).", self.use_adk, bool(database)
        )
        return {
            "response_message": (
                "I can't process that right now — the AI service is unavailable and "
                "there's no offline fallback in this build. Please try again shortly."
            ),
            "tool_events": [], "tasks": [], "notes": [], "workspaces": [], "spaces": [],
            "ai_metadata": {"model_used": "none", "error": "no_fallback_available"},
        }

    def _is_arabic(self, text):
        return bool(re.search(r'[\u0600-\u06FF]', text))

    def check_model_health(self):
        if self.use_adk: return {'status': 'healthy', 'model': 'gemini-adk-routed'}
        return {'status': 'degraded', 'model': None, 'reason': 'ADK/Gemini unavailable, no fallback configured'}
