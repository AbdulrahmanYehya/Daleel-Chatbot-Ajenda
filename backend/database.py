"""
iGenda Database Layer — SQLite backend
Supports: tasks (with recurrence + dependencies), notes (with task links),
          workspaces, user_memory, conversation_history, analytics.
"""
import sqlite3
import json
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
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    color TEXT DEFAULT '#8A2BE2',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    due_date TEXT,
                    due_time TEXT,
                    duration TEXT,
                    priority TEXT DEFAULT 'medium',
                    category TEXT DEFAULT 'personal',
                    language TEXT DEFAULT 'en',
                    start_date TEXT,
                    end_date TEXT,
                    workspace_id INTEGER REFERENCES workspaces(id) ON DELETE SET NULL,
                    completed INTEGER DEFAULT 0,
                    completed_at TEXT,
                    recurrence TEXT DEFAULT NULL,
                    depends_on INTEGER DEFAULT NULL REFERENCES tasks(id) ON DELETE SET NULL,
                    linked_note_id INTEGER DEFAULT NULL REFERENCES notes(id) ON DELETE SET NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT DEFAULT '',
                    category TEXT DEFAULT 'General',
                    language TEXT DEFAULT 'en',
                    workspace_id INTEGER REFERENCES workspaces(id) ON DELETE SET NULL,
                    linked_task_id INTEGER DEFAULT NULL REFERENCES tasks(id) ON DELETE SET NULL,
                    word_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS user_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL UNIQUE,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS conversation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS analytics (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    total_tasks_created INTEGER DEFAULT 0,
                    total_notes_created INTEGER DEFAULT 0,
                    last_activity TEXT
                );

                INSERT OR IGNORE INTO analytics (id, total_tasks_created, total_notes_created, last_activity)
                VALUES (1, 0, 0, NULL);
            """)
            # Migrate existing DBs — add new columns if they don't exist yet
            self._migrate(conn)
        logging.info("SQLite database initialized.")

    def _migrate(self, conn):
        """Safe column additions for existing databases — won't fail if column already exists."""
        migrations = [
            "ALTER TABLE tasks ADD COLUMN completed_at TEXT",
            "ALTER TABLE tasks ADD COLUMN recurrence TEXT DEFAULT NULL",
            "ALTER TABLE tasks ADD COLUMN depends_on INTEGER DEFAULT NULL",
            "ALTER TABLE tasks ADD COLUMN linked_note_id INTEGER DEFAULT NULL",
            "ALTER TABLE notes ADD COLUMN linked_task_id INTEGER DEFAULT NULL",
        ]
        for sql in migrations:
            try:
                conn.execute(sql)
            except Exception:
                pass  # Column already exists

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
    def save_message(self, role: str, content: str):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO conversation_history (role, content, timestamp) VALUES (?, ?, ?)",
                (role, content, datetime.now().isoformat())
            )
            conn.execute("""
                DELETE FROM conversation_history WHERE id NOT IN (
                    SELECT id FROM conversation_history ORDER BY id DESC LIMIT 40
                )
            """)

    def get_history(self, limit: int = 20) -> list:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT role, content FROM conversation_history ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [{'role': r['role'], 'content': r['content']} for r in reversed(rows)]

    def clear_history(self):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM conversation_history")

    # =====================================================================
    # PERSISTENT AGENT MEMORY
    # =====================================================================
    def save_memory(self, key: str, value: str):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO user_memory (key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """, (key, value, datetime.now().isoformat()))

    def get_memory(self, key: str) -> str:
        with self._get_conn() as conn:
            row = conn.execute("SELECT value FROM user_memory WHERE key = ?", (key,)).fetchone()
            return row['value'] if row else None

    def get_all_memory(self) -> dict:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT key, value FROM user_memory").fetchall()
            return {row['key']: row['value'] for row in rows}

    def delete_memory(self, key: str) -> bool:
        with self._get_conn() as conn:
            result = conn.execute("DELETE FROM user_memory WHERE key = ?", (key,))
            return result.rowcount > 0

    # =====================================================================
    # SCHEDULE, SEARCH & CONTEXT
    # =====================================================================
    def check_schedule_conflict(self, check_date, check_time):
        if not check_date or not check_time:
            return "Clear"
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT title FROM tasks WHERE due_date = ? AND due_time = ? AND completed = 0",
                (check_date, check_time)
            ).fetchone()
            if row:
                return f"Conflict Found: '{row['title']}' is already scheduled at {check_date} {check_time}."
            return "Clear"

    def search_data(self, query: str = "", item_type: str = "all") -> dict:
        q = f"%{query.lower()}%"
        results = {"tasks": [], "notes": [], "workspaces": []}
        with self._get_conn() as conn:
            if item_type in ("all", "task"):
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE lower(title) LIKE ? OR lower(description) LIKE ?", (q, q)
                ).fetchall()
                results["tasks"] = [self._row_to_dict(r) for r in rows]
            if item_type in ("all", "note"):
                rows = conn.execute(
                    "SELECT * FROM notes WHERE lower(title) LIKE ? OR lower(content) LIKE ?", (q, q)
                ).fetchall()
                results["notes"] = [self._row_to_dict(r) for r in rows]
            if item_type in ("all", "workspace"):
                rows = conn.execute(
                    "SELECT * FROM workspaces WHERE lower(name) LIKE ? OR lower(description) LIKE ?", (q, q)
                ).fetchall()
                results["workspaces"] = [self._row_to_dict(r) for r in rows]
        return results

    def get_overdue_tasks(self) -> list:
        today = datetime.now().strftime('%Y-%m-%d')
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE due_date < ? AND completed = 0 ORDER BY due_date ASC", (today,)
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def get_todays_tasks(self) -> list:
        today = datetime.now().strftime('%Y-%m-%d')
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE due_date = ? AND completed = 0 ORDER BY due_time ASC", (today,)
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def get_upcoming_tasks(self, days: int = 3) -> list:
        """Tasks due in the next N days — used in daily briefing."""
        today = datetime.now().strftime('%Y-%m-%d')
        future = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE due_date > ? AND due_date <= ? AND completed = 0 ORDER BY due_date ASC, due_time ASC",
                (today, future)
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def get_daily_briefing(self) -> dict:
        """Full context snapshot for the daily briefing feature."""
        now = datetime.now()
        hour = now.hour
        if hour < 12:
            period = "morning"
        elif hour < 17:
            period = "afternoon"
        else:
            period = "evening"

        return {
            "now": now.strftime('%Y-%m-%d %H:%M'),
            "day": now.strftime('%A, %B %d %Y'),
            "period": period,
            "overdue": self.get_overdue_tasks(),
            "today": self.get_todays_tasks(),
            "upcoming": self.get_upcoming_tasks(days=3),
            "memory": self.get_all_memory(),
            "analytics": self.get_analytics(),
        }

    # =====================================================================
    # RECURRENCE — spawn next occurrence when a recurring task is completed
    # =====================================================================
    RECURRENCE_MAP = {
        'daily': 1, 'weekly': 7, 'biweekly': 14, 'monthly': 30,
        'يومي': 1, 'أسبوعي': 7, 'شهري': 30,
    }

    def spawn_next_recurrence(self, task: dict) -> dict:
        """When a recurring task is completed, create its next occurrence."""
        recurrence = task.get('recurrence', '').lower().strip()
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
            title=task['title'],
            description=task.get('description', ''),
            due_date=next_date,
            due_time=task.get('due_time'),
            priority=task.get('priority', 'medium'),
            category=task.get('category', 'personal'),
            workspace_id=task.get('workspace_id'),
            recurrence=recurrence,
        )

    # =====================================================================
    # WORKSPACES
    # =====================================================================
    def create_workspace(self, name, description="", color="#8A2BE2"):
        with self._get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO workspaces (name, description, color, created_at) VALUES (?, ?, ?, ?)",
                (str(name).strip(), str(description).strip(), color, datetime.now().isoformat())
            )
            return self._row_to_dict(conn.execute("SELECT * FROM workspaces WHERE id = ?", (cur.lastrowid,)).fetchone())

    def get_workspaces(self):
        with self._get_conn() as conn:
            return [self._row_to_dict(r) for r in conn.execute(
                "SELECT * FROM workspaces ORDER BY created_at DESC"
            ).fetchall()]

    def update_workspace(self, workspace_id, updates: dict):
        allowed = {'name', 'description', 'color'}
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if not filtered:
            return None
        cols = ', '.join(f"{k} = ?" for k in filtered)
        vals = list(filtered.values()) + [int(workspace_id)]
        with self._get_conn() as conn:
            conn.execute(f"UPDATE workspaces SET {cols} WHERE id = ?", vals)
            return self._row_to_dict(conn.execute("SELECT * FROM workspaces WHERE id = ?", (int(workspace_id),)).fetchone())

    def delete_workspace(self, workspace_id):
        with self._get_conn() as conn:
            result = conn.execute("DELETE FROM workspaces WHERE id = ?", (int(workspace_id),))
            return result.rowcount > 0

    def get_workspace_summary(self, workspace_id: int) -> dict:
        """Full summary of a workspace for PDF export."""
        with self._get_conn() as conn:
            ws = self._row_to_dict(conn.execute("SELECT * FROM workspaces WHERE id = ?", (int(workspace_id),)).fetchone())
            if not ws:
                return None
            tasks = [self._row_to_dict(r) for r in conn.execute(
                "SELECT * FROM tasks WHERE workspace_id = ? ORDER BY due_date ASC", (int(workspace_id),)
            ).fetchall()]
            notes = [self._row_to_dict(r) for r in conn.execute(
                "SELECT * FROM notes WHERE workspace_id = ? ORDER BY created_at DESC", (int(workspace_id),)
            ).fetchall()]
            return {"workspace": ws, "tasks": tasks, "notes": notes}

    # =====================================================================
    # TASKS
    # =====================================================================
    def create_task(self, title, description="", due_date=None, due_time=None, duration=None,
                    priority="medium", language="en", category="personal",
                    start_date=None, end_date=None, workspace_id=None,
                    recurrence=None, depends_on=None, linked_note_id=None):
        today = datetime.now().strftime('%Y-%m-%d')
        if not due_date or (due_date < today and not start_date):
            due_date = today
        with self._get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO tasks (title, description, due_date, due_time, duration, priority,
                    category, language, start_date, end_date, workspace_id, completed,
                    recurrence, depends_on, linked_note_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
            """, (
                str(title).strip(), str(description).strip(),
                due_date, due_time, duration, priority, category, language,
                start_date, end_date,
                int(workspace_id) if workspace_id else None,
                recurrence,
                int(depends_on) if depends_on else None,
                int(linked_note_id) if linked_note_id else None,
                datetime.now().isoformat()
            ))
            conn.execute(
                "UPDATE analytics SET total_tasks_created = total_tasks_created + 1, last_activity = ? WHERE id = 1",
                (datetime.now().isoformat(),)
            )
            return self._row_to_dict(conn.execute("SELECT * FROM tasks WHERE id = ?", (cur.lastrowid,)).fetchone())

    def get_tasks(self):
        with self._get_conn() as conn:
            return [self._row_to_dict(r) for r in conn.execute(
                "SELECT * FROM tasks ORDER BY completed ASC, due_date ASC, due_time ASC"
            ).fetchall()]

    def complete_task(self, task_id: int) -> dict:
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE tasks SET completed = 1, completed_at = ?, updated_at = ? WHERE id = ?",
                (now, now, int(task_id))
            )
            task = self._row_to_dict(conn.execute("SELECT * FROM tasks WHERE id = ?", (int(task_id),)).fetchone())
        # Spawn next recurrence if applicable
        if task and task.get('recurrence'):
            self.spawn_next_recurrence(task)
        return task

    def uncomplete_task(self, task_id: int) -> dict:
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE tasks SET completed = 0, completed_at = NULL, updated_at = ? WHERE id = ?",
                (now, int(task_id))
            )
            return self._row_to_dict(conn.execute("SELECT * FROM tasks WHERE id = ?", (int(task_id),)).fetchone())

    def update_task(self, task_id, updates: dict):
        allowed = {'title', 'description', 'due_date', 'due_time', 'priority',
                   'completed', 'duration', 'workspace_id', 'recurrence', 'depends_on', 'linked_note_id'}
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if not filtered:
            return None
        filtered['updated_at'] = datetime.now().isoformat()
        cols = ', '.join(f"{k} = ?" for k in filtered)
        vals = list(filtered.values()) + [int(task_id)]
        with self._get_conn() as conn:
            conn.execute(f"UPDATE tasks SET {cols} WHERE id = ?", vals)
            return self._row_to_dict(conn.execute("SELECT * FROM tasks WHERE id = ?", (int(task_id),)).fetchone())

    def delete_task(self, task_id):
        with self._get_conn() as conn:
            result = conn.execute("DELETE FROM tasks WHERE id = ?", (int(task_id),))
            return result.rowcount > 0

    def is_task_blocked(self, task_id: int) -> bool:
        """Returns True if the task's dependency is not yet completed."""
        with self._get_conn() as conn:
            row = conn.execute("SELECT depends_on FROM tasks WHERE id = ?", (int(task_id),)).fetchone()
            if not row or not row['depends_on']:
                return False
            dep = conn.execute("SELECT completed FROM tasks WHERE id = ?", (row['depends_on'],)).fetchone()
            return dep is not None and not bool(dep['completed'])

    # =====================================================================
    # NOTES
    # =====================================================================
    def create_note(self, title, content, category="General", language="en",
                    workspace_id=None, linked_task_id=None):
        word_count = len(str(content).split())
        with self._get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO notes (title, content, category, language, workspace_id,
                    linked_task_id, word_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(title).strip(), str(content), category, language,
                int(workspace_id) if workspace_id else None,
                int(linked_task_id) if linked_task_id else None,
                word_count, datetime.now().isoformat()
            ))
            conn.execute(
                "UPDATE analytics SET total_notes_created = total_notes_created + 1, last_activity = ? WHERE id = 1",
                (datetime.now().isoformat(),)
            )
            return self._row_to_dict(conn.execute("SELECT * FROM notes WHERE id = ?", (cur.lastrowid,)).fetchone())

    def get_notes(self):
        with self._get_conn() as conn:
            return [self._row_to_dict(r) for r in conn.execute(
                "SELECT * FROM notes ORDER BY created_at DESC"
            ).fetchall()]

    def update_note(self, note_id, updates: dict):
        allowed = {'title', 'content', 'category', 'workspace_id', 'linked_task_id'}
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if not filtered:
            return None
        if 'content' in filtered:
            filtered['word_count'] = len(str(filtered['content']).split())
        filtered['updated_at'] = datetime.now().isoformat()
        cols = ', '.join(f"{k} = ?" for k in filtered)
        vals = list(filtered.values()) + [int(note_id)]
        with self._get_conn() as conn:
            conn.execute(f"UPDATE notes SET {cols} WHERE id = ?", vals)
            return self._row_to_dict(conn.execute("SELECT * FROM notes WHERE id = ?", (int(note_id),)).fetchone())

    def delete_note(self, note_id):
        with self._get_conn() as conn:
            result = conn.execute("DELETE FROM notes WHERE id = ?", (int(note_id),))
            return result.rowcount > 0

    # =====================================================================
    # UTILITY
    # =====================================================================
    def clear_all(self):
        with self._get_conn() as conn:
            conn.executescript("""
                DELETE FROM tasks;
                DELETE FROM notes;
                DELETE FROM workspaces;
                DELETE FROM user_memory;
                DELETE FROM conversation_history;
                UPDATE analytics SET total_tasks_created=0, total_notes_created=0, last_activity=NULL WHERE id=1;
            """)

    def get_analytics(self):
        """Basic counts for the header stats bar."""
        tasks = self.get_tasks()
        notes = self.get_notes()
        with self._get_conn() as conn:
            row = self._row_to_dict(conn.execute("SELECT * FROM analytics WHERE id = 1").fetchone())
        return {
            'total_tasks': len(tasks),
            'total_notes': len(notes),
            'total_workspaces': len(self.get_workspaces()),
            'completed_tasks': len([t for t in tasks if t.get('completed')]),
            'total_tasks_created': row.get('total_tasks_created', 0),
            'total_notes_created': row.get('total_notes_created', 0),
            'overdue_tasks': len(self.get_overdue_tasks()),
        }

    def get_smart_analytics(self) -> dict:
        """
        Deep behavioral analytics derived entirely from SQLite timestamps and task data.
        Powers the tool_analyze_productivity agent tool and the analytics panel.
        """
        with self._get_conn() as conn:

            # --- COMPLETION STATS ---
            total = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            completed = conn.execute("SELECT COUNT(*) FROM tasks WHERE completed=1").fetchone()[0]
            overdue = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE completed=0 AND due_date < date('now')"
            ).fetchone()[0]
            completion_rate = round((completed / total * 100), 1) if total > 0 else 0

            # --- COMPLETION BY PRIORITY ---
            priority_stats = {}
            for pri in ['high', 'medium', 'low']:
                t = conn.execute("SELECT COUNT(*) FROM tasks WHERE priority=?", (pri,)).fetchone()[0]
                c = conn.execute("SELECT COUNT(*) FROM tasks WHERE priority=? AND completed=1", (pri,)).fetchone()[0]
                priority_stats[pri] = {
                    'total': t,
                    'completed': c,
                    'rate': round(c / t * 100, 1) if t > 0 else 0
                }

            # --- COMPLETION BY CATEGORY ---
            category_rows = conn.execute("""
                SELECT category,
                       COUNT(*) as total,
                       SUM(completed) as done
                FROM tasks
                GROUP BY category
                ORDER BY total DESC
            """).fetchall()
            category_stats = [
                {
                    'category': r['category'] or 'personal',
                    'total': r['total'],
                    'completed': r['done'] or 0,
                    'rate': round((r['done'] or 0) / r['total'] * 100, 1) if r['total'] > 0 else 0
                }
                for r in category_rows
            ]

            # --- MOST ACTIVE HOUR (when tasks are created) ---
            hour_rows = conn.execute("""
                SELECT CAST(strftime('%H', created_at) AS INTEGER) as hour,
                       COUNT(*) as count
                FROM tasks
                WHERE created_at IS NOT NULL
                GROUP BY hour
                ORDER BY count DESC
            """).fetchall()
            hourly_activity = [{'hour': r['hour'], 'count': r['count']} for r in hour_rows]
            peak_hour = hour_rows[0]['hour'] if hour_rows else None
            if peak_hour is not None:
                period = 'AM' if peak_hour < 12 else 'PM'
                display_hour = peak_hour if peak_hour <= 12 else peak_hour - 12
                display_hour = 12 if display_hour == 0 else display_hour
                peak_hour_label = f"{display_hour}:00 {period}"
            else:
                peak_hour_label = "Not enough data"

            # --- BUSIEST DAY OF WEEK ---
            day_map = {0: 'Sunday', 1: 'Monday', 2: 'Tuesday', 3: 'Wednesday',
                       4: 'Thursday', 5: 'Friday', 6: 'Saturday'}
            day_rows = conn.execute("""
                SELECT CAST(strftime('%w', due_date) AS INTEGER) as dow,
                       COUNT(*) as count
                FROM tasks
                WHERE due_date IS NOT NULL
                GROUP BY dow
                ORDER BY count DESC
            """).fetchall()
            daily_activity = [{'day': day_map.get(r['dow'], str(r['dow'])), 'count': r['count']} for r in day_rows]
            busiest_day = day_map.get(day_rows[0]['dow']) if day_rows else "Not enough data"

            # --- TASKS CREATED VS COMPLETED LAST 7 DAYS ---
            week_rows = conn.execute("""
                SELECT date(due_date) as day,
                       COUNT(*) as total,
                       SUM(completed) as done
                FROM tasks
                WHERE due_date >= date('now', '-7 days')
                  AND due_date <= date('now')
                GROUP BY day
                ORDER BY day ASC
            """).fetchall()
            weekly_trend = [
                {'day': r['day'], 'created': r['total'], 'completed': r['done'] or 0}
                for r in week_rows
            ]

            # --- AVERAGE COMPLETION TIME (hours between creation and completion) ---
            avg_rows = conn.execute("""
                SELECT AVG(
                    (julianday(completed_at) - julianday(created_at)) * 24
                ) as avg_hours
                FROM tasks
                WHERE completed=1
                  AND completed_at IS NOT NULL
                  AND created_at IS NOT NULL
            """).fetchone()
            avg_completion_hours = round(avg_rows['avg_hours'], 1) if avg_rows and avg_rows['avg_hours'] else None

            # --- MOST PRODUCTIVE WORKSPACE ---
            ws_rows = conn.execute("""
                SELECT w.name,
                       COUNT(t.id) as total,
                       SUM(t.completed) as done
                FROM workspaces w
                LEFT JOIN tasks t ON t.workspace_id = w.id
                GROUP BY w.id
                ORDER BY done DESC
            """).fetchall()
            workspace_stats = [
                {
                    'name': r['name'],
                    'total': r['total'] or 0,
                    'completed': r['done'] or 0,
                    'rate': round((r['done'] or 0) / (r['total'] or 1) * 100, 1)
                }
                for r in ws_rows
            ]

            # --- PROCRASTINATION INDEX (overdue by category) ---
            proc_rows = conn.execute("""
                SELECT category, COUNT(*) as overdue_count
                FROM tasks
                WHERE completed=0 AND due_date < date('now')
                GROUP BY category
                ORDER BY overdue_count DESC
            """).fetchall()
            procrastination = [{'category': r['category'] or 'personal', 'overdue': r['overdue_count']}
                               for r in proc_rows]

            # --- NOTES STATS ---
            total_notes = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
            avg_note_words = conn.execute("SELECT AVG(word_count) FROM notes").fetchone()[0]
            most_used_note_category = conn.execute("""
                SELECT category, COUNT(*) as c FROM notes
                GROUP BY category ORDER BY c DESC LIMIT 1
            """).fetchone()

            # --- STREAK: consecutive days with at least one completed task ---
            streak_rows = conn.execute("""
                SELECT DISTINCT date(completed_at) as day
                FROM tasks
                WHERE completed=1 AND completed_at IS NOT NULL
                ORDER BY day DESC
            """).fetchall()
            streak = 0
            if streak_rows:
                from datetime import datetime, timedelta
                today = datetime.now().date()
                for i, row in enumerate(streak_rows):
                    expected = (today - timedelta(days=i)).isoformat()
                    if row['day'] == expected:
                        streak += 1
                    else:
                        break

        return {
            # Headline numbers
            'total_tasks': total,
            'completed_tasks': completed,
            'overdue_tasks': overdue,
            'completion_rate': completion_rate,
            'current_streak_days': streak,

            # Time patterns
            'peak_creation_hour': peak_hour_label,
            'hourly_activity': hourly_activity,
            'busiest_day_of_week': busiest_day,
            'daily_activity': daily_activity,
            'weekly_trend': weekly_trend,

            # Quality patterns
            'avg_completion_time_hours': avg_completion_hours,
            'priority_breakdown': priority_stats,
            'category_breakdown': category_stats,
            'procrastination_by_category': procrastination,

            # Workspaces
            'workspace_productivity': workspace_stats,

            # Notes
            'total_notes': total_notes,
            'avg_note_words': round(avg_note_words, 0) if avg_note_words else 0,
            'top_note_category': most_used_note_category['category'] if most_used_note_category else 'General',
        }