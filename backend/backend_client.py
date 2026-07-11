import os
import logging
import requests

BACKEND_URL = os.getenv("BACKEND_URL")
TIMEOUT = 10


class BackendError(Exception):
    """Raised when the .NET gateway is unreachable or returns a failure envelope."""
    pass


def _headers(user_id: str, user_token: str = "") -> dict:
    if not user_id:
        raise BackendError("Cannot call the backend gateway without a verified user_id.")

    logging.info(f"_headers token present: {bool(user_token)}")
    if user_token:
        logging.info(f"_headers token prefix: {user_token[:20]}")

    headers = {
        "X-User-Id": user_id,
        "Content-Type": "application/json",
    }

    if user_token:
        headers["Authorization"] = f"Bearer {user_token}"

    return headers
    


def _unwrap(response) -> dict:
    """Parses a .NET response body. Two envelope shapes are in play:
      1. {success, data, error} — used by most action/mutation endpoints.
      2. {items, pageNumber, pageSize, totalPages, hasPrevious, hasNext} —
         used by (at least) list/pagination endpoints like GET /api/WorkSpaces,
         which return the paginated list directly with no success/data wrapper.
    Casing of keys is unconfirmed (see _field docstring), so use the same
    tolerant lookup rather than hardcoding either shape.
    """
    try:
        payload = response.json()
    except Exception:
        raise BackendError(f"Non-JSON response ({response.status_code}): {response.text[:200]}")

    success = _field(payload, "success", default=None)

    if success is None:
        # No success/data envelope at all — check for the paginated-list shape
        # before giving up. "items" being present (even as an empty list) is
        # the signal, since pageNumber/pageSize alone could theoretically be 0.
        items = _field(payload, "items", default=None)
        if items is not None:
            return items
        logging.error(f"Unrecognized response envelope shape: {list(payload.keys())[:10]}")

    if not success:
        error = _field(payload, "error", default={}) or {}
        message = _field(error, "message", default=None) if isinstance(error, dict) else None
        raise BackendError(message or f"Request failed ({response.status_code}): {str(payload)[:200]}")
    return _field(payload, "data")


def _field(obj: dict, *names, default=None):
    """
    UNCONFIRMED CASING GUESS — see file docstring. Tries each candidate name
    as given, then Capitalized, then lower, before giving up.
    """
    if not isinstance(obj, dict):
        return default
    for name in names:
        for variant in (name, name[:1].upper() + name[1:], name.lower(), name.upper()):
            if variant in obj:
                return obj[variant]
    return default


def priority_to_int(priority: str) -> int:
    """
    CONFIRMED (backend spec, this pass): 0=Low, 1=Medium, 2=High, 3=Critical.
    NOTE: this replaces the old high=1/medium=2/low=3 guess — flagged to the
    team as a breaking change since it affects every existing task-creation
    call site. Do not revert without re-confirming which mapping is live.
    """
    return {"low": 0, "medium": 1, "high": 2, "critical": 3}.get((priority or "medium").lower(), 1)


def create_quick_task(user_id: str, title: str, description: str = "", due_date: str = "",
                       due_time: str = "", priority: str = "medium", user_token: str = "") -> dict:
    """
    POST /api/ai/tasks/quick
    CONFIRMED (backend spec, this pass): body is snake_case, NOT camelCase —
    overturns the earlier "dueDate/dueTime camelCase DTO" note. due_date is
    full ISO datetime with Z (e.g. "2026-07-12T00:00:00Z"), due_time is a
    12-hour string with AM/PM (e.g. "09:00 AM"). Recurrence is explicitly
    unsupported — do not send it.
    """
    if not BACKEND_URL:
        raise BackendError("BACKEND_URL is not configured.")
    resp = requests.post(
        f"{BACKEND_URL}/api/ai/tasks/quick",
        json={
            "title": title,
            "description": description or None,
            "due_date": due_date or None,
            "due_time": due_time or None,
            "priority": priority_to_int(priority),
        },
        headers=_headers(user_id, user_token=user_token),
        timeout=TIMEOUT,
    )
    return _unwrap(resp)


def create_workspace(user_id: str, name: str, description: str = "", color: str = "", user_token: str = "") -> dict:
    """POST /api/ai/workspaces — confirmed standalone workspace create."""
    if not BACKEND_URL:
        raise BackendError("BACKEND_URL is not configured.")
    resp = requests.post(
        f"{BACKEND_URL}/api/ai/workspaces",
        json={"name": name, "description": description, "color": color},
        headers=_headers(user_id, user_token=user_token),
        timeout=TIMEOUT,
    )
    return _unwrap(resp)


def create_space(user_id: str, workspace_id, name: str, description: str = "",
                  icon_code: str = "", is_public: bool = True, user_token: str = "") -> dict:
    """POST /api/ai/workspaces/{workspaceId}/spaces — confirmed standalone space create."""
    if not BACKEND_URL:
        raise BackendError("BACKEND_URL is not configured.")
    resp = requests.post(
        f"{BACKEND_URL}/api/ai/workspaces/{workspace_id}/spaces",
        json={"name": name, "description": description, "iconCode": icon_code, "isPublic": is_public},
        headers=_headers(user_id, user_token=user_token),
        timeout=TIMEOUT,
    )
    return _unwrap(resp)


def create_subtask(user_id: str, workspace_id, space_id, task_id, title: str, user_token: str = "") -> dict:
    """POST /api/ai/workspaces/{wId}/spaces/{sId}/tasks/{tId}/subtasks — confirmed, scoped path."""
    if not BACKEND_URL:
        raise BackendError("BACKEND_URL is not configured.")
    resp = requests.post(
        f"{BACKEND_URL}/api/ai/workspaces/{workspace_id}/spaces/{space_id}/tasks/{task_id}/subtasks",
        json={"title": title},
        headers=_headers(user_id, user_token=user_token),
        timeout=TIMEOUT,
    )
    return _unwrap(resp)


def link_note_to_task(user_id: str, task_id, note_id, user_token: str = "") -> dict:
    """
    POST /api/ai/tasks/{taskId}/links/notes/{noteId} — no body.
    CONFIRMED: this is the ONLY note-related AI capability. There is no
    create-note, update-note, or delete-note route in the AI controller —
    notes are owned entirely by the frontend/general backend. Do not add
    those functions back without a new confirmed spec.
    """
    if not BACKEND_URL:
        raise BackendError("BACKEND_URL is not configured.")
    resp = requests.post(
        f"{BACKEND_URL}/api/ai/tasks/{task_id}/links/notes/{note_id}",
        headers=_headers(user_id, user_token=user_token), timeout=TIMEOUT,
    )
    return _unwrap(resp)


def persist_tree(user_id: str, tree: dict, user_token: str = "") -> dict:
    """
    POST /api/ai/tree — confirmed to exist, schema:
    {
      "workspace": {
        "name": str, "description": str,
        "spaces": [{
          "name": str, "description": str, "iconCode": str,
          "tasks": [{
            "title": str, "description": str, "dueDate": str,  # ISO datetime
            "subtasks": [{"title": str, "isCompleted": bool}]
          }]
        }]
      }
    }
    UNRESOLVED: this looks like it does the same job as persist_project_plan()
    below (atomic workspace+spaces+tasks+subtasks creation) but with a
    different shape and path. Confirm with the backend team whether this
    replaces persist_project_plan or the two coexist for different cases
    before wiring the agent's tree-generation tool to one or the other.
    """
    if not BACKEND_URL:
        raise BackendError("BACKEND_URL is not configured.")
    resp = requests.post(
        f"{BACKEND_URL}/api/ai/tree", json=tree, headers=_headers(user_id, user_token=user_token), timeout=TIMEOUT,
    )
    return _unwrap(resp)


def persist_project_plan(user_id: str, plan: dict, user_token: str = "") -> dict:
    """
    POST /api/ai/projects/persist

    CHANGE NOTE (Technical Amendment AI2.1, resolving the data-loss gap flagged
    earlier): schema expanded to carry workspace_description, workspace_color,
    and per-task description/due_date/due_time. Nothing is dropped anymore —
    `plan` must match the full shape:
    {
      "workspace_name": str,
      "workspace_description": str | None,
      "workspace_color": str,          # hex, e.g. "#8A2BE2"
      "spaces": [
        {
          "space_name": str,
          "tasks": [
            {
              "title": str, "description": str | None,
              "due_date": str | None,  # YYYY-MM-DD
              "due_time": str | None,  # HH:MM
              "priority": int,
              "subtasks": [{"title": str}]
            }
          ]
        }
      ]
    }
    Construction of this payload from the internal ProjectPlan pydantic model
    happens in ai_handler.py's db_create_project_plan.
    """
    if not BACKEND_URL:
        raise BackendError("BACKEND_URL is not configured.")
    resp = requests.post(
        f"{BACKEND_URL}/api/ai/projects/persist",
        json=plan,
        headers=_headers(user_id, user_token=user_token),
        timeout=TIMEOUT,
    )
    return _unwrap(resp)


# =====================================================================
# WORKSPACES / SPACES  (doc section 4.4)
# =====================================================================

def get_workspaces(user_id: str, user_token: str = ""):
    resp = requests.get(
        f"{BACKEND_URL}/api/WorkSpaces",
        headers=_headers(user_id, user_token=user_token),
        timeout=TIMEOUT,
    )
    return _unwrap(resp) or []


def update_workspace(user_id: str, workspace_id, updates: dict, user_token: str = "") -> dict:
    """PUT /api/WorkSpaces/{Id} — body fields per doc: Name, Description, Icon."""
    resp = requests.put(
        f"{BACKEND_URL}/api/WorkSpaces/{workspace_id}",
        json=updates, headers=_headers(user_id, user_token=user_token), timeout=TIMEOUT,
    )
    return _unwrap(resp)


def delete_workspace(user_id: str, workspace_id, user_token: str = "") -> dict:
    """DELETE /api/WorkSpaces/{Id} (soft delete per doc)."""
    resp = requests.delete(f"{BACKEND_URL}/api/WorkSpaces/{workspace_id}", headers=_headers(user_id, user_token=user_token), timeout=TIMEOUT)
    return _unwrap(resp)


def get_spaces(user_id: str, workspace_id, user_token: str = ""):
    resp = requests.get(
        f"{BACKEND_URL}/api/WorkSpaces/{workspace_id}/Spaces",
        headers=_headers(user_id, user_token=user_token),
        timeout=TIMEOUT,
    )
    return _unwrap(resp) or []


# =====================================================================
# TASKS  (doc section 2 + 4.4)
# =====================================================================

def get_tasks(user_id: str, workspace_id, space_id, user_token: str = "") -> list:
    """GET /api/WorkSpaces/{WorkspaceId}/Spaces/{SpaceId}/Tasks"""
    resp = requests.get(
        f"{BACKEND_URL}/api/WorkSpaces/{workspace_id}/Spaces/{space_id}/Tasks",
        headers=_headers(user_id, user_token=user_token), timeout=TIMEOUT,
    )
    return _unwrap(resp) or []


def get_task(user_id: str, workspace_id, space_id, task_id, user_token: str = "") -> dict:
    """GET /api/WorkSpaces/{WorkspaceId}/Spaces/{SpaceId}/Tasks/{Id}"""
    resp = requests.get(
        f"{BACKEND_URL}/api/WorkSpaces/{workspace_id}/Spaces/{space_id}/Tasks/{task_id}",
        headers=_headers(user_id, user_token=user_token), timeout=TIMEOUT,
    )
    return _unwrap(resp)


def create_task(user_id: str, workspace_id, space_id, title: str, priority: str = "medium", user_token: str = "") -> dict:
    """POST /api/WorkSpaces/{wId}/Spaces/{sId}/Tasks (create_isolated_task)."""
    resp = requests.post(
        f"{BACKEND_URL}/api/WorkSpaces/{workspace_id}/Spaces/{space_id}/Tasks",
        json={"title": title, "priority": priority_to_int(priority)},
        headers=_headers(user_id, user_token=user_token), timeout=TIMEOUT,
    )
    return _unwrap(resp)


def set_task_status(user_id: str, workspace_id, space_id, task_id, status: str, user_token: str = "") -> dict:
    """
    PUT /api/WorkSpaces/{wId}/Spaces/{sId}/Tasks/{Id}/status (toggle_task_status)
    Doc-confirmed values: Todo, Ongoing, Completed, Cancelled.
    """
    resp = requests.put(
        f"{BACKEND_URL}/api/WorkSpaces/{workspace_id}/Spaces/{space_id}/Tasks/{task_id}/status",
        json={"status": status},
        headers=_headers(user_id, user_token=user_token), timeout=TIMEOUT,
    )
    return _unwrap(resp)


def update_task(user_id: str, workspace_id, space_id, task_id, updates: dict, user_token: str = "") -> dict:
    """
    PUT /api/WorkSpaces/{wId}/Spaces/{sId}/Tasks/{Id} (modify_task_details)
    ASSUMPTION: body accepts the same field names as create (title, priority) —
    not confirmed, doc gives no schema for this route.
    """
    resp = requests.put(
        f"{BACKEND_URL}/api/WorkSpaces/{workspace_id}/Spaces/{space_id}/Tasks/{task_id}",
        json=updates, headers=_headers(user_id, user_token=user_token), timeout=TIMEOUT,
    )
    return _unwrap(resp)


def delete_task(user_id: str, workspace_id, space_id, task_id, user_token: str = "") -> dict:
    """DELETE /api/WorkSpaces/{wId}/Spaces/{sId}/Tasks/{Id} (delete_isolated_task, soft delete)."""
    resp = requests.delete(
        f"{BACKEND_URL}/api/WorkSpaces/{workspace_id}/Spaces/{space_id}/Tasks/{task_id}",
        headers=_headers(user_id, user_token=user_token), timeout=TIMEOUT,
    )
    return _unwrap(resp)


def set_subtask_status(user_id: str, workspace_id, space_id, task_id, subtask_id, status: str, user_token: str = "") -> dict:
    """PUT /api/WorkSpaces/{wId}/Spaces/{sId}/Tasks/{tId}/SubTasks/{Id}/status (toggle_subtask_state)."""
    resp = requests.put(
        f"{BACKEND_URL}/api/WorkSpaces/{workspace_id}/Spaces/{space_id}/Tasks/{task_id}/SubTasks/{subtask_id}/status",
        json={"status": status},
        headers=_headers(user_id, user_token=user_token), timeout=TIMEOUT,
    )
    return _unwrap(resp)


# =====================================================================
# NOTES  (doc section 2 + 4.4)
# =====================================================================

def get_notes(user_id: str, workspace_id, space_id, user_token: str = "") -> list:
    """GET /api/WorkSpaces/{WorkspaceId}/Spaces/{SpaceId}/Notes"""
    resp = requests.get(
        f"{BACKEND_URL}/api/WorkSpaces/{workspace_id}/Spaces/{space_id}/Notes",
        headers=_headers(user_id, user_token=user_token), timeout=TIMEOUT,
    )
    return _unwrap(resp) or []


def create_note(user_id: str, workspace_id, space_id, title: str, content: str = "", user_token: str = "") -> dict:
    """
    POST /api/WorkSpaces/{wId}/Spaces/{sId}/Notes (persist_new_note)
    ASSUMPTION: body field names (title/content) — not given in the doc.
    """
    resp = requests.post(
        f"{BACKEND_URL}/api/WorkSpaces/{workspace_id}/Spaces/{space_id}/Notes",
        json={"title": title, "content": content},
        headers=_headers(user_id, user_token=user_token), timeout=TIMEOUT,
    )
    return _unwrap(resp)


def get_note(user_id: str, workspace_id, space_id, note_id, user_token: str = "") -> dict:
    """GET /api/WorkSpaces/{wId}/Spaces/{sId}/Notes/{Id} (fetch_note_content)."""
    resp = requests.get(
        f"{BACKEND_URL}/api/WorkSpaces/{workspace_id}/Spaces/{space_id}/Notes/{note_id}",
        headers=_headers(user_id, user_token=user_token), timeout=TIMEOUT,
    )
    return _unwrap(resp)


def delete_note(user_id: str, workspace_id, space_id, note_id, user_token: str = "") -> dict:
    """DELETE /api/WorkSpaces/{wId}/Spaces/{sId}/Notes/{Id} (soft delete)."""
    resp = requests.delete(
        f"{BACKEND_URL}/api/WorkSpaces/{workspace_id}/Spaces/{space_id}/Notes/{note_id}",
        headers=_headers(user_id, user_token=user_token), timeout=TIMEOUT,
    )
    return _unwrap(resp)


# =====================================================================
# MEMORY / ANALYTICS / BRIEFING  (doc section 4.1 + 4.4)
# =====================================================================

def get_memory(user_id: str, user_token: str = "") -> dict:
    """GET /api/ai/memory"""
    resp = requests.get(f"{BACKEND_URL}/api/ai/memory", headers=_headers(user_id, user_token=user_token), timeout=TIMEOUT)
    return _unwrap(resp) or {}


def save_memory(user_id: str, key: str, value: str, user_token: str = "") -> dict:
    """POST /api/ai/memory"""
    resp = requests.post(
        f"{BACKEND_URL}/api/ai/memory", json={"key": key, "value": value},
        headers=_headers(user_id, user_token=user_token), timeout=TIMEOUT,
    )
    return _unwrap(resp)


def delete_memory(user_id: str, key: str, user_token: str = "") -> dict:
    """DELETE /api/ai/memory/{key}"""
    resp = requests.delete(f"{BACKEND_URL}/api/ai/memory/{key}", headers=_headers(user_id, user_token=user_token), timeout=TIMEOUT)
    return _unwrap(resp)


def get_analytics(user_id: str, user_token: str = "") -> dict:
    """GET /api/ai/analytics/smart"""
    resp = requests.get(f"{BACKEND_URL}/api/ai/analytics/smart", headers=_headers(user_id, user_token=user_token), timeout=TIMEOUT)
    return _unwrap(resp) or {}


def get_briefing(user_id: str, user_token: str = "") -> dict:
    """GET /api/ai/daily-briefing"""
    resp = requests.get(f"{BACKEND_URL}/api/ai/daily-briefing", headers=_headers(user_id, user_token=user_token), timeout=TIMEOUT)
    return _unwrap(resp) or {}


def clear_all(user_id: str, user_token: str = "") -> dict:
    """
    POST /api/ai/clear
    Confirmed in integration doc v2 section 6.5 (Status: DONE) — atomic
    cascade wipe of all tasks/notes/subtasks/workspaces for the user.
    """
    if not BACKEND_URL:
        raise BackendError("BACKEND_URL is not configured.")
    resp = requests.post(f"{BACKEND_URL}/api/ai/clear", headers=_headers(user_id, user_token=user_token), timeout=TIMEOUT)
    return _unwrap(resp)


# =====================================================================
# LOCATION RESOLVERS
# No endpoint in either document looks up a task/note by ID alone — every
# mutating route needs {wId}/{sId}. These walk the documented GET endpoints
# to find them. O(workspaces x spaces) HTTP calls per lookup — genuinely
# expensive, kept only because there's no better option in the spec.
# =====================================================================

def resolve_task_location(user_id: str, task_id, user_token: str = ""):
    """Returns (workspace_id, space_id) containing task_id, via GET /api/ai/tasks/{taskId}/location. No fallback."""
    resp = requests.get(f"{BACKEND_URL}/api/ai/tasks/{task_id}/location", headers=_headers(user_id, user_token=user_token), timeout=TIMEOUT)
    data = _unwrap(resp)
    wid = _field(data, "workspaceId", default=None)
    sid = _field(data, "spaceId", default=None)
    if wid is None or sid is None:
        raise BackendError(f"Location response missing workspaceId/spaceId: {str(data)[:200]}")
    return wid, sid


def resolve_note_location(user_id: str, note_id, user_token: str = ""):
    """Returns (workspace_id, space_id) containing note_id, via GET /api/ai/notes/{noteId}/location. No fallback."""
    resp = requests.get(f"{BACKEND_URL}/api/ai/notes/{note_id}/location", headers=_headers(user_id, user_token=user_token), timeout=TIMEOUT)
    data = _unwrap(resp)
    wid = _field(data, "workspaceId", default=None)
    sid = _field(data, "spaceId", default=None)
    if wid is None or sid is None:
        raise BackendError(f"Location response missing workspaceId/spaceId: {str(data)[:200]}")
    return wid, sid