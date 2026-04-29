import fitz  # PyMuPDF
import logging
from typing import List, Dict, Any
from quiz_generator import QuizGenerator

logger = logging.getLogger(__name__)

class PDFService:
    def __init__(self, quiz_gen: QuizGenerator):
        self.quiz_gen = quiz_gen

    def extract_text(self, file_path: str) -> str:
        """Extracts text from a PDF file."""
        text = ""
        try:
            doc = fitz.open(file_path)
            for page in doc:
                text += page.get_text()
            doc.close()
        except Exception as e:
            logger.error(f"Failed to extract text from PDF: {e}")
        return text

    async def generate_quizzes_from_text(self, text: str, count: int = 10) -> List[Dict[str, Any]]:
        """Uses AI to extract MCQs from raw text (Supports Hindi, Gujarati, English)."""
        # Clean text a bit to avoid token limits
        sample_text = text[:8000] # Take first 8000 chars for now
        
        prompt = (
            "Task: Extract exactly {count} Multiple Choice Questions (MCQs) from the provided text.\n"
            "Language Support: The text may contain Hindi, Gujarati, or English. Preserve the original script and language for the question and options.\n\n"
            "Format: Return a JSON object with a 'quizzes' list.\n"
            "Each quiz must have:\n"
            "- 'question': The question text in its original language.\n"
            "- 'options': List of 4 options in their original language.\n"
            "- 'correct_index': 0-based index of correct answer.\n"
            "- 'explanation': A brief explanation in the same language as the question.\n\n"
            "Text Content:\n{text}\n\n"
            "Return ONLY the JSON object."
        ).format(count=count, text=sample_text)
        
        try:
            quizzes = await self.quiz_gen._call_groq_with_retry(prompt)
            return quizzes
        except Exception as e:
            logger.error(f"Failed to generate quizzes from PDF text: {e}")
            return []
