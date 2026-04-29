import fitz  # PyMuPDF
import logging
import re
from typing import List, Dict, Any
from quiz_generator import QuizGenerator

logger = logging.getLogger(__name__)

class PDFService:
    def __init__(self, quiz_gen: QuizGenerator):
        self.quiz_gen = quiz_gen

    def extract_text(self, file_path: str) -> str:
        """Extracts text from a PDF file with layout awareness."""
        text = ""
        try:
            doc = fitz.open(file_path)
            for page in doc:
                # Using "blocks" to better handle multi-column layouts often found in exam papers
                blocks = page.get_text("blocks")
                for b in blocks:
                    text += b[4] + "\n"
            doc.close()
        except Exception as e:
            logger.error(f"Failed to extract text from PDF: {e}")
        
        # Basic cleaning for Hindi/Gujarati scripts to remove weird artifacts
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\xff]', '', text) 
        return text.strip()

    async def generate_quizzes_from_text(self, text: str, count: int = 10) -> Dict[str, Any]:
        """Uses AI to extract MCQs from raw text (Enhanced support for Hindi & Gujarati)."""
        # Clean text a bit to avoid token limits
        sample_text = text[:10000] # Increased limit for better context
        
        prompt = (
            "Task: Extract exactly {count} Multiple Choice Questions (MCQs) from the provided text.\n"
            "CRITICAL: The text likely contains questions in Hindi or Gujarati. "
            "You MUST preserve the script perfectly. Do NOT translate to English unless the original text is in English.\n\n"
            "Format: Return a JSON object with a 'quizzes' list.\n"
            "Each quiz must have:\n"
            "- 'question': The full question text in its original language (Hindi/Gujarati/English).\n"
            "- 'options': Exactly 4 options in their original language.\n"
            "- 'correct_index': 0-based index of the correct answer.\n"
            "- 'explanation': A short explanation in the SAME language as the question.\n\n"
            "Text Content:\n{text}\n\n"
            "Return ONLY the JSON object. If you cannot find {count} questions, extract as many as possible."
        ).format(count=count, text=sample_text)
        
        try:
            quizzes = await self.quiz_gen._call_groq_with_retry(prompt)
            # Ensure it's a dict
            if isinstance(quizzes, list):
                return {"quizzes": quizzes}
            return quizzes
        except Exception as e:
            logger.error(f"Failed to generate quizzes from PDF text: {e}")
            return {"quizzes": []}
