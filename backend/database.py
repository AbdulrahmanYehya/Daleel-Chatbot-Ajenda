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

                # Migration: Ensure essential keys exist
                if 'tasks' not in self.data: self.data['tasks'] = []
                if 'notes' not in self.data: self.data['notes'] = []
                if 'last_id' not in self.data: self.data['last_id'] = 0
                if 'ai_context' not in self.data: self.data['ai_context'] = {}
                if 'analytics' not in self.data or not isinstance(self.data['analytics'], dict):
                    self.data['analytics'] = {
                        'total_tasks_created': len(self.data.get('tasks', [])),
                        'total_notes_created': len(self.data.get('notes', [])),
                        'last_activity': datetime.now().isoformat(),
                        'ai_interactions': 0
                    }
                    self.save_data() # Save migrated structure

                logging.info("Database loaded successfully")
            except json.JSONDecodeError as e:
                logging.error(f"Error decoding JSON from database file '{self.db_file}': {e}. Creating default data.")
                self._create_default_data()
            except Exception as e:
                logging.error(f"Unexpected error loading database: {e}", exc_info=True)
                self._create_default_data()
        else:
            logging.info(f"Database file '{self.db_file}' not found. Creating default data.")
            self._create_default_data()

    def _create_default_data(self):
        self.data = {
            'tasks': [],
            'notes': [],
            'analytics': {
                'total_tasks_created': 0,
                'total_notes_created': 0,
                'last_activity': datetime.now().isoformat(),
                'ai_interactions': 0
            },
            'last_id': 0,
            'ai_context': {}
        }
        self.save_data()
        logging.info("Created default database structure.")

    def save_data(self):
        try:
            # Create backup before saving
            backup_file = self.db_file + '.bak'
            if os.path.exists(self.db_file):
                try:
                    os.replace(self.db_file, backup_file) # Atomic rename if possible
                except OSError: # Fallback for cross-device or permission issues
                     import shutil
                     shutil.copy2(self.db_file, backup_file)


            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            # Remove backup after successful save
            if os.path.exists(backup_file):
                try:
                    os.remove(backup_file)
                except OSError as e:
                     logging.warning(f"Could not remove backup file {backup_file}: {e}")

        except Exception as e:
            logging.error(f"Error saving database: {e}", exc_info=True)
            # Attempt to restore from backup if save failed
            if os.path.exists(backup_file):
                 try:
                      os.replace(backup_file, self.db_file)
                      logging.info("Restored database from backup due to save error.")
                 except OSError as restore_err:
                      logging.error(f"CRITICAL: Failed to restore database from backup: {restore_err}")


    def get_next_id(self):
        # Ensure last_id is an int
        if not isinstance(self.data.get('last_id'), int):
            self.data['last_id'] = 0
        self.data['last_id'] += 1
        return self.data['last_id']

    def create_task(self, title, description, due_date=None, due_time=None, duration=None,
                   priority="medium", language="en", category="personal", start_date=None, end_date=None):

        # Validate and parse date/range
        parsed_due_date = self._parse_custom_date(due_date) if due_date else datetime.now().strftime('%Y-%m-%d')
        parsed_start_date = self._parse_custom_date(start_date) if start_date else None
        parsed_end_date = self._parse_custom_date(end_date) if end_date else None

        # Handle explicit date range string like "YYYY-MM-DD - YYYY-MM-DD" passed in due_date
        if isinstance(due_date, str) and ' - ' in due_date:
            try:
                start_str, end_str = due_date.split(' - ', 1)
                parsed_start_date = self._parse_custom_date(start_str)
                parsed_end_date = self._parse_custom_date(end_str)
                parsed_due_date = parsed_start_date # Use start date as primary
            except:
                logging.warning(f"Could not parse date range string: {due_date}")
                # Fallback: use the first part if possible
                parsed_due_date = self._parse_custom_date(due_date.split(' - ')[0])


        task = {
            'id': self.get_next_id(),
            'title': title.strip(),
            'description': description.strip(),
            'due_date': parsed_due_date,
            'due_time': due_time, # Should already be HH:MM or None
            'duration': duration, # Keep duration as provided (e.g., "1 hour") or None
            'priority': priority if priority in ['high', 'medium', 'low'] else 'medium',
            'category': category or 'personal',
            'language': language,
            'start_date': parsed_start_date,
            'end_date': parsed_end_date,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'completed': False,
            'completed_at': None,
            'ai_generated': True
        }
        self.data['tasks'].append(task)

        # Update analytics
        self.data['analytics']['total_tasks_created'] = self.data['analytics'].get('total_tasks_created', 0) + 1
        self.data['analytics']['last_activity'] = datetime.now().isoformat()
        self.data['analytics']['ai_interactions'] = self.data['analytics'].get('ai_interactions', 0) + 1

        self.save_data()
        logging.info(f"Task created: ID={task['id']}, Title='{task['title']}'")
        return task

    def create_note(self, title, content, category="General", language="en",
                   word_count=None, paragraph_count=None, character_count=None):

        # Calculate stats if not provided
        content_str = str(content) # Ensure content is string
        if word_count is None:
            word_count = len(content_str.split())
        if paragraph_count is None:
            paragraph_count = len([p for p in content_str.split('\n') if p.strip()])
        if character_count is None:
            character_count = len(content_str)

        note = {
            'id': self.get_next_id(),
            'title': title.strip(),
            'content': content_str,
            'category': category or 'General',
            'language': language,
            'word_count': word_count,
            'paragraph_count': paragraph_count,
            'character_count': character_count,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'ai_generated': True
        }
        self.data['notes'].append(note)

        # Update analytics
        self.data['analytics']['total_notes_created'] = self.data['analytics'].get('total_notes_created', 0) + 1
        self.data['analytics']['last_activity'] = datetime.now().isoformat()
        self.data['analytics']['ai_interactions'] = self.data['analytics'].get('ai_interactions', 0) + 1

        self.save_data()
        logging.info(f"Note created: ID={note['id']}, Title='{note['title']}'")
        return note

    def _parse_custom_date(self, date_str):
        """Parse dates in various formats (YYYY-MM-DD, DD/Month/YYYY)."""
        if not date_str or not isinstance(date_str, str):
            # Return current date if input is invalid or None
             # logging.warning(f"Invalid date input '{date_str}', defaulting to today.")
             return datetime.now().strftime('%Y-%m-%d')

        date_str = date_str.strip()

        # Try YYYY-MM-DD format first
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            try:
                datetime.strptime(date_str, '%Y-%m-%d')
                return date_str
            except ValueError:
                pass # Invalid date, try other formats

        # Try DD/MonthName/YYYY format
        try:
             # Handle English month names
            dt_obj = datetime.strptime(date_str, '%d/%B/%Y')
            return dt_obj.strftime('%Y-%m-%d')
        except ValueError:
             pass # Try Arabic month names or other formats

        # Add parsing for Arabic month names if needed
        # ...

        # Default to today if all parsing fails
        # logging.warning(f"Could not parse date '{date_str}', defaulting to today.")
        return datetime.now().strftime('%Y-%m-%d')

    def get_tasks(self):
        # Sort by creation date, newest first (optional)
        return sorted(self.data.get('tasks', []), key=lambda t: t.get('created_at', ''), reverse=True)

    def get_notes(self):
        # Sort by creation date, newest first (optional)
        return sorted(self.data.get('notes', []), key=lambda n: n.get('created_at', ''), reverse=True)

    def delete_task(self, task_id):
        try:
            task_id = int(task_id)
            initial_len = len(self.data['tasks'])
            self.data['tasks'] = [t for t in self.data['tasks'] if t['id'] != task_id]
            if len(self.data['tasks']) < initial_len:
                self.save_data()
                logging.info(f"Task deleted: {task_id}")
                return True
            else:
                 logging.warning(f"Task not found for deletion: {task_id}")
                 return False
        except ValueError:
             logging.error(f"Invalid task ID for deletion: {task_id}")
             return False

    def delete_note(self, note_id):
        try:
            note_id = int(note_id)
            initial_len = len(self.data['notes'])
            self.data['notes'] = [n for n in self.data['notes'] if n['id'] != note_id]
            if len(self.data['notes']) < initial_len:
                self.save_data()
                logging.info(f"Note deleted: {note_id}")
                return True
            else:
                 logging.warning(f"Note not found for deletion: {note_id}")
                 return False
        except ValueError:
             logging.error(f"Invalid note ID for deletion: {note_id}")
             return False

    def clear_all(self):
        self.data['tasks'] = []
        self.data['notes'] = []
        self.data['last_id'] = 0
        self.data['ai_context'] = {}
        # Reset analytics, keeping structure
        self.data['analytics'] = {
            'total_tasks_created': 0,
            'total_notes_created': 0,
            'last_activity': datetime.now().isoformat(),
            'ai_interactions': 0
        }
        self.save_data()
        logging.info("Database cleared.")

    def update_ai_context(self, context_updates):
        # (Unchanged)
        if 'ai_context' not in self.data:
            self.data['ai_context'] = {}
        self.data['ai_context'].update(context_updates)
        # Maybe limit context size here too?
        self.save_data()

    def get_ai_context(self):
        # (Unchanged)
        return self.data.get('ai_context', {})

    # --- Search and Update Functions ---

    def find_tasks_by_keyword(self, keyword, language=None):
        """Search tasks by title or description (case-insensitive)."""
        keyword = keyword.lower().strip()
        results = []
        if not keyword: return results
        for task in self.data.get('tasks', []):
            if keyword in task['title'].lower() or keyword in task.get('description', '').lower():
                results.append(task)
        logging.debug(f"Found {len(results)} tasks matching '{keyword}'")
        return results

    def find_notes_by_keyword(self, keyword, language=None):
        """Search notes by title or content (case-insensitive)."""
        keyword = keyword.lower().strip()
        results = []
        if not keyword: return results
        for note in self.data.get('notes', []):
            if keyword in note['title'].lower() or keyword in note.get('content', '').lower():
                results.append(note)
        logging.debug(f"Found {len(results)} notes matching '{keyword}'")
        return results

    def update_task(self, task_id, updates):
        """Update specific fields of a task."""
        try:
            task_id = int(task_id)
            task_found = False
            for task in self.data['tasks']:
                if task['id'] == task_id:
                    logging.info(f"Updating task ID {task_id} with: {updates}")
                    for key, value in updates.items():
                        if key in task:
                            # Add specific validation/parsing if needed
                            if key == 'due_date':
                                value = self._parse_custom_date(value)
                            # Add validation for priority, etc.
                            if key == 'priority' and value not in ['high', 'medium', 'low']:
                                logging.warning(f"Invalid priority '{value}' ignored for task {task_id}")
                                continue

                            task[key] = value
                            logging.debug(f"Task {task_id}: Set {key} = {value}")
                        else:
                            logging.warning(f"Attempted to update non-existent key '{key}' on task {task_id}")
                    task['updated_at'] = datetime.now().isoformat()
                    task_found = True
                    self.save_data()
                    logging.info(f"Task {task_id} updated successfully.")
                    return task # Return the updated task
            
            if not task_found:
                 logging.error(f"Task not found for update: {task_id}")
                 raise ValueError(f"Task with ID {task_id} not found.")
                 
        except ValueError:
            logging.error(f"Invalid task ID for update: {task_id}")
            raise ValueError(f"Invalid Task ID: {task_id}")
        except Exception as e:
             logging.error(f"Error updating task {task_id}: {e}", exc_info=True)
             raise e # Re-raise the exception


    def update_note(self, note_id, updates):
        """Update specific fields of a note."""
        try:
            note_id = int(note_id)
            note_found = False
            for note in self.data['notes']:
                if note['id'] == note_id:
                    logging.info(f"Updating note ID {note_id} with: {updates}")
                    content_updated = False
                    for key, value in updates.items():
                        if key in note:
                            note[key] = value
                            if key == 'content':
                                 content_updated = True
                            logging.debug(f"Note {note_id}: Set {key} = {value}")
                        else:
                            logging.warning(f"Attempted to update non-existent key '{key}' on note {note_id}")

                    # Recalculate stats if content changed
                    if content_updated:
                         note['content'] = str(note['content']) # Ensure string
                         note['word_count'] = len(note['content'].split())
                         note['paragraph_count'] = len([p for p in note['content'].split('\n') if p.strip()])
                         note['character_count'] = len(note['content'])

                    note['updated_at'] = datetime.now().isoformat()
                    note_found = True
                    self.save_data()
                    logging.info(f"Note {note_id} updated successfully.")
                    return note # Return the updated note

            if not note_found:
                 logging.error(f"Note not found for update: {note_id}")
                 raise ValueError(f"Note with ID {note_id} not found.")

        except ValueError:
            logging.error(f"Invalid note ID for update: {note_id}")
            raise ValueError(f"Invalid Note ID: {note_id}")
        except Exception as e:
             logging.error(f"Error updating note {note_id}: {e}", exc_info=True)
             raise e # Re-raise the exception


    def get_analytics(self):
        """Get analytics data, calculating counts."""
        # Ensure analytics structure exists
        if 'analytics' not in self.data or not isinstance(self.data['analytics'], dict):
            self._create_default_data()

        tasks = self.get_tasks()
        notes = self.get_notes()
        completed_tasks_count = len([t for t in tasks if t.get('completed', False)])

        # Update core counts based on current data
        analytics_data = self.data['analytics']
        analytics_data['total_tasks'] = len(tasks) # Current total
        analytics_data['total_notes'] = len(notes) # Current total
        analytics_data['completed_tasks'] = completed_tasks_count

        # Keep historical creation counts and interactions if they exist
        analytics_data['total_tasks_created'] = analytics_data.get('total_tasks_created', len(tasks))
        analytics_data['total_notes_created'] = analytics_data.get('total_notes_created', len(notes))
        analytics_data['ai_interactions'] = analytics_data.get('ai_interactions', 0)
        analytics_data['last_activity'] = analytics_data.get('last_activity', datetime.now().isoformat())

        # You could add more derived analytics here (e.g., completion rate)
        # analytics_data['completion_rate'] = f"{completed_tasks_count / len(tasks) * 100:.0f}%" if tasks else "0%"

        return analytics_data