"""
NOTE TO BACKEND TEAM:
This class implements the Data Access Object (DAO) pattern using a local JSON file ('data.json').
When integrating with the production environment, please replace the internal logic of 
'create_task', 'get_tasks', 'create_note', etc., to connect to your PostgreSQL/MongoDB instance.

Please MAINTAIN the method signatures (inputs) and return dictionary structures 
so the AI module (ai_handler.py) continues to function without changes.
"""

import json
import os
from datetime import datetime
import re
import logging
import shutil

class Database:
    def __init__(self, db_file='data.json'):
        self.db_file = db_file
        self.load_data()

    def load_data(self):
        """Loads data from the JSON file, creating defaults if missing."""
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
                
                # Migration/Safety: Ensure all required keys exist
                if 'tasks' not in self.data: self.data['tasks'] = []
                if 'notes' not in self.data: self.data['notes'] = []
                if 'last_id' not in self.data: self.data['last_id'] = 0
                if 'analytics' not in self.data:
                    self.data['analytics'] = {
                        'total_tasks_created': len(self.data.get('tasks', [])),
                        'total_notes_created': len(self.data.get('notes', [])),
                        'last_activity': datetime.now().isoformat()
                    }
                logging.info("Database loaded successfully")
            except Exception as e:
                logging.error(f"Error loading database: {e}. Creating new one.")
                self._create_default_data()
        else:
            self._create_default_data()

    def _create_default_data(self):
        """Resets the database structure."""
        self.data = {
            'tasks': [], 
            'notes': [], 
            'analytics': {
                'total_tasks_created': 0, 
                'total_notes_created': 0
            }, 
            'last_id': 0
        }
        self.save_data()

    def save_data(self):
        """Writes data to JSON atomically to prevent corruption."""
        try:
            # Write to a temp file first
            temp_file = self.db_file + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            
            # Atomic replacement
            os.replace(temp_file, self.db_file)
        except Exception as e:
            logging.error(f"Error saving database: {e}")

    def get_next_id(self):
        """Generates a simple unique ID."""
        self.data['last_id'] += 1
        return self.data['last_id']

    # --- TASK METHODS ---

    def create_task(self, title, description, due_date=None, due_time=None, duration=None, priority="medium", language="en", category="personal", start_date=None, end_date=None):
        task = {
            'id': self.get_next_id(),
            'title': title.strip(),
            'description': description.strip(),
            'due_date': due_date or datetime.now().strftime('%Y-%m-%d'),
            'due_time': due_time,
            'duration': duration,
            'priority': priority,
            'category': category,
            'language': language,
            'start_date': start_date,
            'end_date': end_date,
            'completed': False,
            'created_at': datetime.now().isoformat()
        }
        
        self.data['tasks'].append(task)
        self.data['analytics']['total_tasks_created'] += 1
        self.save_data()
        return task

    def get_tasks(self):
        return self.data.get('tasks', [])

    def update_task(self, task_id, updates):
        for task in self.data['tasks']:
            if int(task['id']) == int(task_id):
                task.update(updates)
                task['updated_at'] = datetime.now().isoformat()
                self.save_data()
                return task
        return None

    def delete_task(self, task_id):
        initial_count = len(self.data['tasks'])
        self.data['tasks'] = [t for t in self.data['tasks'] if int(t['id']) != int(task_id)]
        
        if len(self.data['tasks']) < initial_count:
            self.save_data()
            return True
        return False

    # --- NOTE METHODS ---

    def create_note(self, title, content, category="General", language="en"):
        note = {
            'id': self.get_next_id(),
            'title': title.strip(),
            'content': str(content),
            'category': category,
            'language': language,
            'word_count': len(str(content).split()),
            'created_at': datetime.now().isoformat()
        }
        
        self.data['notes'].append(note)
        self.data['analytics']['total_notes_created'] += 1
        self.save_data()
        return note

    def get_notes(self):
        return self.data.get('notes', [])

    def update_note(self, note_id, updates):
        for note in self.data['notes']:
            if int(note['id']) == int(note_id):
                note.update(updates)
                # Recalculate word count if content changed
                if 'content' in updates:
                    note['word_count'] = len(str(note['content']).split())
                
                note['updated_at'] = datetime.now().isoformat()
                self.save_data()
                return note
        return None

    def delete_note(self, note_id):
        initial_count = len(self.data['notes'])
        self.data['notes'] = [n for n in self.data['notes'] if int(n['id']) != int(note_id)]
        
        if len(self.data['notes']) < initial_count:
            self.save_data()
            return True
        return False

    # --- UTILITY METHODS ---

    def clear_all(self):
        """Wipes all data (Factory Reset)."""
        self._create_default_data()

    def get_analytics(self):
        """Calculates realtime stats for the frontend dashboard."""
        tasks = self.get_tasks()
        notes = self.get_notes()
        completed_tasks = len([t for t in tasks if t.get('completed', False)])

        return {
            'total_tasks': len(tasks),
            'total_notes': len(notes),
            'completed_tasks': completed_tasks,
            # Historical stats (kept even if items deleted)
            'total_tasks_created': self.data['analytics'].get('total_tasks_created', len(tasks)),
            'total_notes_created': self.data['analytics'].get('total_notes_created', len(notes))
        }