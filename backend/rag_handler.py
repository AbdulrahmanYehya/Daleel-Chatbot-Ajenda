import json
import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import os
import pickle
from datetime import datetime
import logging

class EnhancedRAGHandler:
    def __init__(self):
        self.examples = self._load_examples()
        self.vectorizer = TfidfVectorizer(analyzer='word', stop_words=None, max_features=2000)
        self._build_or_load_index()
    
    def _load_examples(self):
        try:
            from rag_examples import RAG_EXAMPLES
            # Filter out research examples as they are no longer needed
            if 'notes_ar' in RAG_EXAMPLES:
                RAG_EXAMPLES['notes_ar'] = [
                    ex for ex in RAG_EXAMPLES['notes_ar'] 
                    if ex.get('output', {}).get('notes', [{}])[0].get('category') != 'Research'
                ]
            if 'notes_en' in RAG_EXAMPLES:
                RAG_EXAMPLES['notes_en'] = [
                    ex for ex in RAG_EXAMPLES['notes_en'] 
                    if ex.get('output', {}).get('notes', [{}])[0].get('category') != 'Research'
                ]
            
            logging.info(f"✅ Loaded {sum(len(examples) for examples in RAG_EXAMPLES.values())} RAG examples (research excluded)")
            return RAG_EXAMPLES
        except ImportError:
            logging.error("❌ Could not load RAG examples file")
            # Return minimal examples as backup
            return {
                'tasks_ar': [
                    {"input": "اعمل مهمة", "output": {"tasks": [{"title": "مهمة", "description": "وصف المهمة", "due_date": "2024-01-15", "priority": "medium"}]}}
                ],
                'tasks_en': [
                    {"input": "Create task", "output": {"tasks": [{"title": "Task", "description": "Task description", "due_date": "2024-01-15", "priority": "medium"}]}}
                ],
                'notes_ar': [
                    {"input": "اكتب ملاحظة", "output": {"notes": [{"title": "ملاحظة", "content": "محتوى الملاحظة", "category": "General"}]}}
                ],
                'notes_en': [
                    {"input": "Write note", "output": {"notes": [{"title": "Note", "content": "Note content", "category": "General"}]}}
                ]
            }
    
    def _build_or_load_index(self):
        """Build or load precomputed RAG index"""
        cache_file = 'rag_index_cache.pkl'
        
        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'rb') as f:
                    cache_data = pickle.load(f)
                    self.vectorizer = cache_data['vectorizer']
                    self.tfidf_matrix = cache_data['tfidf_matrix']
                    self.example_map = cache_data['example_map']
                logging.info("Loaded RAG index from cache")
            else:
                self._build_index()
                self._save_index_cache(cache_file)
        except Exception as e:
            logging.error(f"Error loading RAG cache: {e}")
            self._build_index()
    
    def _build_index(self):
        """Build TF-IDF index for all examples"""
        all_texts = []
        self.example_map = []
        
        for category, examples in self.examples.items():
            for example in examples:
                all_texts.append(example['input'])
                self.example_map.append({
                    'category': category,
                    'input': example['input'],
                    'output': example['output'],
                })
        
        if all_texts:
            self.tfidf_matrix = self.vectorizer.fit_transform(all_texts)
            logging.info(f"Built RAG index with {len(all_texts)} examples")
        else:
            self.tfidf_matrix = None
            logging.warning("No examples found for RAG index")
    
    def _save_index_cache(self, cache_file):
        """Save RAG index to cache"""
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump({
                    'vectorizer': self.vectorizer,
                    'tfidf_matrix': self.tfidf_matrix,
                    'example_map': self.example_map
                }, f)
            logging.info("Saved RAG index to cache")
        except Exception as e:
            logging.error(f"Error saving RAG cache: {e}")
    
    def find_similar_examples(self, query, language, intent_type='tasks', top_k=3):
        """Find similar examples using cosine similarity with improved matching"""
        if not hasattr(self, 'tfidf_matrix') or self.tfidf_matrix is None:
            return []
        
        # Filter by language and type
        valid_categories = []
        if intent_type == 'tasks':
            valid_categories = [f'tasks_{language}']
        elif intent_type == 'notes':
            valid_categories = [f'notes_{language}']
        else: # auto
            valid_categories = [f'tasks_{language}', f'notes_{language}']
        
        # Preprocess query - remove extra spaces and make lowercase for better matching
        processed_query = ' '.join(query.lower().split())
        
        # Transform query
        query_vec = self.vectorizer.transform([processed_query])
        
        # Calculate similarities
        similarities = cosine_similarity(query_vec, self.tfidf_matrix).flatten()
        
        # Get top matches from valid categories
        results = []
        for idx, similarity in enumerate(similarities):
            example_info = self.example_map[idx]
            if example_info['category'] in valid_categories:
                boosted_similarity = similarity
                
                # Boost for planning/complex queries
                if any(keyword in processed_query for keyword in ['plan', 'schedule', 'routine', 'complex', 'lectures', 'خطط', 'جدول', 'روتين', 'محاضرات']):
                    boosted_similarity += 0.3
                
                # Boost for task-related queries
                if any(keyword in processed_query for keyword in ['task', 'create', 'make', 'add', 'اعمل', 'أنشئ']):
                    boosted_similarity += 0.2
                
                # Boost for time-related queries  
                if any(keyword in processed_query for keyword in ['tomorrow', '10am', '2pm', 'time', 'hour', 'غدا', 'ساعة', 'مساء']):
                    boosted_similarity += 0.1
                
                results.append({
                    'similarity': min(boosted_similarity, 1.0),  # Cap at 1.0
                    'input': example_info['input'],
                    'output': example_info['output'],
                    'category': example_info['category']
                })
        
        # Sort by similarity and return top k
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:top_k]
        
    def get_fallback_response(self, user_message, language):
        """Enhanced fallback response using RAG"""
        # Auto-detect intent for fallback
        if any(word in user_message.lower() for word in ['note', 'write', 'اكتب', 'ملاحظة']):
            intent_type = 'notes'
        else:
            intent_type = 'tasks'

        similar_examples = self.find_similar_examples(user_message, language, intent_type, 3)
        
        logging.info(f"RAG Fallback - User message: '{user_message}'")
        logging.info(f"RAG Fallback - Language: {language}")
        logging.info(f"RAG Fallback - Found {len(similar_examples)} similar examples")
        
        for i, example in enumerate(similar_examples):
            logging.info(f"RAG Example {i+1}: Similarity={example['similarity']:.3f}, Input='{example['input']}'")
        
        if similar_examples and similar_examples[0]['similarity'] > 0.2:
            logging.info("Using RAG-based fallback with good match")
            result = similar_examples[0]['output']
            
            # Add natural response message
            task_count = len(result.get('tasks', []))
            note_count = len(result.get('notes', []))
            
            if language == 'ar':
                if note_count > 0:
                     result['response_message'] = f"تم إنشاء {note_count} ملاحظات بناءً على طلبك."
                else:
                     result['response_message'] = f"تم إنشاء {task_count} مهام بناءً على طلبك."
            else:
                if note_count > 0:
                    result['response_message'] = f"Created {note_count} notes based on your request."
                else:
                    result['response_message'] = f"Created {task_count} tasks based on your request."
            
            return result
        
        # Ultimate fallback
        logging.info("Using ultimate fallback - no good matches found")
        return self._create_ultimate_fallback(user_message, language)

    def _create_ultimate_fallback(self, user_message, language):
        """Create ultimate fallback when nothing else works"""
        if language == 'ar':
            return {
                "response_message": "أفهم أنك تريد مساعدتي. يمكنني إنشاء مهام أو ملاحظات بناءً على طلبك. هل يمكنك إعادة صياغة طلبك؟",
                "tasks": [],
                "notes": [],
                "suggestions": [
                    "جرب صياغة طلبك بشكل مختلف",
                    "أخبرني بما تريد بالضبط أن أفعله",
                    "استخدم أمثلة مثل 'أنشئ مهمة للدراسة'"
                ]
            }
        else:
            return {
                "response_message": "I understand you need assistance. I can create tasks or notes based on your request. Could you rephrase what you'd like me to do?",
                "tasks": [],
                "notes": [],
                "suggestions": [
                    "Try rephrasing your request",
                    "Tell me exactly what you want me to create",
                    "Use examples like 'create a study task'"
                ]
            }