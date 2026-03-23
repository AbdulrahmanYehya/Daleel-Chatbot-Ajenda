import json
import re
import hashlib
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import os
import pickle
from datetime import datetime
import logging
from sentence_transformers import SentenceTransformer


class EnhancedRAGHandler:
    def __init__(self):
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.examples = self._load_examples()
        self._build_or_load_index()

    def _load_examples(self):
        try:
            from rag_examples import RAG_EXAMPLES
            # Remove 'Research' category notes
            for key in ['notes_ar', 'notes_en']:
                if key in RAG_EXAMPLES:
                    RAG_EXAMPLES[key] = [
                        ex for ex in RAG_EXAMPLES[key]
                        if ex.get('output', {}).get('notes', [{}])[0].get('category') != 'Research'
                    ]
            logging.info(f"Loaded RAG examples.")
            return RAG_EXAMPLES
        except ImportError:
            logging.error("Could not import rag_examples.py")
            return {}

    def _get_examples_hash(self) -> str:
        """Hash the examples dict so we can detect when examples change and invalidate cache."""
        try:
            content = json.dumps(self.examples, sort_keys=True, ensure_ascii=False)
            return hashlib.md5(content.encode()).hexdigest()
        except Exception:
            return "unknown"

    def _build_or_load_index(self):
        """Load cached embeddings if they exist and are valid; otherwise rebuild."""
        cache_file = 'rag_index_cache.pkl'
        current_hash = self._get_examples_hash()

        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'rb') as f:
                    cache_data = pickle.load(f)

                # FIX 1: Validate all required keys exist
                # FIX 2: Check hash to invalidate stale cache when examples change
                if (all(k in cache_data for k in ('embeddings', 'example_map', 'all_texts', 'examples_hash'))
                        and cache_data['examples_hash'] == current_hash):
                    self.embeddings = cache_data['embeddings']
                    self.example_map = cache_data['example_map']
                    self.all_texts = cache_data['all_texts']
                    logging.info("Loaded RAG index from cache.")
                    return
                else:
                    logging.info("Cache is stale or corrupt — rebuilding.")
        except Exception as e:
            logging.warning(f"Cache load failed: {e}")

        # FIX 3: Always delete the old cache file before rebuilding
        try:
            if os.path.exists(cache_file):
                os.remove(cache_file)
                logging.info("Deleted stale/corrupt cache file.")
        except OSError as e:
            logging.warning(f"Could not delete cache file: {e}")

        self._build_index()
        self._save_index_cache(cache_file, current_hash)

    def _build_index(self):
        self.all_texts = []
        self.example_map = []

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
            self.embeddings = self.model.encode(self.all_texts)
            logging.info("RAG index built successfully.")
        else:
            self.embeddings = None
            logging.warning("No examples found for RAG index.")

    def _save_index_cache(self, cache_file, examples_hash):
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump({
                    'embeddings': self.embeddings,
                    'example_map': self.example_map,
                    'all_texts': self.all_texts,
                    'examples_hash': examples_hash,  # FIX: store hash for invalidation
                }, f)
            logging.info("Saved RAG index to cache.")
        except Exception as e:
            logging.error(f"Error saving RAG cache: {e}")

    def find_similar_examples(self, query, language, intent_type='tasks', top_k=3):
        if self.embeddings is None:
            return []

        valid_categories = []
        if intent_type == 'tasks':
            valid_categories = [f'tasks_{language}']
        elif intent_type == 'notes':
            valid_categories = [f'notes_{language}']
        else:
            valid_categories = [f'tasks_{language}', f'notes_{language}']

        query_vec = self.model.encode([query])
        similarities = cosine_similarity(query_vec, self.embeddings)[0]

        results = []
        for idx, score in enumerate(similarities):
            if self.example_map[idx]['category'] in valid_categories:
                results.append({
                    'similarity': float(score),
                    'input': self.example_map[idx]['input'],
                    'output': self.example_map[idx]['output'],
                    'category': self.example_map[idx]['category']
                })

        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:top_k]

    # FIX: Renamed from process_query to get_fallback_response (was mismatched with ai_handler call)
    def get_fallback_response(self, user_message, language):
        """Primary entry point for the offline RAG fallback."""
        if any(word in user_message.lower() for word in ['note', 'write', 'save', 'اكتب', 'ملاحظة', 'احفظ']):
            intent_type = 'notes'
        else:
            intent_type = 'tasks'

        similar_examples = self.find_similar_examples(user_message, language, intent_type, 3)

        if similar_examples and similar_examples[0]['similarity'] > 0.4:
            logging.info(f"RAG match: '{similar_examples[0]['input']}' ({similar_examples[0]['similarity']:.2f})")
            result = similar_examples[0]['output'].copy()

            task_count = len(result.get('tasks', []))
            note_count = len(result.get('notes', []))

            if language == 'ar':
                msg = f"تم إنشاء {note_count} ملاحظات" if note_count > 0 else f"تم إنشاء {task_count} مهام"
                result['response_message'] = msg + " بناءً على طلبك."
            else:
                msg = f"Created {note_count} notes" if note_count > 0 else f"Created {task_count} tasks"
                result['response_message'] = msg + " based on your request. (Offline Mode)"

            return result

        return self._create_ultimate_fallback(user_message, language)

    def _create_ultimate_fallback(self, user_message, language):
        if language == 'ar':
            return {
                "response_message": "لم أتمكن من فهم طلبك بدقة. هل يمكنك إعادة صياغته؟",
                "tasks": [], "notes": [], "suggestions": ["أنشئ مهمة للدراسة", "اكتب ملاحظة"]
            }
        return {
            "response_message": "I couldn't quite understand that. Could you rephrase? (Offline Mode)",
            "tasks": [], "notes": [], "suggestions": ["Create a study task", "Write a note"]
        }