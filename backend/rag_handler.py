import json
import re
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import os
import pickle
from datetime import datetime
import logging
# UPGRADE: Using SentenceTransformer for semantic understanding
from sentence_transformers import SentenceTransformer

class EnhancedRAGHandler:
    def __init__(self):
        # Load a lightweight, high-performance semantic model
        # This model is small (~80MB) and runs fast on CPU
        self.model = SentenceTransformer('all-MiniLM-L6-v2') 
        self.examples = self._load_examples()
        self._build_or_load_index()
    
    def _load_examples(self):
        try:
            from rag_examples import RAG_EXAMPLES
            
            # Clean examples (Remove 'Research' category as requested previously)
            for key in ['notes_ar', 'notes_en']:
                if key in RAG_EXAMPLES:
                    RAG_EXAMPLES[key] = [
                        ex for ex in RAG_EXAMPLES[key] 
                        if ex.get('output', {}).get('notes', [{}])[0].get('category') != 'Research'
                    ]
            
            logging.info(f"✅ Loaded RAG examples")
            return RAG_EXAMPLES
        except ImportError:
            logging.error("❌ Could not load RAG examples file")
            return {}
    
    def _build_or_load_index(self):
        """Build or load precomputed RAG index (Semantic Embeddings)"""
        cache_file = 'rag_index_cache.pkl'
        
        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'rb') as f:
                    cache_data = pickle.load(f)
                    # Restore data from cache
                    self.embeddings = cache_data['embeddings']
                    self.example_map = cache_data['example_map']
                    self.all_texts = cache_data['all_texts']
                logging.info("Loaded RAG index from cache")
            else:
                self._build_index()
                self._save_index_cache(cache_file)
        except Exception as e:
            logging.error(f"Error loading RAG cache: {e}")
            self._build_index()
    
    def _build_index(self):
        """Builds the semantic index of all examples"""
        self.all_texts = []
        self.example_map = []
        
        # Flatten the examples dictionary into a list
        for category, examples in self.examples.items():
            for example in examples:
                self.all_texts.append(example['input'])
                self.example_map.append({
                    'category': category,
                    'input': example['input'],
                    'output': example['output'],
                })
        
        if self.all_texts:
            logging.info(f"Building semantic embeddings for {len(self.all_texts)} examples...")
            # This turns text into numbers (vectors)
            self.embeddings = self.model.encode(self.all_texts)
            logging.info("RAG Index built successfully.")
        else:
            self.embeddings = None
            logging.warning("No examples found for RAG index")

    def _save_index_cache(self, cache_file):
        """Save RAG index to cache to speed up next boot"""
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump({
                    'embeddings': self.embeddings,
                    'example_map': self.example_map,
                    'all_texts': self.all_texts
                }, f)
            logging.info("Saved RAG index to cache")
        except Exception as e:
            logging.error(f"Error saving RAG cache: {e}")
    
    def find_similar_examples(self, query, language, intent_type='tasks', top_k=3):
        """Finds examples with similar MEANING, not just keywords"""
        if self.embeddings is None:
            return []
        
        # Filter valid categories (e.g., only look at Arabic Tasks if language is 'ar')
        valid_categories = []
        if intent_type == 'tasks':
            valid_categories = [f'tasks_{language}']
        elif intent_type == 'notes':
            valid_categories = [f'notes_{language}']
        else:
            valid_categories = [f'tasks_{language}', f'notes_{language}']
        
        # Encode the user's query into a vector
        query_vec = self.model.encode([query])
        
        # Calculate semantic similarity
        similarities = cosine_similarity(query_vec, self.embeddings)[0]
        
        # Rank results
        results = []
        for idx, score in enumerate(similarities):
            example_info = self.example_map[idx]
            if example_info['category'] in valid_categories:
                results.append({
                    'similarity': float(score),
                    'input': example_info['input'],
                    'output': example_info['output'],
                    'category': example_info['category']
                })
        
        # Sort by highest score
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:top_k]
        
    def get_fallback_response(self, user_message, language):
        """Enhanced fallback using Semantic RAG"""
        # Quick check for note intent
        if any(word in user_message.lower() for word in ['note', 'write', 'اكتب', 'ملاحظة']):
            intent_type = 'notes'
        else:
            intent_type = 'tasks'

        similar_examples = self.find_similar_examples(user_message, language, intent_type, 3)
        
        # Higher threshold (0.4) because semantic search is more confident than keywords
        if similar_examples and similar_examples[0]['similarity'] > 0.4: 
            logging.info(f"RAG Match Found: {similar_examples[0]['input']} ({similar_examples[0]['similarity']:.2f})")
            result = similar_examples[0]['output']
            
            # Add dynamic response message
            task_count = len(result.get('tasks', []))
            note_count = len(result.get('notes', []))
            
            if language == 'ar':
                 msg = f"تم إنشاء {note_count} ملاحظات" if note_count > 0 else f"تم إنشاء {task_count} مهام"
                 result['response_message'] = msg + " بناءً على طلبك."
            else:
                 msg = f"Created {note_count} notes" if note_count > 0 else f"Created {task_count} tasks"
                 result['response_message'] = msg + " based on your request."
            
            return result
        
        return self._create_ultimate_fallback(user_message, language)

    def _create_ultimate_fallback(self, user_message, language):
        if language == 'ar':
            return {
                "response_message": "لم أتمكن من فهم طلبك بدقة. هل يمكنك إعادة صياغته؟",
                "tasks": [], "notes": [], "suggestions": ["أنشئ مهمة للدراسة", "اكتب ملاحظة"]
            }
        else:
            return {
                "response_message": "I couldn't quite understand that. Could you rephrase?",
                "tasks": [], "notes": [], "suggestions": ["Create a study task", "Write a note"]
            }