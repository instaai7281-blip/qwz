import os
import json
import logging
import re
from typing import List, Dict, Any
from groq import Groq
from openai import OpenAI

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOPICS = {
    "gk_india": "General Knowledge India",
    "gujarat_history": "Gujarat History & Culture", 
    "gujarat_polity": "Gujarat Polity & Administration",
    "indian_polity": "Indian Constitution & Polity",
    "current_affairs": "Most Recent Current Affairs India (National & International)",
    "reasoning": "Logical Reasoning",
    "maths_basic": "Basic Mathematics",
    "science_gk": "General Science",
    "gujarati_grammar": "Gujarati Grammar & Literature",
    "economy": "Indian Economy"
}

class QuizGenerator:
    def __init__(self):
        self.groq_key = os.getenv("GROQ_API_KEY")
        self.nvidia_key = os.getenv("NVIDIA_API_KEY")
        
        if self.groq_key:
            self.groq_client = Groq(api_key=self.groq_key)
        else:
            logger.warning("GROQ_API_KEY not found.")
            
        if self.nvidia_key:
            self.nvidia_client = OpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=self.nvidia_key
            )
        else:
            logger.error("NVIDIA_API_KEY not found.")

        self.groq_model = "llama-3.3-70b-versatile"
        self.nvidia_model = "meta/llama-3.1-70b-instruct"

    async def generate_quiz(self, topic: str, difficulty: str, num_questions: int, language: str) -> List[Dict[str, Any]]:
        from datetime import datetime
        current_date_str = datetime.now().strftime("%B %d, %Y")
        topic_name = TOPICS.get(topic, topic)
        
        use_nvidia = (topic == "current_affairs" and self.nvidia_key) or not self.groq_key
        
        provider_name = "NVIDIA" if use_nvidia else "Groq"
        logger.info(f"Generating quiz for {topic} using {provider_name}")

        prompt = (
            f"You are an expert quiz maker for Indian government exams (GPSC, UPSC, SSC, Banking). "
            f"Today's date is {current_date_str}. Generate {num_questions} MCQ questions on topic: {topic_name}. Difficulty: {difficulty}. Language: {language}.\n"
            f"CRITICAL: If the topic is 'Current Affairs', generate questions based on the MOST RECENT news from the last 24-48 hours. Focus on major appointments, government schemes, awards, international summits, and key events in India.\n\n"
            "INSTRUCTION FOR LANGUAGES:\n"
            "If the language is 'bilingual', you MUST provide the question, options, and explanation in BOTH English and Gujarati.\n"
            "Format for bilingual:\n"
            "Question: [English Question]\\n\\n[Gujarati Question]\n"
            "Options: [English Option] | [Gujarati Option]\n"
            "Explanation: 📝 [English Explanation]\\n\\n📙 [Gujarati Explanation]\\n\\n"
            "CRITICAL FORMATTING & ACCURACY:\n"
            "1. 'correct_index' MUST BE the 0-based index of the correct option. (0 for 1st, 1 for 2nd, etc.)\n"
            "2. Ensure the answer is factually 100% CORRECT.\n"
            "3. ALWAYS add TWO newlines (\\n\\n) between English and Gujarati text.\n"
            "4. The explanation MUST end with: @Quiz_Masterx\n\n"
            "JSON SCHEMA:\n"
            '[{"question": "...", "options": ["...", "...", "...", "..."], "correct_index": 0, "explanation": "..."}]\n\n'
            "Return ONLY the JSON array."
        )

        try:
            if use_nvidia:
                return await self._call_nvidia(prompt)
            else:
                return await self._call_groq_with_retry(prompt)
        except Exception as e:
            logger.error(f"Failed to generate quiz via {provider_name}: {e}")
            raise

    async def _call_nvidia(self, prompt: str) -> List[Dict[str, Any]]:
        response = self.nvidia_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=self.nvidia_model,
            temperature=0.7,
        )
        text = response.choices[0].message.content
        clean_json = self._extract_json(text)
        data = json.loads(clean_json)
        return data if isinstance(data, list) else data.get("quizzes", [])

    async def _call_groq_with_retry(self, prompt: str, retry_count: int = 1) -> List[Dict[str, Any]]:
        for attempt in range(retry_count + 1):
            try:
                response = self.groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=self.groq_model,
                    temperature=0.7,
                )
                text = response.choices[0].message.content
                clean_json = self._extract_json(text)
                data = json.loads(clean_json)
                return data if isinstance(data, list) else data.get("quizzes", [])
            except Exception as e:
                if attempt == retry_count: raise
        return []

    def _extract_json(self, text: str) -> str:
        match = re.search(r'(\[.*\]|\{.*\})', text, re.DOTALL)
        return match.group(0) if match else text
