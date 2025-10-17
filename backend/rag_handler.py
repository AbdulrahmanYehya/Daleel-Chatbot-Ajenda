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
        self.context_weights = self._initialize_context_weights()
    
    def _load_examples(self):
        try:
            from rag_examples import RAG_EXAMPLES
            print(f"✅ Loaded {sum(len(examples) for examples in RAG_EXAMPLES.values())} RAG examples")
            return RAG_EXAMPLES
        except ImportError:
            print("❌ Could not load RAG examples file")
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
            if category == 'context_aware':
                continue  # Skip context-aware for main index
                
            for example in examples:
                all_texts.append(example['input'])
                self.example_map.append({
                    'category': category,
                    'input': example['input'],
                    'output': example['output'],
                    'context': example.get('context', {})
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
    
    def _initialize_context_weights(self):
        """Initialize weights for different context factors"""
        return {
            'recent_topics': 0.3,
            'user_preferences': 0.25,
            'time_of_day': 0.15,
            'day_of_week': 0.1,
            'historical_patterns': 0.2
        }
    
    def get_contextual_prompt(self, user_message, language, conversation_context):
        """Create context-aware guided prompt"""
        # Find similar examples considering context
        similar_examples = self.find_contextual_examples(user_message, language, conversation_context, top_k=2)
        
        if not similar_examples:
            return self.get_guided_prompt(user_message, language)
        
        # Build context-aware prompt
        prompt_parts = []
        prompt_parts.append("Based on the current context and similar situations, here are relevant examples:\n")
        
        for i, example in enumerate(similar_examples, 1):
            prompt_parts.append(f"Context Example {i}:")
            if example.get('context'):
                prompt_parts.append(f"Context: {json.dumps(example['context'], ensure_ascii=False)}")
            prompt_parts.append(f"User: {example['input']}")
            prompt_parts.append(f"Assistant: {json.dumps(example['output'], ensure_ascii=False)}")
            prompt_parts.append("")
        
        prompt_parts.append(f"Current context: {json.dumps(conversation_context, ensure_ascii=False)}")
        prompt_parts.append(f"Now respond to this user message considering the context:")
        prompt_parts.append(f"User: {user_message}")
        prompt_parts.append("Assistant:")
        
        return "\n".join(prompt_parts)
    
    def find_contextual_examples(self, query, language, context, top_k=3):
        """Find examples considering conversation context"""
        if not hasattr(self, 'tfidf_matrix') or self.tfidf_matrix is None:
            return []
        
        # Filter by language
        valid_categories = [f'tasks_{language}', f'notes_{language}']
        
        # Transform query
        query_vec = self.vectorizer.transform([query])
        
        # Calculate base similarities
        similarities = cosine_similarity(query_vec, self.tfidf_matrix).flatten()
        
        # Apply context weighting
        weighted_results = []
        for idx, similarity in enumerate(similarities):
            example_info = self.example_map[idx]
            if example_info['category'] in valid_categories:
                context_similarity = self._calculate_context_similarity(context, example_info.get('context', {}))
                weighted_similarity = similarity * 0.7 + context_similarity * 0.3
                
                weighted_results.append({
                    'similarity': weighted_similarity,
                    'input': example_info['input'],
                    'output': example_info['output'],
                    'context': example_info.get('context', {}),
                    'category': example_info['category']
                })
        
        # Sort by weighted similarity and return top k
        weighted_results.sort(key=lambda x: x['similarity'], reverse=True)
        return weighted_results[:top_k]
    
    def _calculate_context_similarity(self, current_context, example_context):
        """Calculate similarity between current and example contexts"""
        if not current_context or not example_context:
            return 0.5  # Neutral similarity
        
        common_keys = set(current_context.keys()) & set(example_context.keys())
        if not common_keys:
            return 0.3  # Low similarity
        
        matches = 0
        for key in common_keys:
            if current_context[key] == example_context[key]:
                matches += 1
        
        return matches / len(common_keys)
    
    def get_guided_prompt(self, user_message, language, intent_type='auto'):
        """Create guided prompt with similar examples"""
        # Auto-detect intent
        if intent_type == 'auto':
            if any(word in user_message.lower() for word in ['research', 'note', 'write', 'ابحث', 'اكتب', 'ملاحظة', 'study', 'دراسة']):
                intent_type = 'notes'
            else:
                intent_type = 'tasks'
        
        # Find similar examples
        similar_examples = self.find_similar_examples(user_message, language, intent_type, top_k=2)
        
        if not similar_examples:
            return None
        
        # Build guided prompt
        prompt_parts = []
        prompt_parts.append("Here are similar examples to guide your response:\n")
        
        for i, example in enumerate(similar_examples, 1):
            prompt_parts.append(f"Example {i}:")
            prompt_parts.append(f"User: {example['input']}")
            prompt_parts.append(f"Assistant: {json.dumps(example['output'], ensure_ascii=False)}")
            prompt_parts.append("")
        
        prompt_parts.append(f"Now respond to this user message in the same JSON format:")
        prompt_parts.append(f"User: {user_message}")
        prompt_parts.append("Assistant:")
        
        return "\n".join(prompt_parts)
    
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
        else:
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
                # SIGNIFICANTLY BOOST similarity for complex queries with multiple items
                boosted_similarity = similarity
                
                # Boost for meeting-related queries
                if any(keyword in processed_query for keyword in ['meeting', 'meetings', 'team', 'client', 'call', 'schedule']):
                    boosted_similarity += 0.3  # Big boost for meeting-related
                
                # Boost for task-related queries
                if any(keyword in processed_query for keyword in ['task', 'create', 'make', 'add', 'schedule']):
                    boosted_similarity += 0.2
                
                # Boost for time-related queries  
                if any(keyword in processed_query for keyword in ['tomorrow', '10am', '2pm', 'time', 'hour']):
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
        # Try to find similar examples for fallback
        similar_examples = self.find_similar_examples(user_message, language, 'auto', 3)  # Get top 3
        
        # ADD DEBUG LOGGING
        logging.info(f"RAG Fallback - User message: '{user_message}'")
        logging.info(f"RAG Fallback - Language: {language}")
        logging.info(f"RAG Fallback - Found {len(similar_examples)} similar examples")
        
        for i, example in enumerate(similar_examples):
            logging.info(f"RAG Example {i+1}: Similarity={example['similarity']:.3f}, Input='{example['input']}'")
        
        if similar_examples and similar_examples[0]['similarity'] > 0.2:  # Lowered threshold from 0.4
            logging.info("Using RAG-based fallback with good match")
            result = similar_examples[0]['output']
            # Add natural response message
            task_count = len(result.get('tasks', []))
            note_count = len(result.get('notes', []))
            
            if language == 'ar':
                result['response_message'] = f"تم إنشاء {task_count} مهام و {note_count} ملاحظات بناءً على طلبك."
            else:
                result['response_message'] = f"Created {task_count} tasks and {note_count} notes based on your request."
            
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