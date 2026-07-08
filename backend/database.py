"""
iGenda Database Layer — SQLite backend

Structure:
  Workspace  (top-level container, e.g. "Graduation Project")
    └── Space  (subdivision, e.g. "AI", "Backend", "Frontend")
          ├── Task  (main task, e.g. "Study for OS exam")
          │     └── Subtask  (child task via parent_id)
          └── Note
"""
import sqlite3
import os
from datetime import datetime, timedelta
import logging

DB_FILE = 'igenda.db'


class Database:
    def __init__(self, db_file=DB_FILE):
        self.db_file = db_file
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS workspaces (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     TEXT NOT NULL,
                    name        TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    color       TEXT DEFAULT '#8A2BE2',
                    created_at  TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS spaces (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id      TEXT NOT NULL,
                    name         TEXT NOT NULL,
                    description  TEXT DEFAULT '',
                    color        TEXT DEFAULT '#8A2BE2',
                    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                    created_at   TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id        TEXT NOT NULL,
                    title          TEXT NOT NULL,
                    description    TEXT DEFAULT '',
                    due_date       TEXT,
                    due_time       TEXT,
                    duration       TEXT,
                    priority       TEXT DEFAULT 'medium',
                    category       TEXT DEFAULT 'personal',
                    language       TEXT DEFAULT 'en',
                    start_date     TEXT,
                    end_date       TEXT,
                    workspace_id   INTEGER REFERENCES workspaces(id) ON DELETE SET NULL,
                    space_id       INTEGER REFERENCES spaces(id) ON DELETE SET NULL,
                    parent_id      INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
                    completed      INTEGER DEFAULT 0,
                    completed_at   TEXT,
                    recurrence     TEXT DEFAULT NULL,
                    depends_on     INTEGER DEFAULT NULL REFERENCES tasks(id) ON DELETE SET NULL,
                    linked_note_id INTEGER DEFAULT NULL,
                    created_at     TEXT NOT NULL,
                    updated_at     TEXT
                );

                CREATE TABLE IF NOT EXISTS notes (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id        TEXT NOT NULL,
                    title          TEXT NOT NULL,
                    content        TEXT DEFAULT '',
                    category       TEXT DEFAULT 'General',
                    language       TEXT DEFAULT 'en',
                    workspace_id   INTEGER REFERENCES workspaces(id) ON DELETE SET NULL,
                    space_id       INTEGER REFERENCES spaces(id) ON DELETE SET NULL,
                    linked_task_id INTEGER DEFAULT NULL,
                    word_count     INTEGER DEFAULT 0,
                    created_at     TEXT NOT NULL,
                    updated_at     TEXT
                );

                CREATE TABLE IF NOT EXISTS user_memory (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    TEXT NOT NULL,
                    key        TEXT NOT NULL,
                    value      TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, key)
                );

                CREATE TABLE IF NOT EXISTS conversation_history (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id   TEXT NOT NULL,
                    role      TEXT NOT NULL,
                    content   TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS analytics (
                    user_id              TEXT PRIMARY KEY,
                    total_tasks_created  INTEGER DEFAULT 0,
                    total_notes_created  INTEGER DEFAULT 0,
                    last_activity        TEXT
                );
            """)
            self._migrate(conn)
        logging.info("SQLite database initialized.")

    def _migrate(self, conn):
        """Safe migrations for existing databases."""
        migrations = [
            "ALTER TABLE tasks ADD COLUMN completed_at TEXT",
            "ALTER TABLE tasks ADD COLUMN recurrence TEXT DEFAULT NULL",
            "ALTER TABLE tasks ADD COLUMN depends_on INTEGER DEFAULT NULL",
            "ALTER TABLE tasks ADD COLUMN linked_note_id INTEGER DEFAULT NULL",
            "ALTER TABLE tasks ADD COLUMN space_id INTEGER DEFAULT NULL",
            "ALTER TABLE tasks ADD COLUMN parent_id INTEGER DEFAULT NULL",
            "ALTER TABLE notes ADD COLUMN linked_task_id INTEGER DEFAULT NULL",
            "ALTER TABLE notes ADD COLUMN space_id INTEGER DEFAULT NULL",
            """CREATE TABLE IF NOT EXISTS spaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                color TEXT DEFAULT '#8A2BE2',
                workspace_id INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )""",
        ]
        for sql in migrations:
            try:
                conn.execute(sql)
            except Exception:
                pass
                
        # Inject Multi-tenant columns safely into old tables
        multi_tenant_tables = ['workspaces', 'spaces', 'tasks', 'notes', 'user_memory', 'conversation_history']
        for table in multi_tenant_tables:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN user_id TEXT DEFAULT 'yahya'")
            except Exception:
                pass

    def _row_to_dict(self, row):
        if row is None:
            return None
        d = dict(row)
        if 'completed' in d:
            d['completed'] = bool(d['completed'])
        return d

    # =====================================================================
    # CONVERSATION HISTORY
    # =====================================================================
    def save_message(self, user_id, role, content):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO conversation_history (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                (user_id, role, content, datetime.now().isoformat())
            )
            conn.execute("""
                DELETE FROM conversation_history WHERE user_id=? AND id NOT IN (
                    SELECT id FROM conversation_history WHERE user_id=? ORDER BY id DESC LIMIT 40
                )
            """, (user_id, user_id))

    def get_history(self, user_id, limit=20):
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT role, content FROM conversation_history WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit)
            ).fetchall()
            return [{'role': r['role'], 'content': r['content']} for r in reversed(rows)]

    def clear_history(self, user_id):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM conversation_history WHERE user_id=?", (user_id,))

    # =====================================================================
    # PERSISTENT AGENT MEMORY
    # =====================================================================
    def save_memory(self, user_id, key, value):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO user_memory (user_id, key, value, updated_at) VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """, (user_id, key, str(value), datetime.now().isoformat()))

    def get_memory(self, user_id, key):
        with self._get_conn() as conn:
            row = conn.execute("SELECT value FROM user_memory WHERE user_id=? AND key = ?", (user_id, key)).fetchone()
            return row['value'] if row else None

    def get_all_memory(self, user_id):
        with self._get_conn() as conn:
            rows = conn.execute("SELECT key, value FROM user_memory WHERE user_id=?", (user_id,)).fetchall()
            return {r['key']: r['value'] for r in rows}

    def delete_memory(self, user_id, key):
        with self._get_conn() as conn:
            result = conn.execute("DELETE FROM user_memory WHERE user_id=? AND key = ?", (user_id, key))
            return result.rowcount > 0

    # =====================================================================
    # SCHEDULE, SEARCH & CONTEXT
    # =====================================================================
    def check_schedule_conflict(self, user_id, check_date, check_time):
        if not check_date or not check_time:
            return "Clear"
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT title FROM tasks WHERE user_id=? AND due_date=? AND due_time=? AND completed=0 AND parent_id IS NULL",
                (user_id, check_date, check_time)
            ).fetchone()
            if row:
                return f"Conflict Found: '{row['title']}' is already scheduled at {check_date} {check_time}."
            return "Clear"

    def search_data(self, user_id, query="", item_type="all"):
        q = f"%{query.lower()}%"
        results = {"tasks": [], "notes": [], "workspaces": [], "spaces": []}
        with self._get_conn() as conn:
            if item_type in ("all", "task"):
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE user_id=? AND (lower(title) LIKE ? OR lower(description) LIKE ?)", (user_id, q, q)
                ).fetchall()
                results["tasks"] = [self._row_to_dict(r) for r in rows]
            if item_type in ("all", "note"):
                rows = conn.execute(
                    "SELECT * FROM notes WHERE user_id=? AND (lower(title) LIKE ? OR lower(content) LIKE ?)", (user_id, q, q)
                ).fetchall()
                results["notes"] = [self._row_to_dict(r) for r in rows]
            if item_type in ("all", "workspace"):
                rows = conn.execute(
                    "SELECT * FROM workspaces WHERE user_id=? AND (lower(name) LIKE ? OR lower(description) LIKE ?)", (user_id, q, q)
                ).fetchall()
                results["workspaces"] = [self._row_to_dict(r) for r in rows]
            if item_type in ("all", "space"):
                rows = conn.execute(
                    "SELECT * FROM spaces WHERE user_id=? AND (lower(name) LIKE ? OR lower(description) LIKE ?)", (user_id, q, q)
                ).fetchall()
                results["spaces"] = [self._row_to_dict(r) for r in rows]
        return results

    def get_overdue_tasks(self, user_id):
        today = datetime.now().strftime('%Y-%m-%d')
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE user_id=? AND due_date<? AND completed=0 AND parent_id IS NULL ORDER BY due_date ASC",
                (user_id, today,)
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def get_todays_tasks(self, user_id):
        today = datetime.now().strftime('%Y-%m-%d')
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE user_id=? AND due_date=? AND completed=0 AND parent_id IS NULL ORDER BY due_time ASC",
                (user_id, today,)
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def get_upcoming_tasks(self, user_id, days=3):
        today = datetime.now().strftime('%Y-%m-%d')
        future = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM tasks WHERE user_id=? AND due_date>? AND due_date<=?
                   AND completed=0 AND parent_id IS NULL ORDER BY due_date ASC, due_time ASC""",
                (user_id, today, future)
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def get_daily_briefing(self, user_id):
        now = datetime.now()
        hour = now.hour
        period = "morning" if hour < 12 else ("afternoon" if hour < 17 else "evening")
        return {
            "now": now.strftime('%Y-%m-%d %H:%M'),
            "day": now.strftime('%A, %B %d %Y'),
            "period": period,
            "overdue": self.get_overdue_tasks(user_id),
            "today": self.get_todays_tasks(user_id),
            "upcoming": self.get_upcoming_tasks(user_id, days=3),
            "memory": self.get_all_memory(user_id),
            "analytics": self.get_analytics(user_id),
        }

    # =====================================================================
    # RECURRENCE
    # =====================================================================
    RECURRENCE_MAP = {'daily':1,'weekly':7,'biweekly':14,'monthly':30,'يومي':1,'أسبوعي':7,'شهري':30}

    def spawn_next_recurrence(self, user_id, task):
        recurrence = (task.get('recurrence') or '').lower().strip()
        if not recurrence or recurrence == 'none':
            return None
        days = self.RECURRENCE_MAP.get(recurrence)
        if not days:
            return None
        base_date = task.get('due_date') or datetime.now().strftime('%Y-%m-%d')
        try:
            next_date = (datetime.strptime(base_date, '%Y-%m-%d') + timedelta(days=days)).strftime('%Y-%m-%d')
        except ValueError:
            next_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
        return self.create_task(
            user_id=user_id, title=task['title'], description=task.get('description', ''),
            due_date=next_date, due_time=task.get('due_time'),
            priority=task.get('priority', 'medium'), category=task.get('category', 'personal'),
            workspace_id=task.get('workspace_id'), space_id=task.get('space_id'),
            recurrence=recurrence,
        )

    # =====================================================================
    # WORKSPACES
    # =====================================================================
    def create_workspace(self, user_id, name, description="", color="#8A2BE2"):
        with self._get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO workspaces (user_id, name, description, color, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, str(name).strip(), str(description).strip(), color, datetime.now().isoformat())
            )
            return self._row_to_dict(conn.execute("SELECT * FROM workspaces WHERE id=?", (cur.lastrowid,)).fetchone())

    def get_workspaces(self, user_id):
        with self._get_conn() as conn:
            return [self._row_to_dict(r) for r in conn.execute(
                "SELECT * FROM workspaces WHERE user_id=? ORDER BY created_at DESC", (user_id,)
            ).fetchall()]

    def update_workspace(self, user_id, workspace_id, updates):
        allowed = {'name', 'description', 'color'}
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if not filtered:
            return None
        cols = ', '.join(f"{k}=?" for k in filtered)
        vals = list(filtered.values()) + [int(workspace_id), user_id]
        with self._get_conn() as conn:
            conn.execute(f"UPDATE workspaces SET {cols} WHERE id=? AND user_id=?", vals)
            return self._row_to_dict(conn.execute("SELECT * FROM workspaces WHERE id=?", (int(workspace_id),)).fetchone())

    def delete_workspace(self, user_id, workspace_id):
        with self._get_conn() as conn:
            return conn.execute("DELETE FROM workspaces WHERE id=? AND user_id=?", (int(workspace_id), user_id)).rowcount > 0

    def get_workspace_summary(self, user_id, workspace_id):
        with self._get_conn() as conn:
            ws = self._row_to_dict(conn.execute("SELECT * FROM workspaces WHERE id=? AND user_id=?", (int(workspace_id), user_id)).fetchone())
            if not ws:
                return None
            spaces = self.get_spaces(user_id=user_id, workspace_id=int(workspace_id))
            for space in spaces:
                space['tasks'] = self.get_tasks(user_id=user_id, space_id=space['id'])
                space['notes'] = self.get_notes(user_id=user_id, space_id=space['id'])
            ws_tasks = [self._row_to_dict(r) for r in conn.execute(
                "SELECT * FROM tasks WHERE workspace_id=? AND space_id IS NULL AND parent_id IS NULL AND user_id=? ORDER BY due_date ASC",
                (int(workspace_id), user_id)
            ).fetchall()]
            ws_notes = [self._row_to_dict(r) for r in conn.execute(
                "SELECT * FROM notes WHERE workspace_id=? AND space_id IS NULL AND user_id=? ORDER BY created_at DESC",
                (int(workspace_id), user_id)
            ).fetchall()]
            return {"workspace": ws, "spaces": spaces, "tasks": ws_tasks, "notes": ws_notes}

    # =====================================================================
    # SPACES
    # =====================================================================
    def create_space(self, user_id, name, workspace_id, description="", color="#8A2BE2"):
        with self._get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO spaces (user_id, name, description, color, workspace_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, str(name).strip(), str(description).strip(), color, int(workspace_id), datetime.now().isoformat())
            )
            return self._row_to_dict(conn.execute("SELECT * FROM spaces WHERE id=?", (cur.lastrowid,)).fetchone())

    def get_spaces(self, user_id, workspace_id=None):
        with self._get_conn() as conn:
            if workspace_id:
                rows = conn.execute(
                    "SELECT * FROM spaces WHERE workspace_id=? AND user_id=? ORDER BY created_at ASC", (int(workspace_id), user_id)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM spaces WHERE user_id=? ORDER BY workspace_id ASC, created_at ASC", (user_id,)).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def update_space(self, user_id, space_id, updates):
        allowed = {'name', 'description', 'color'}
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if not filtered:
            return None
        cols = ', '.join(f"{k}=?" for k in filtered)
        vals = list(filtered.values()) + [int(space_id), user_id]
        with self._get_conn() as conn:
            conn.execute(f"UPDATE spaces SET {cols} WHERE id=? AND user_id=?", vals)
            return self._row_to_dict(conn.execute("SELECT * FROM spaces WHERE id=?", (int(space_id),)).fetchone())

    def delete_space(self, user_id, space_id):
        with self._get_conn() as conn:
            return conn.execute("DELETE FROM spaces WHERE id=? AND user_id=?", (int(space_id), user_id)).rowcount > 0

    # =====================================================================
    # TASKS (with subtask support via parent_id)
    # =====================================================================
    def create_task(self, user_id, title, description="", due_date=None, due_time=None, duration=None,
                    priority="medium", language="en", category="personal",
                    start_date=None, end_date=None, workspace_id=None, space_id=None,
                    parent_id=None, recurrence=None, depends_on=None, linked_note_id=None):
        today = datetime.now().strftime('%Y-%m-%d')
        if not due_date or (due_date < today and not start_date):
            due_date = today
        with self._get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO tasks (user_id, title, description, due_date, due_time, duration, priority,
                    category, language, start_date, end_date, workspace_id, space_id,
                    parent_id, completed, recurrence, depends_on, linked_note_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
            """, (
                user_id,
                str(title).strip(), str(description).strip(),
                due_date, due_time, duration, priority, category, language,
                start_date, end_date,
                int(workspace_id) if workspace_id else None,
                int(space_id) if space_id else None,
                int(parent_id) if parent_id else None,
                recurrence,
                int(depends_on) if depends_on else None,
                int(linked_note_id) if linked_note_id else None,
                datetime.now().isoformat()
            ))
            
            conn.execute("""
                INSERT INTO analytics (user_id, total_tasks_created, total_notes_created, last_activity) 
                VALUES (?, 1, 0, ?) 
                ON CONFLICT(user_id) DO UPDATE SET 
                total_tasks_created=total_tasks_created+1, last_activity=excluded.last_activity
            """, (user_id, datetime.now().isoformat()))
            
            return self._row_to_dict(conn.execute("SELECT * FROM tasks WHERE id=?", (cur.lastrowid,)).fetchone())

    def get_tasks(self, user_id, space_id=None, workspace_id=None, parent_id=None, include_subtasks=False):
        with self._get_conn() as conn:
            conditions = ["user_id=?"]
            params = [user_id]
            if not include_subtasks and parent_id is None:
                conditions.append("parent_id IS NULL")
            if space_id is not None:
                conditions.append("space_id=?")
                params.append(int(space_id))
            if workspace_id is not None:
                conditions.append("workspace_id=?")
                params.append(int(workspace_id))
            if parent_id is not None:
                conditions = [c for c in conditions if c != "parent_id IS NULL"]
                conditions.append("parent_id=?")
                params.append(int(parent_id))
            where = f"WHERE {' AND '.join(conditions)}"
            rows = conn.execute(
                f"SELECT * FROM tasks {where} ORDER BY completed ASC, due_date ASC, due_time ASC",
                params
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def get_subtasks(self, user_id, parent_id):
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE parent_id=? AND user_id=? ORDER BY completed ASC, created_at ASC",
                (int(parent_id), user_id)
            ).fetchall()
            subtasks = [self._row_to_dict(r) for r in rows]
        total = len(subtasks)
        done = sum(1 for s in subtasks if s.get('completed'))
        return {
            "subtasks": subtasks,
            "total": total,
            "completed": done,
            "progress_pct": round(done / total * 100) if total > 0 else 0
        }

    def get_task_with_subtasks(self, user_id, task_id):
        with self._get_conn() as conn:
            task = self._row_to_dict(conn.execute("SELECT * FROM tasks WHERE id=? AND user_id=?", (int(task_id), user_id)).fetchone())
        if not task:
            return None
        sub = self.get_subtasks(user_id=user_id, parent_id=task_id)
        task['subtasks'] = sub['subtasks']
        task['subtask_progress'] = {'total': sub['total'], 'completed': sub['completed'], 'pct': sub['progress_pct']}
        return task

    def complete_task(self, user_id, task_id):
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE tasks SET completed=1, completed_at=?, updated_at=? WHERE id=? AND user_id=?",
                (now, now, int(task_id), user_id)
            )
            task = self._row_to_dict(conn.execute("SELECT * FROM tasks WHERE id=?", (int(task_id),)).fetchone())
        if task and task.get('recurrence') and not task.get('parent_id'):
            self.spawn_next_recurrence(user_id=user_id, task=task)
        return task

    def uncomplete_task(self, user_id, task_id):
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE tasks SET completed=0, completed_at=NULL, updated_at=? WHERE id=? AND user_id=?",
                (now, int(task_id), user_id)
            )
            return self._row_to_dict(conn.execute("SELECT * FROM tasks WHERE id=?", (int(task_id),)).fetchone())

    def update_task(self, user_id, task_id, updates):
        allowed = {'title','description','due_date','due_time','priority','completed',
                   'duration','workspace_id','space_id','recurrence','depends_on',
                   'linked_note_id','parent_id'}
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if not filtered:
            return None
        filtered['updated_at'] = datetime.now().isoformat()
        cols = ', '.join(f"{k}=?" for k in filtered)
        vals = list(filtered.values()) + [int(task_id), user_id]
        with self._get_conn() as conn:
            conn.execute(f"UPDATE tasks SET {cols} WHERE id=? AND user_id=?", vals)
            return self._row_to_dict(conn.execute("SELECT * FROM tasks WHERE id=?", (int(task_id),)).fetchone())

    def delete_task(self, user_id, task_id):
        with self._get_conn() as conn:
            return conn.execute("DELETE FROM tasks WHERE id=? AND user_id=?", (int(task_id), user_id)).rowcount > 0

    def is_task_blocked(self, user_id, task_id):
        with self._get_conn() as conn:
            row = conn.execute("SELECT depends_on FROM tasks WHERE id=? AND user_id=?", (int(task_id), user_id)).fetchone()
            if not row or not row['depends_on']:
                return False
            dep = conn.execute("SELECT completed FROM tasks WHERE id=? AND user_id=?", (row['depends_on'], user_id)).fetchone()
            return dep is not None and not bool(dep['completed'])

    # =====================================================================
    # NOTES
    # =====================================================================
    def create_note(self, user_id, title, content, category="General", language="en",
                    workspace_id=None, space_id=None, linked_task_id=None):
        word_count = len(str(content).split())
        with self._get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO notes (user_id, title, content, category, language, workspace_id,
                    space_id, linked_task_id, word_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                str(title).strip(), str(content), category, language,
                int(workspace_id) if workspace_id else None,
                int(space_id) if space_id else None,
                int(linked_task_id) if linked_task_id else None,
                word_count, datetime.now().isoformat()
            ))
            
            conn.execute("""
                INSERT INTO analytics (user_id, total_tasks_created, total_notes_created, last_activity) 
                VALUES (?, 0, 1, ?) 
                ON CONFLICT(user_id) DO UPDATE SET 
                total_notes_created=total_notes_created+1, last_activity=excluded.last_activity
            """, (user_id, datetime.now().isoformat()))
            
            return self._row_to_dict(conn.execute("SELECT * FROM notes WHERE id=?", (cur.lastrowid,)).fetchone())

    def get_notes(self, user_id, space_id=None, workspace_id=None):
        with self._get_conn() as conn:
            conditions = ["user_id=?"]
            params = [user_id]
            if space_id is not None:
                conditions.append("space_id=?")
                params.append(int(space_id))
            if workspace_id is not None:
                conditions.append("workspace_id=?")
                params.append(int(workspace_id))
            where = f"WHERE {' AND '.join(conditions)}"
            rows = conn.execute(f"SELECT * FROM notes {where} ORDER BY created_at DESC", params).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def update_note(self, user_id, note_id, updates):
        allowed = {'title','content','category','workspace_id','space_id','linked_task_id'}
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if not filtered:
            return None
        if 'content' in filtered:
            filtered['word_count'] = len(str(filtered['content']).split())
        filtered['updated_at'] = datetime.now().isoformat()
        cols = ', '.join(f"{k}=?" for k in filtered)
        vals = list(filtered.values()) + [int(note_id), user_id]
        with self._get_conn() as conn:
            conn.execute(f"UPDATE notes SET {cols} WHERE id=? AND user_id=?", vals)
            return self._row_to_dict(conn.execute("SELECT * FROM notes WHERE id=?", (int(note_id),)).fetchone())

    def delete_note(self, user_id, note_id):
        with self._get_conn() as conn:
            return conn.execute("DELETE FROM notes WHERE id=? AND user_id=?", (int(note_id), user_id)).rowcount > 0

    # =====================================================================
    # UTILITY
    # =====================================================================
    def clear_all(self, user_id):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM tasks WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM notes WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM spaces WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM workspaces WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM user_memory WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM conversation_history WHERE user_id=?", (user_id,))
            conn.execute(
                "UPDATE analytics SET total_tasks_created=0, total_notes_created=0, last_activity=NULL WHERE user_id=?",
                (user_id,)
            )

    def get_analytics(self, user_id):
        tasks = self.get_tasks(user_id=user_id, include_subtasks=False)
        notes = self.get_notes(user_id=user_id)
        with self._get_conn() as conn:
            row_raw = conn.execute("SELECT * FROM analytics WHERE user_id=?", (user_id,)).fetchone()
            row = self._row_to_dict(row_raw) if row_raw else {}
            space_count = conn.execute("SELECT COUNT(*) FROM spaces WHERE user_id=?", (user_id,)).fetchone()[0]
        return {
            'total_tasks': len(tasks),
            'total_notes': len(notes),
            'total_workspaces': len(self.get_workspaces(user_id=user_id)),
            'total_spaces': space_count,
            'completed_tasks': len([t for t in tasks if t.get('completed')]),
            'total_tasks_created': row.get('total_tasks_created', 0),
            'total_notes_created': row.get('total_notes_created', 0),
            'overdue_tasks': len(self.get_overdue_tasks(user_id=user_id)),
        }

    def get_smart_analytics(self, user_id):
        """Deep behavioral analytics from SQLite timestamps, fully scoped to user_id."""
        with self._get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM tasks WHERE parent_id IS NULL AND user_id=?", (user_id,)).fetchone()[0]
            completed = conn.execute("SELECT COUNT(*) FROM tasks WHERE completed=1 AND parent_id IS NULL AND user_id=?", (user_id,)).fetchone()[0]
            overdue = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE completed=0 AND due_date<date('now') AND parent_id IS NULL AND user_id=?", (user_id,)
            ).fetchone()[0]
            completion_rate = round((completed / total * 100), 1) if total > 0 else 0

            sub_total = conn.execute("SELECT COUNT(*) FROM tasks WHERE parent_id IS NOT NULL AND user_id=?", (user_id,)).fetchone()[0]
            sub_done = conn.execute("SELECT COUNT(*) FROM tasks WHERE parent_id IS NOT NULL AND completed=1 AND user_id=?", (user_id,)).fetchone()[0]

            priority_stats = {}
            for pri in ['high', 'medium', 'low']:
                t = conn.execute("SELECT COUNT(*) FROM tasks WHERE priority=? AND parent_id IS NULL AND user_id=?", (pri, user_id)).fetchone()[0]
                c = conn.execute("SELECT COUNT(*) FROM tasks WHERE priority=? AND completed=1 AND parent_id IS NULL AND user_id=?", (pri, user_id)).fetchone()[0]
                priority_stats[pri] = {'total': t, 'completed': c, 'rate': round(c/t*100,1) if t > 0 else 0}

            cat_rows = conn.execute("""
                SELECT category, COUNT(*) as total, SUM(completed) as done
                FROM tasks WHERE parent_id IS NULL AND user_id=? GROUP BY category ORDER BY total DESC
            """, (user_id,)).fetchall()
            category_stats = [
                {'category': r['category'] or 'personal', 'total': r['total'],
                 'completed': r['done'] or 0,
                 'rate': round((r['done'] or 0)/r['total']*100,1) if r['total'] > 0 else 0}
                for r in cat_rows
            ]

            hour_rows = conn.execute("""
                SELECT CAST(strftime('%H', created_at) AS INTEGER) as hour, COUNT(*) as count
                FROM tasks WHERE created_at IS NOT NULL AND user_id=? GROUP BY hour ORDER BY count DESC
            """, (user_id,)).fetchall()
            hourly_activity = [{'hour': r['hour'], 'count': r['count']} for r in hour_rows]
            if hour_rows:
                ph = hour_rows[0]['hour']
                period = 'AM' if ph < 12 else 'PM'
                dh = ph if ph <= 12 else ph - 12
                dh = 12 if dh == 0 else dh
                peak_hour_label = f"{dh}:00 {period}"
            else:
                peak_hour_label = "Not enough data"

            day_map = {0:'Sunday',1:'Monday',2:'Tuesday',3:'Wednesday',4:'Thursday',5:'Friday',6:'Saturday'}
            day_rows = conn.execute("""
                SELECT CAST(strftime('%w', due_date) AS INTEGER) as dow, COUNT(*) as count
                FROM tasks WHERE due_date IS NOT NULL AND parent_id IS NULL AND user_id=? GROUP BY dow ORDER BY count DESC
            """, (user_id,)).fetchall()
            daily_activity = [{'day': day_map.get(r['dow'], str(r['dow'])), 'count': r['count']} for r in day_rows]
            busiest_day = day_map.get(day_rows[0]['dow']) if day_rows else "Not enough data"

            week_rows = conn.execute("""
                SELECT date(due_date) as day, COUNT(*) as total, SUM(completed) as done
                FROM tasks WHERE due_date>=date('now','-7 days') AND due_date<=date('now') AND parent_id IS NULL AND user_id=?
                GROUP BY day ORDER BY day ASC
            """, (user_id,)).fetchall()
            weekly_trend = [{'day': r['day'], 'created': r['total'], 'completed': r['done'] or 0} for r in week_rows]

            avg_row = conn.execute("""
                SELECT AVG((julianday(completed_at)-julianday(created_at))*24) as avg_hours
                FROM tasks WHERE completed=1 AND completed_at IS NOT NULL AND created_at IS NOT NULL AND parent_id IS NULL AND user_id=?
            """, (user_id,)).fetchone()
            avg_completion_hours = round(avg_row['avg_hours'], 1) if avg_row and avg_row['avg_hours'] else None

            ws_rows = conn.execute("""
                SELECT w.name, COUNT(t.id) as total, SUM(t.completed) as done
                FROM workspaces w LEFT JOIN tasks t ON t.workspace_id=w.id AND t.parent_id IS NULL
                WHERE w.user_id=? GROUP BY w.id ORDER BY done DESC
            """, (user_id,)).fetchall()
            workspace_stats = [{'name':r['name'],'total':r['total'] or 0,'completed':r['done'] or 0,
                                 'rate':round((r['done'] or 0)/(r['total'] or 1)*100,1)} for r in ws_rows]

            space_rows = conn.execute("""
                SELECT s.name, COUNT(t.id) as total, SUM(t.completed) as done
                FROM spaces s LEFT JOIN tasks t ON t.space_id=s.id AND t.parent_id IS NULL
                WHERE s.user_id=? GROUP BY s.id ORDER BY done DESC
            """, (user_id,)).fetchall()
            space_stats = [{'name':r['name'],'total':r['total'] or 0,'completed':r['done'] or 0,
                             'rate':round((r['done'] or 0)/(r['total'] or 1)*100,1)} for r in space_rows]

            proc_rows = conn.execute("""
                SELECT category, COUNT(*) as c FROM tasks
                WHERE completed=0 AND due_date<date('now') AND parent_id IS NULL AND user_id=?
                GROUP BY category ORDER BY c DESC
            """, (user_id,)).fetchall()
            procrastination = [{'category': r['category'] or 'personal', 'overdue': r['c']} for r in proc_rows]

            total_notes = conn.execute("SELECT COUNT(*) FROM notes WHERE user_id=?", (user_id,)).fetchone()[0]
            avg_words = conn.execute("SELECT AVG(word_count) FROM notes WHERE user_id=?", (user_id,)).fetchone()[0]
            top_cat = conn.execute(
                "SELECT category, COUNT(*) as c FROM notes WHERE user_id=? GROUP BY category ORDER BY c DESC LIMIT 1", (user_id,)
            ).fetchone()

            streak = 0
            streak_rows = conn.execute("""
                SELECT DISTINCT date(completed_at) as day FROM tasks
                WHERE completed=1 AND completed_at IS NOT NULL AND user_id=? ORDER BY day DESC
            """, (user_id,)).fetchall()
            if streak_rows:
                today_date = datetime.now().date()
                for i, sr in enumerate(streak_rows):
                    if sr['day'] == (today_date - timedelta(days=i)).isoformat():
                        streak += 1
                    else:
                        break

        return {
            'total_tasks': total, 'completed_tasks': completed, 'overdue_tasks': overdue,
            'completion_rate': completion_rate, 'current_streak_days': streak,
            'subtask_total': sub_total, 'subtask_completed': sub_done,
            'subtask_completion_rate': round(sub_done/sub_total*100,1) if sub_total > 0 else 0,
            'peak_creation_hour': peak_hour_label, 'hourly_activity': hourly_activity,
            'busiest_day_of_week': busiest_day, 'daily_activity': daily_activity,
            'weekly_trend': weekly_trend, 'avg_completion_time_hours': avg_completion_hours,
            'priority_breakdown': priority_stats, 'category_breakdown': category_stats,
            'procrastination_by_category': procrastination,
            'workspace_productivity': workspace_stats, 'space_productivity': space_stats,
            'total_notes': total_notes,
            'avg_note_words': round(avg_words, 0) if avg_words else 0,
            'top_note_category': top_cat['category'] if top_cat else 'General',
        }