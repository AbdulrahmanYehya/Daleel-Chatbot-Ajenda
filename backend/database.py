import json
import os
from datetime import datetime, timedelta
import re
import logging

class Database:
    def __init__(self, db_file='data.json'):
        self.db_file = db_file
        self.load_data()
    
    def load_data(self):
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
                
                # ADD THIS: Ensure analytics field exists for existing databases
                if 'analytics' not in self.data:
                    self.data['analytics'] = {
                        'total_tasks_created': len(self.data.get('tasks', [])),
                        'total_notes_created': len(self.data.get('notes', [])),
                        'last_activity': datetime.now().isoformat(),
                        'ai_interactions': 0
                    }
                    self.save_data()
                    
                logging.info("Database loaded successfully")
            except Exception as e:
                logging.error(f"Error loading database: {e}")
                self._create_default_data()
        else:
            self._create_default_data()
    
    def _create_default_data(self):
        self.data = {
            'tasks': [],
            'notes': [],
            'analytics': {  # ADD THIS ANALYTICS SECTION
                'total_tasks_created': 0,
                'total_notes_created': 0,
                'last_activity': datetime.now().isoformat(),
                'ai_interactions': 0
            },
            'last_id': 0,
            'ai_context': {}
        }
        self.save_data()
    
    def save_data(self):
        try:
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Error saving database: {e}")
    
    def get_next_id(self):
        self.data['last_id'] += 1
        return self.data['last_id']
    
    def create_task(self, title, description, due_date=None, due_time=None, duration=None, 
                   priority="medium", language="en", category="work", start_date=None, end_date=None):
        # Parse date range if provided
        if due_date and '-' in due_date:
            start_date, end_date = self.parse_date_range(due_date)
            due_date = start_date  # Use start date as primary due date
        
        task = {
            'id': self.get_next_id(),
            'title': title,
            'description': description,
            'due_date': due_date or datetime.now().strftime('%Y-%m-%d'),
            'due_time': due_time,
            'duration': duration or '1 hour',
            'priority': priority,
            'category': category,
            'language': language,
            'start_date': start_date,
            'end_date': end_date,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'completed': False,
            'completed_at': None,
            'ai_generated': True  # Mark as AI-generated
        }
        self.data['tasks'].append(task)
        self.data['analytics']['total_tasks_created'] += 1
        self.data['analytics']['last_activity'] = datetime.now().isoformat()
        self.data['analytics']['ai_interactions'] = self.data['analytics'].get('ai_interactions', 0) + 1
        self.save_data()
        return task
    
    def create_note(self, title, content, category="General", language="en", 
                   word_count=None, paragraph_count=None, character_count=None):
        note = {
            'id': self.get_next_id(),
            'title': title,
            'content': content,
            'category': category,
            'language': language,
            'word_count': word_count or len(content.split()),
            'paragraph_count': paragraph_count or len([p for p in content.split('\n') if p.strip()]),
            'character_count': character_count or len(content),
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'ai_generated': True  # Mark as AI-generated
        }
        self.data['notes'].append(note)
        self.data['analytics']['total_notes_created'] += 1
        self.data['analytics']['last_activity'] = datetime.now().isoformat()
        self.data['analytics']['ai_interactions'] = self.data['analytics'].get('ai_interactions', 0) + 1
        self.save_data()
        return note
    
    def parse_date_range(self, date_string):
        """Parse date ranges like '06/November/2025 - 09/November/2025'"""
        if not date_string or '-' not in date_string:
            return date_string, None
        
        try:
            start_str, end_str = date_string.split('-', 1)
            start_str = start_str.strip()
            end_str = end_str.strip()
            
            # Parse dates
            start_date = self._parse_custom_date(start_str)
            end_date = self._parse_custom_date(end_str)
            
            return start_date, end_date
        except:
            return date_string, None
    
    def _parse_custom_date(self, date_str):
        """Parse dates in various formats"""
        try:
            # Handle formats like "06/November/2025"
            if '/' in date_str:
                parts = date_str.split('/')
                if len(parts) == 3:
                    day, month, year = parts
                    month_num = {
                        'january': 1, 'february': 2, 'march': 3, 'april': 4,
                        'may': 5, 'june': 6, 'july': 7, 'august': 8,
                        'september': 9, 'october': 10, 'november': 11, 'december': 12
                    }.get(month.lower().strip(), datetime.now().month)
                    
                    return f"{year.strip()}-{month_num:02d}-{int(day.strip()):02d}"
            
            # Default to today if parsing fails
            return datetime.now().strftime('%Y-%m-%d')
        except:
            return datetime.now().strftime('%Y-%m-%d')
    
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
    
    def update_ai_context(self, context_updates):
        """Update AI conversation context"""
        if 'ai_context' not in self.data:
            self.data['ai_context'] = {}
        
        self.data['ai_context'].update(context_updates)
        self.save_data()
    
    def get_ai_context(self):
        """Get AI conversation context"""
        return self.data.get('ai_context', {})