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
                'last_id': 0
            }
            self.save_data()
    
    def save_data(self):
        with open(self.db_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
    
    def get_next_id(self):
        self.data['last_id'] += 1
        return self.data['last_id']
    
    def create_task(self, title, description, due_date=None, due_time=None, priority="medium", language="en"):
        task = {
            'id': self.get_next_id(),
            'title': title,
            'description': description,
            'due_date': due_date,
            'due_time': due_time,
            'priority': priority,
            'language': language,
            'created_at': datetime.now().isoformat(),
            'completed': False
        }
        self.data['tasks'].append(task)
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