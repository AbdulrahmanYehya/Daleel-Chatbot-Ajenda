import json
import os
from datetime import datetime

class Database:
    def __init__(self, db_file='data.json'):
        self.db_file = db_file
        self.load_data()
    
    def load_data(self):
        if os.path.exists(self.db_file):
            with open(self.db_file, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
        else:
            self.data = {
                'tasks': [],
                'notes': [],
                'analytics': {
                    'total_tasks_created': 0,
                    'total_notes_created': 0,
                    'last_activity': datetime.now().isoformat()
                },
                'last_id': 0
            }
            self.save_data()
    
    def save_data(self):
        with open(self.db_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
    
    def get_next_id(self):
        self.data['last_id'] += 1
        return self.data['last_id']
    
    def create_task(self, title, description, due_date=None, due_time=None, duration="1 hour", priority="medium", category="work", language="en"):
        task = {
            'id': self.get_next_id(),
            'title': title,
            'description': description,
            'due_date': due_date or datetime.now().strftime('%Y-%m-%d'),
            'due_time': due_time,
            'duration': duration,
            'priority': priority,
            'category': category,
            'language': language,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'completed': False,
            'completed_at': None
        }
        self.data['tasks'].append(task)
        self.data['analytics']['total_tasks_created'] += 1
        self.data['analytics']['last_activity'] = datetime.now().isoformat()
        self.save_data()
        return task
    
    def create_note(self, title, content, category="General", language="en"):
        note = {
            'id': self.get_next_id(),
            'title': title,
            'content': content,
            'category': category,
            'language': language,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        self.data['notes'].append(note)
        self.data['analytics']['total_notes_created'] += 1
        self.data['analytics']['last_activity'] = datetime.now().isoformat()
        self.save_data()
        return note
    
    def get_tasks(self):
        return self.data['tasks']
    
    def get_notes(self):
        return self.data['notes']
    
    def delete_task(self, task_id):
        self.data['tasks'] = [t for t in self.data['tasks'] if t['id'] != task_id]
        self.save_data()
    
    def delete_note(self, note_id):
        self.data['notes'] = [n for n in self.data['notes'] if n['id'] != note_id]
        self.save_data()
    
    def clear_all(self):
        self.data['tasks'] = []
        self.data['notes'] = []
        self.save_data()
    
    def complete_task(self, task_id):
        for task in self.data['tasks']:
            if task['id'] == task_id:
                task['completed'] = True
                task['completed_at'] = datetime.now().isoformat()
                self.save_data()
                return True
        return False