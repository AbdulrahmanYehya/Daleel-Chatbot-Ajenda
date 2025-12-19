import re
from collections import Counter
import PyPDF2
import logging
import io

class DocumentProcessor:
    """Handles extracting raw text from uploaded files (PDF, TXT)."""
    
    @staticmethod
    def extract_text_from_file(file):
        try:
            text_content = ""
            
            # Check file extension
            if file.filename.lower().endswith('.pdf'):
                # Handle PDF files
                # Wrap in BytesIO to ensure stream compatibility
                file_stream = io.BytesIO(file.read())
                pdf_reader = PyPDF2.PdfReader(file_stream)
                
                for page in pdf_reader.pages:
                    extract = page.extract_text()
                    if extract:
                        text_content += extract + "\n"
                        
            elif file.filename.lower().endswith('.txt'):
                # Handle Text files
                # Reset pointer just in case, though file.read() moves it
                file.seek(0)
                text_content = file.read().decode('utf-8')
            
            return text_content.strip()
            
        except Exception as e:
            logging.error(f"Error extracting text from file: {e}")
            return None

class LocalSummarizer:
    """Handles mathematical summarization of text (No AI Model required)."""
    
    def __init__(self):
        # Common stop words to ignore during frequency analysis
        self.stop_words = set(['the', 'is', 'at', 'which', 'on', 'and', 'a', 'of', 'for', 'it', 'with', 'as', 'in'])

    def summarize(self, text, num_sentences=3):
        """
        Summarizes text by finding the most significant sentences 
        based on word frequency.
        """
        if not text: return "", "Untitled"
        
        # 1. Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        if len(sentences) <= num_sentences: 
            return text, self.extract_title(text)

        # 2. Calculate Word Frequency
        words = re.findall(r'\w+', text.lower())
        words = [w for w in words if w not in self.stop_words and len(w) > 2]
        word_freq = Counter(words)
        
        if not word_freq: return text, "Untitled"
        
        max_freq = max(word_freq.values())

        # 3. Score Sentences
        sent_scores = {}
        for sent in sentences:
            score = 0
            sent_words = re.findall(r'\w+', sent.lower())
            
            if not sent_words: continue
            
            for w in sent_words:
                if w in word_freq:
                    # Normalize score by max frequency
                    score += word_freq[w] / max_freq
            
            # Penalize very short sentences (often headers or fragments) 
            # and very long sentences (hard to read)
            if len(sent_words) < 4 or len(sent_words) > 30:
                score *= 0.5
                
            sent_scores[sent] = score

        # 4. Pick Top N Sentences
        # Sort by score descending
        sorted_sents = sorted(sent_scores, key=sent_scores.get, reverse=True)[:num_sentences]
        
        # Reorder the selected sentences as they appeared in original text for natural flow
        final_summary = [s for s in sentences if s in sorted_sents]
        summary_text = ' '.join(final_summary)
        
        return summary_text, self.extract_title(sentences[0])

    def extract_title(self, first_sentence):
        """
        Generates a title from the first sentence or first few words.
        """
        # Cleanup
        clean_sent = first_sentence.strip()
        words = clean_sent.split()
        
        # If sentence is short, use it as title
        if len(words) <= 6:
            return clean_sent
            
        # Otherwise truncate
        return ' '.join(words[:5]).title() + "..."