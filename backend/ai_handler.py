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

from rag_handler import EnhancedRAGHandler
from nlp_handler import LocalSummarizer
import requests

BACKEND_URL = os.getenv("BACKEND_URL")

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
        self.embedder = EnhancedRAGHandler().model
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

    def _get_semantic_memory(self, user_id: str, query: str, top_k: int = 3) -> str:
        """Retrieves only the most relevant memory facts using vector search."""
        try:
            memories = self.db.get_all_memory(user_id=user_id)
            if not memories:
                return "No persistent memory found."
            
            mem_items = list(memories.items())
            mem_texts = [f"{k}: {v}" for k, v in mem_items]
            
            query_vec = self.embedder.encode([query])
            mem_vecs = self.embedder.encode(mem_texts)
            similarities = cosine_similarity(query_vec, mem_vecs)[0]
            
            top_indices = np.argsort(similarities)[::-1][:top_k]
            relevant_memories = [mem_texts[i] for i in top_indices if similarities[i] > 0.2]
            
            if not relevant_memories:
                return "No highly relevant memory found for this specific query."
            return "\n".join(relevant_memories)
        except Exception as e:
            logging.warning(f"Semantic memory error: {e}")
            return "Memory unavailable."

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
            return json.dumps({
                "now": datetime.now().strftime('%Y-%m-%d %H:%M'),
                "day_of_week": datetime.now().strftime('%A'),
                "todays_tasks": db.get_todays_tasks(user_id=user_id),
                "overdue_tasks": db.get_overdue_tasks(user_id=user_id),
                "upcoming_tasks": db.get_upcoming_tasks(user_id=user_id, days=3),
            }, ensure_ascii=False)

        def tool_daily_briefing() -> str:
            """Generate a daily briefing, morning report, or daily summary."""
            return json.dumps(db.get_daily_briefing(user_id=user_id), ensure_ascii=False)

        def tool_save_memory(key: str, value: str) -> str:
            """Remember facts, user preferences, habits, or personal data permanently."""
            try:
                db.save_memory(user_id=user_id, key=key, value=value)
                return f"Remembered: {key} = {value}"
            except Exception as e:
                return f"FAILED: Could not save memory. Error: {e}"

        def tool_get_memory(key: str) -> str:
            """Retrieve specific saved memories or preferences about the user."""
            val = db.get_memory(user_id=user_id, key=key)
            return val if val else f"FAILED: No memory found for key '{key}'"

        def tool_web_search(query: str) -> str:
            """Search the internet for external facts, news, or research."""
            try:
                from ddgs import DDGS
                results = DDGS().text(query, max_results=3)
                if not results: return "FAILED: No results found on the web."
                return "\n\n".join([f"Title: {r['title']}\nSnippet: {r['body']}" for r in results])
            except Exception as e:
                return f"FAILED: Web search error: {e}"

        def tool_search_my_data(query: str, item_type: str = "all") -> str:
            """Search the internal database for existing tasks, notes, or projects."""
            return json.dumps(db.search_data(user_id=user_id, query=query, item_type=item_type), ensure_ascii=False)

        def tool_check_schedule(date: str, time: str) -> str:
            """Check if a specific time slot is free or conflicts with existing tasks."""
            return db.check_schedule_conflict(user_id=user_id, check_date=date, check_time=time)

        def tool_analyze_productivity() -> str:
            """Get statistics, analytics, and habits about completed tasks and procrastination."""
            try:
                data = db.get_smart_analytics(user_id=user_id)
                return json.dumps(data, ensure_ascii=False)
            except Exception as e:
                return f"FAILED: Could not analyze productivity. Error: {e}"

        def db_create_project_plan(plan_data: ProjectPlan) -> str:
            """
            CRITICAL: USE THIS TOOL FOR ANY REQUEST TO PLAN A TRIP, STUDY SCHEDULE, OR COMPLEX PROJECT.
            Creates a full workspace, spaces, tasks, and subtasks perfectly structured using Pydantic.
            """
            try:
                ws = db.create_workspace(user_id=user_id, name=plan_data.workspace.name, description=plan_data.workspace.description, color=plan_data.workspace.color)
                
                tasks_created = 0
                subtasks_created = 0
                
                for space_data in plan_data.spaces:
                    sp = db.create_space(user_id=user_id, name=space_data.name, workspace_id=ws['id'])
                    for task_data in space_data.tasks:
                        task = db.create_task(
                            user_id=user_id,
                            title=task_data.title, 
                            description=task_data.description,
                            due_date=task_data.due_date,
                            due_time=task_data.due_time,
                            priority=task_data.priority, 
                            workspace_id=ws['id'], 
                            space_id=sp['id']
                        )
                        tasks_created += 1
                        
                        for sub in task_data.subtasks:
                            db.create_task(user_id=user_id, title=sub.title, parent_id=task['id'], workspace_id=ws['id'], space_id=sp['id'])
                            subtasks_created += 1
                            
                return f"SUCCESS: Created Workspace '{ws['name']}' with {len(plan_data.spaces)} spaces, {tasks_created} tasks, and {subtasks_created} subtasks perfectly nested."
            except Exception as e:
                return f"FAILED to create plan: {e}"

        def db_create_workspace(name: str, description: str = "", color: str = "#8A2BE2") -> str:
            """Create a single new workspace (top-level project folder). Do not use for complex projects."""
            try:
                ws = db.create_workspace(user_id=user_id, name=name, description=description, color=color)
                return json.dumps({"status": "created", "workspace_id": ws['id'], "name": ws['name']})
            except Exception as e: return f"FAILED: Error creating workspace: {e}"

        def db_create_space(name: str, workspace_id: int, description: str = "", color: str = "#8A2BE2") -> str:
            """Create a single space (sub-folder) inside an existing workspace."""
            try:
                space = db.create_space(user_id=user_id, name=name, workspace_id=workspace_id, description=description, color=color)
                return json.dumps({"status": "created", "space_id": space['id'], "name": space['name'], "workspace_id": workspace_id})
            except Exception as e: return f"FAILED: Error creating space. Ensure workspace_id {workspace_id} is valid. Error: {e}"

        def db_update_workspace_color(workspace_id: int, color: str) -> str:
            """Change the visual color of a workspace."""
            try:
                ws = db.update_workspace(user_id=user_id, workspace_id=workspace_id, updates={'color': color})
                return "Workspace color updated." if ws else f"FAILED: Workspace ID {workspace_id} not found."
            except Exception as e: return f"FAILED: Error updating color: {e}"

        def db_delete_item(item_type: str, item_id: int) -> str:
            """Delete a task, note, workspace, or space from the database."""
            try:
                item_type = item_type.lower()
                if item_type == 'task': success = db.delete_task(user_id=user_id, task_id=item_id)
                elif item_type == 'note': success = db.delete_note(user_id=user_id, note_id=item_id)
                elif item_type == 'workspace': success = db.delete_workspace(user_id=user_id, workspace_id=item_id)
                elif item_type == 'space': success = db.delete_space(user_id=user_id, space_id=item_id)
                else: return "FAILED: Invalid type. Must be task, note, workspace, or space."
                return "Deleted successfully." if success else f"FAILED: ID {item_id} not found."
            except Exception as e: return f"FAILED: Error deleting item: {e}"

        def db_create_task(title: str, description: str = "", due_date: str = "",
                           due_time: str = "", priority: str = "medium",
                           workspace_id: int = None, space_id: int = None,
                           recurrence: str = None, depends_on: int = None) -> str:
            """Create a single, isolated task."""
            try:
                task = db.create_task(
                    user_id=user_id, title=title, description=description, due_date=due_date,
                    due_time=due_time, priority=priority, workspace_id=workspace_id,
                    space_id=space_id, recurrence=recurrence, depends_on=depends_on
                )
                return json.dumps({"status": "created", "task_id": task['id'], "title": task['title']})
            except Exception as e: return f"FAILED: Error creating task. Check if workspace_id/space_id are valid. Error: {e}"

        def db_create_subtask(title: str, parent_task_id: int, description: str = "",
                              priority: str = "medium", due_date: str = "") -> str:
            """Create a subtask (child step) for an existing task."""
            try:
                parent = db.get_task_with_subtasks(user_id=user_id, task_id=parent_task_id)
                if not parent: return f"FAILED: Parent task ID {parent_task_id} not found."
                task = db.create_task(user_id=user_id, title=title, description=description, due_date=due_date or parent.get('due_date', ''), priority=priority, workspace_id=parent.get('workspace_id'), space_id=parent.get('space_id'), parent_id=parent_task_id)
                return json.dumps({"status": "created", "subtask_id": task['id'], "title": task['title']})
            except Exception as e: return f"FAILED: Error creating subtask: {e}"

        def db_get_subtasks(parent_task_id: int) -> str:
            """Retrieve the list of subtasks for a given parent task."""
            try:
                data = db.get_task_with_subtasks(user_id=user_id, task_id=parent_task_id)
                return json.dumps(data, ensure_ascii=False) if data else f"FAILED: Task ID {parent_task_id} not found."
            except Exception as e: return f"FAILED: Error getting subtasks: {e}"

        def db_complete_all_subtasks(parent_task_id: int) -> str:
            """Mark all subtasks of a specific parent task as completed."""
            try:
                subtasks = db.get_subtasks(user_id=user_id, parent_id=parent_task_id)
                count = 0
                for st in subtasks['subtasks']:
                    if not st.get('completed'):
                        db.complete_task(user_id=user_id, task_id=st['id'])
                        count += 1
                return f"Marked {count} subtask(s) complete."
            except Exception as e: return f"FAILED: Error completing subtasks: {e}"

        def db_complete_task(task_id: int) -> str:
            """Mark a specific task as completed."""
            try:
                task = db.complete_task(user_id=user_id, task_id=task_id)
                return f"Task '{task['title']}' completed!" if task else f"FAILED: Task ID {task_id} not found."
            except Exception as e: return f"FAILED: Error completing task: {e}"

        def db_update_task(task_id: int, title: str = None, description: str = None,
                           due_date: str = None, due_time: str = None, priority: str = None,
                           recurrence: str = None, depends_on: int = None, workspace_id: int = None,
                           space_id: int = None) -> str:
            """Modify the details of an existing task."""
            try:
                updates = {k: v for k, v in [('title', title), ('description', description), ('due_date', due_date), ('due_time', due_time), ('priority', priority), ('recurrence', recurrence), ('depends_on', depends_on), ('workspace_id', workspace_id), ('space_id', space_id)] if v is not None}
                task = db.update_task(user_id=user_id, task_id=task_id, updates=updates)
                return f"Task updated: {task['title']}" if task else f"FAILED: Task ID {task_id} not found."
            except Exception as e: return f"FAILED: Error updating task: {e}"

        def db_link_note_to_task(task_id: int, note_id: int) -> str:
            """Link an existing note to an existing task."""
            try:
                task = db.update_task(user_id=user_id, task_id=task_id, updates={'linked_note_id': note_id})
                note = db.update_note(user_id=user_id, note_id=note_id, updates={'linked_task_id': task_id})
                return f"Linked note to task." if task and note else "FAILED: Task or Note ID not found. Could not link."
            except Exception as e: return f"FAILED: Error linking item: {e}"

        def db_check_task_blocked(task_id: int) -> str:
            """Check if a task has dependencies preventing it from being completed."""
            try:
                blocked = db.is_task_blocked(user_id=user_id, task_id=task_id)
                return f"Task {task_id} is {'BLOCKED' if blocked else 'ready to work on'}."
            except Exception as e: return f"FAILED: Error checking dependencies: {e}"

        def db_create_note(title: str, content: str, workspace_id: int = None,
                           space_id: int = None, linked_task_id: int = None) -> str:
            """Create a note containing research, summaries, or text blocks."""
            try:
                note = db.create_note(user_id=user_id, title=title, content=content, workspace_id=workspace_id, space_id=space_id, linked_task_id=linked_task_id)
                return json.dumps({"status": "created", "note_id": note['id'], "title": note['title']})
            except Exception as e: return f"FAILED: Error creating note: {e}"

        def db_update_note(note_id: int, title: str = None, content: str = None,
                           workspace_id: int = None, space_id: int = None, category: str = None) -> str:
            """Update the contents or category of an existing note."""
            try:
                updates = {k: v for k, v in [('title', title), ('content', content), ('workspace_id', workspace_id), ('space_id', space_id), ('category', category)] if v is not None}
                note = db.update_note(user_id=user_id, note_id=note_id, updates=updates)
                return f"Note updated: {note['title']}" if note else f"FAILED: Note ID {note_id} not found."
            except Exception as e: return f"FAILED: Error updating note: {e}"

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
            tool_web_search, tool_search_my_data, tool_check_schedule, tool_analyze_productivity,
            db_create_project_plan, db_create_workspace, db_create_space, db_update_workspace_color, db_delete_item,
            db_create_task, db_create_subtask, db_get_subtasks, db_complete_all_subtasks,
            db_complete_task, db_update_task, db_link_note_to_task, db_check_task_blocked,
            db_create_note, db_update_note,
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
        try:
            cutoff = (datetime.now() - timedelta(minutes=30)).isoformat()
            tasks = [t for t in self.db.get_tasks(user_id=user_id, include_subtasks=True) if t.get('created_at', '') > cutoff]
            workspaces = [w for w in self.db.get_workspaces(user_id=user_id) if w.get('created_at', '') > cutoff]
            spaces = [s for s in self.db.get_spaces(user_id=user_id) if s.get('created_at', '') > cutoff]
            
            if not any([tasks, workspaces, spaces]): return ""
                
            lines = ["\n=== ITEMS CREATED IN THIS SESSION (last 30 min) ==="]
            for w in workspaces: lines.append(f"- Workspace '{w['name']}' id:{w['id']}")
            for s in spaces: lines.append(f"- Space '{s['name']}' id:{s['id']} workspace_id:{s['workspace_id']}")
            for t in tasks:
                kind = "Subtask" if t.get('parent_id') else "Task"
                lines.append(f"- {kind} '{t['title']}' id:{t['id']} workspace_id:{t.get('workspace_id') or 'none'} space_id:{t.get('space_id') or 'none'}")
            
            lines.append("\n[CRITICAL DIRECTIVE: The IDs above are for REFERENCE. Do NOT assign new tasks to these workspaces or spaces by default. HOWEVER, if you are explicitly asked to fix a project, add to a recent project, or update a tool call that just failed, you MUST use the appropriate workspace_id and space_id from above.]")
            return "\n".join(lines)
        except Exception:
            return ""

    def _detect_urgency_hint(self, message: str) -> str:
        urgent_words = ['urgent', 'asap', 'emergency', 'immediately', 'right now', 'critical', 'important', 'crucial', 'today', 'now', 'عاجل', 'مهم', 'ضروري', 'فوري', 'الآن', 'اليوم']
        if any(w in message.lower() for w in urgent_words):
            return "\n[AGENT HINT: urgency detected — use priority='high' for any tasks created from this request]"
        return ""

    def _build_agent(self, selected_tools, user_id, user_message):
        memory_context = self._get_semantic_memory(user_id, user_message)

        instruction = (
            "You are iGenda — an elite, proactive AI productivity agent. "
            "The user is Yahya, a Computer Science student at Mansoura University (Class of 2026).\n\n"
            f"=== RELEVANT USER MEMORY ===\n{memory_context}\n\n"
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
            return {
                "response_message": final_text, "tool_events": tool_events, "tasks": self.db.get_tasks(user_id=user_id), "notes": self.db.get_notes(user_id=user_id),
                "workspaces": self.db.get_workspaces(user_id=user_id), "spaces": self.db.get_spaces(user_id=user_id), "processing_time": round(time.time() - start_time, 2),
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
            try:
                tasks = db.get_tasks(user_id=user_id)
                matches = []
                for t in tasks:
                    if search_term.lower() in t['title'].lower() or search_term.lower() in t.get('description', '').lower():
                        matches.append(f"ID: {t['id']} | Title: {t['title']}")
                if not matches: return "FAILED: No matching tasks found. Create it as a new main task instead."
                return "MATCHES: " + " ; ".join(matches[:3])
            except Exception as e: return f"FAILED: Error searching for task: {e}"

        def db_create_task(title: str, description: str = "", due_date: str = "", due_time: str = "", priority: str = "medium") -> str:
            try:
                task = db.create_task(user_id=user_id, title=title, description=description, due_date=due_date, due_time=due_time, priority=priority)
                return json.dumps({"status": "created", "task_id": task['id'], "title": task['title']})
            except Exception as e: return f"FAILED: Error creating task: {e}"

        def db_create_subtask(title: str, parent_task_id: int, description: str = "", priority: str = "medium") -> str:
            """Break a task into a subtask. MUST call db_find_task_id FIRST to get the parent_task_id."""
            try:
                parent = db.get_task_with_subtasks(user_id=user_id, task_id=parent_task_id)
                if not parent: return f"FAILED: Parent ID {parent_task_id} not found."
                task = db.create_task(user_id=user_id, title=title, description=description, priority=priority, workspace_id=parent.get('workspace_id'), space_id=parent.get('space_id'), parent_id=parent_task_id)
                return json.dumps({"status": "created", "subtask_id": task['id'], "title": task['title']})
            except Exception as e: return f"FAILED: Error creating subtask: {e}"

        def db_complete_task(task_id: int) -> str:
            try:
                task = db.complete_task(user_id=user_id, task_id=task_id)
                return f"Task '{task['title']}' completed!" if task else f"FAILED: Task ID {task_id} not found."
            except Exception as e: return f"FAILED: Error completing task: {e}"

        def db_update_task(task_id: int, title: str = None, due_date: str = None) -> str:
            try:
                updates = {k: v for k, v in [('title', title), ('due_date', due_date)] if v is not None}
                task = db.update_task(user_id=user_id, task_id=task_id, updates=updates)
                return "Task updated." if task else "FAILED: Task ID not found."
            except Exception as e: return f"FAILED: Error updating task: {e}"

        def db_delete_item(item_type: str, item_id: int) -> str:
            try:
                if item_type.lower() == 'task': success = db.delete_task(user_id=user_id, task_id=item_id)
                elif item_type.lower() == 'note': success = db.delete_note(user_id=user_id, note_id=item_id)
                else: return "FAILED: Invalid type. Must be task or note."
                return "Deleted." if success else "FAILED: Item ID not found."
            except Exception as e: return f"FAILED: Error deleting item: {e}"

        def db_create_note(title: str, content: str) -> str:
            try:
                note = db.create_note(user_id=user_id, title=title, content=content)
                return f"Note created: {note['id']}"
            except Exception as e: return f"FAILED: Error creating note: {e}"

        return [db_find_task_id, db_create_task, db_create_subtask, db_complete_task, db_update_task, db_delete_item, db_create_note]

    def _build_agent(self, tools):
        instruction = (
            "You are iGenda's Fast Action Agent. Your ONLY job is to execute quick commands.\n"
            "1. NO CHAT: Just execute the tool and confirm.\n"
            "2. SUBTASKS: If asked to add a subtask to an existing task, you MUST call `db_find_task_id(search_term)` FIRST to find the parent_task_id.\n"
            "3. EXECUTION: Once you have the parent_task_id, call `db_create_subtask`.\n"
            "4. BILINGUAL: Reply in the same language as the user."
        )
        self.agent = Agent(name="iGenda_Action_Agent", model="gemini-2.5-flash", instruction=instruction, tools=tools)
        self.runner = Runner(agent=self.agent, app_name="iGenda_App", session_service=self.session_service)

    def process_message(self, user_id: str, user_message: str, language: str = 'en') -> dict:
        start_time = time.time()
        tool_events = []
        session_id = f"{user_id}_action_session"
        
        try: _run_async(self.session_service.get_session(app_name="iGenda_App", user_id=user_id, session_id=session_id))
        except Exception: _run_async(self.session_service.create_session(app_name="iGenda_App", user_id=user_id, session_id=session_id))
        
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

        return {
            "response_message": final_text, "tool_events": tool_events, "tasks": self.db.get_tasks(user_id=user_id), "notes": self.db.get_notes(user_id=user_id),
            "workspaces": self.db.get_workspaces(user_id=user_id), "spaces": self.db.get_spaces(user_id=user_id), "processing_time": round(time.time() - start_time, 2),
            "ai_metadata": {"model_used": "gemini-adk-action", "retries": attempt - 1}
        }

# ======================================================================================
# MASTER HANDLER & INTENT ROUTER
# ======================================================================================
class EnhancedAIHandler:
    def __init__(self):
        self.enhanced_rag = EnhancedRAGHandler()
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
            "1. ACTION: Creating, updating, deleting, or asking about a single task, note, or reminder. "
            "(e.g., 'add a task', 'remind me', 'مهمة', 'ذكرني', 'ملاحظة', 'احذف').\n"
            "2. COMPLEX: Planning a multi-day trip, generating a study schedule, workspaces, complex projects, or anything requiring multiple steps. "
            "(e.g., 'plan', 'trip', 'schedule', 'project', 'خطط', 'جدول', 'مشروع', 'سفر', 'إجازة').\n"
            "3. CHAT: Casual conversation, greetings, or general questions not related to database tasks. "
            "(e.g., 'hello', 'how are you', 'مرحبا', 'كيف حالك').\n\n"
            "Reply with ONLY the category word: ACTION, COMPLEX, or CHAT."
        )
        try:
            client = genai.Client()
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

    def process_multimodal_message(self, user_message, message_type='text', context_data=None, database=None, language='en', user_id='yahya', user_token=''):
        if self.use_adk and database:
            intent = self._route_intent(user_message)
            logging.info(f"Router classified intent as: {intent} for user {user_id}")
            
            if intent == "CHAT":
                try:
                    client = genai.Client()
                    sys_inst = "You are iGenda. Be warm and very brief. Reply in the user's exact language."
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

        detected_lang = 'ar' if self._is_arabic(user_message) else language
        rag_result = self.enhanced_rag.get_fallback_response(user_message, detected_lang)

        if database and 'tasks' in rag_result:
            for t in rag_result['tasks']: database.create_task(user_id=user_id, title=t.get('title'), description=t.get('description'), due_date=t.get('due_date'))
        if database and 'notes' in rag_result:
            for n in rag_result['notes']: database.create_note(user_id=user_id, title=n.get('title'), content=n.get('content'))

        rag_result.setdefault('tool_events', [])
        rag_result.setdefault('spaces', [])
        rag_result['ai_metadata'] = {"model_used": "local-rag-fallback"}
        if database:
            rag_result['workspaces'] = database.get_workspaces(user_id=user_id)
            if hasattr(database, 'get_spaces'): rag_result['spaces'] = database.get_spaces(user_id=user_id)
        return rag_result

    def _is_arabic(self, text):
        return bool(re.search(r'[\u0600-\u06FF]', text))

    def check_model_health(self):
        if self.use_adk: return {'status': 'healthy', 'model': 'gemini-adk-routed'}
        return {'status': 'healthy', 'model': 'local-rag-fallback'}
