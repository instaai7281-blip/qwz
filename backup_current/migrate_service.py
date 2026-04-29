import httpx
from bs4 import BeautifulSoup
import asyncio
import re
import logging
from typing import List, Dict, Any
from quiz_generator import QuizGenerator

logger = logging.getLogger(__name__)

class Migrator:
    def __init__(self, quiz_gen: QuizGenerator):
        self.quiz_gen = quiz_gen

    async def fetch_message(self, channel: str, msg_id: int):
        url = f"https://t.me/{channel}/{msg_id}?embed=1"
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, timeout=10)
                if resp.status_code == 200:
                    return resp.text
            except Exception as e:
                logger.error(f"Failed to fetch {url}: {e}")
        return None

    def parse_poll(self, html: str, msg_id: int):
        if not html: return None
        soup = BeautifulSoup(html, 'html.parser')
        
        # Look for poll question
        poll_question_elem = soup.select_one('.tgme_widget_message_poll_question')
        message_text_elem = soup.select_one('.tgme_widget_message_text')
        
        question = ""
        if poll_question_elem:
            question = poll_question_elem.get_text(strip=True)
        elif message_text_elem:
            question = message_text_elem.get_text(strip=True)
            
        if not question: return None
            
        options = []
        for opt in soup.select('.tgme_widget_message_poll_option_text'):
            options.append(opt.get_text(strip=True))
            
        if not options: return None
            
        # Try to detect correct index if marked (rare in web embed)
        correct_index = 0
        correct_elem = soup.select_one('.tgme_widget_message_poll_option_correct')
        if correct_elem:
            for i, opt in enumerate(soup.select('.tgme_widget_message_poll_option')):
                if 'tgme_widget_message_poll_option_correct' in opt.get('class', []):
                    correct_index = i
                    break

        return {
            "msg_id": msg_id,
            "question": question,
            "options": options,
            "correct_index": correct_index,
            "explanation": "✨ Sources: External Channel | @Quiz_Masterx"
        }

    async def get_correct_answer_ai(self, question: str, options: List[str]) -> int:
        """Uses AI to determine the correct answer from options."""
        prompt = (
            "Task: Identify the correct option index (0-based) for the MCQ below.\n\n"
            f"Question: {question}\n"
            f"Options:\n" + "\n".join([f"{i}. {opt}" for i, opt in enumerate(options)]) +
            "\n\nInstructions:\n"
            "1. Analyze the question carefully.\n"
            "2. Determine the factually correct answer.\n"
            "3. Return ONLY the integer index (e.g., 0, 1, 2, or 3).\n"
            "4. Do NOT provide any text other than the digit."
        )
        try:
            resp = self.quiz_gen.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.quiz_gen.groq_model,
                temperature=0,
            )
            text = resp.choices[0].message.content.strip()
            match = re.search(r'\d+', text)
            if match:
                idx = int(match.group(0))
                if 0 <= idx < len(options):
                    return idx
        except Exception as e:
            logger.error(f"AI answer detection failed: {e}")
        return 0

    async def get_explanation_ai(self, question: str, options: List[str], correct_idx: int) -> str:
        """Uses AI to generate a brief explanation for the correct answer."""
        correct_answer = options[correct_idx]
        prompt = (
            f"Question: {question}\n"
            f"Correct Answer: {correct_answer}\n\n"
            "Provide a very brief (max 150 chars) professional explanation for why this is correct. "
            "Respond ONLY with the explanation text."
        )
        try:
            resp = self.quiz_gen.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.quiz_gen.groq_model,
                temperature=0.5,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"AI explanation generation failed: {e}")
            return f"The correct answer is {correct_answer}."

    async def migrate_batch(self, link: str, count: int, callback=None):
        """Extracts and prepares a batch of quizzes."""
        match = re.search(r't\.me/([^/]+)/(\d+)', link)
        if not match:
            raise ValueError("Invalid Telegram message link.")
            
        channel = match.group(1)
        start_id = int(match.group(2))
        
        quizzes = []
        current_id = start_id
        searched = 0
        
        while len(quizzes) < count and searched < 200:
            if callback: await callback(len(quizzes), searched)
            
            html = await self.fetch_message(channel, current_id)
            poll = self.parse_poll(html, current_id)
            
            if poll:
                # 1. Detect correct index
                if poll['correct_index'] == 0:
                    poll['correct_index'] = await self.get_correct_answer_ai(poll['question'], poll['options'])
                
                # 2. Generate proper explanation
                explanation = await self.get_explanation_ai(poll['question'], poll['options'], poll['correct_index'])
                poll['explanation'] = f"📝 {explanation}\n\n✅ Correct: {poll['options'][poll['correct_index']]}\n\n@Quiz_Masterx"
                
                quizzes.append(poll)
                
            current_id += 1
            searched += 1
            await asyncio.sleep(1)
            
        return quizzes
