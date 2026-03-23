import re
from collections import Counter
import PyPDF2
import logging
import io
try:
    import docx # Requires: pip install python-docx
except ImportError:
    logging.warning("python-docx not installed. Word documents will fail.")

class DocumentProcessor:
    """Handles extracting raw text from uploaded files (PDF, TXT, DOCX)."""
    
    @staticmethod
    def extract_text_from_file(file):
        try:
            text_content = ""
            file_extension = file.filename.lower()
            
            # Wrap in BytesIO to ensure stream compatibility for binary files
            file_bytes = file.read()
            file_stream = io.BytesIO(file_bytes)
            
            if file_extension.endswith('.pdf'):
                pdf_reader = PyPDF2.PdfReader(file_stream)
                for page in pdf_reader.pages:
                    extract = page.extract_text()
                    if extract:
                        text_content += extract + "\n"
                        
            elif file_extension.endswith('.docx'):
                doc = docx.Document(file_stream)
                text_content = "\n".join([para.text for para in doc.paragraphs])
                        
            elif file_extension.endswith('.txt'):
                text_content = file_bytes.decode('utf-8')
            
            # Reset the original file pointer just in case Flask needs it
            file.seek(0)
            return text_content.strip()
            
        except Exception as e:
            logging.error(f"Error extracting text from file: {e}", exc_info=True)
            return None

class LocalSummarizer:
    """Handles mathematical summarization of text (Offline Backup Model)."""
    def __init__(self):
        self.stop_words = set(['the', 'is', 'in', 'and', 'to', 'a', 'of', 'for', 'on', 'with', 'as', 'by', 'an', 'this', 'that', 'في', 'من', 'على', 'إلى', 'عن', 'ب', 'ل', 'أن', 'هذا', 'هذه'])

    def summarize(self, text, num_sentences=3):
        if not text or len(text.strip()) == 0: return "", "Untitled"
        sentences = re.split(r'(?<=[.!?]) +|(?<=[.!?\n])', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
        if len(sentences) <= num_sentences: return text, self.extract_title(sentences[0])
        
        word_freq = Counter()
        for sent in sentences:
            words = re.findall(r'\w+', sent.lower())
            for w in words:
                if w not in self.stop_words: word_freq[w] += 1
                
        if not word_freq: return text, self.extract_title(sentences[0])
        max_freq = max(word_freq.values())
        sent_scores = {}
        
        for sent in sentences:
            score = 0
            sent_words = re.findall(r'\w+', sent.lower())
            if not sent_words: continue
            for w in sent_words:
                if w in word_freq: score += word_freq[w] / max_freq
            if len(sent_words) < 4 or len(sent_words) > 30: score *= 0.5
            sent_scores[sent] = score

        sorted_sents = sorted(sent_scores, key=sent_scores.get, reverse=True)[:num_sentences]
        final_summary = [s for s in sentences if s in sorted_sents]
        summary_text = ' '.join(final_summary)
        return summary_text, self.extract_title(sentences[0])

    def extract_title(self, first_sentence):
        clean_sent = first_sentence.strip()
        words = clean_sent.split()
        if len(words) <= 6: return clean_sent.replace('.', '')
        return ' '.join(words[:6]) + "..."