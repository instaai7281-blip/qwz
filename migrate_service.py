import asyncio
import re
import logging
from typing import List, Dict, Any
from pyrogram import Client, filters
from pyrogram.enums import PollType
from quiz_generator import QuizGenerator

logger = logging.getLogger(__name__)

class Migrator:
    def __init__(self, app: Client, ai_db: Any, quiz_gen: QuizGenerator):
        self.app = app
        self.ai_db = ai_db
        self.quiz_gen = quiz_gen

    async def migrate_channel(self, source_chat: str, target_chat: str, limit: int = 10):
        """Migrates quizzes from source channel to target channel with AI enhancements."""
        count = 0
        async for message in self.app.get_chat_history(source_chat, limit=limit * 2): # Look a bit further
            if count >= limit:
                break
                
            if message.poll:
                # 1. Extract details
                question = message.poll.question
                options = [opt.text for opt in message.poll.options]
                
                # 2. Get correct index using AI (if not accessible)
                # Note: For public polls, we often don't know the correct answer unless we vote.
                # AI can guess the correct one.
                correct_idx = await self.get_correct_answer_ai(question, options)
                
                # 3. Generate explanation
                explanation = await self.get_explanation_ai(question, options, correct_idx)
                
                # 4. Post to target
                try:
                    await self.app.send_poll(
                        chat_id=target_chat,
                        question=question,
                        options=options,
                        is_anonymous=True,
                        type=PollType.QUIZ,
                        correct_option_id=correct_idx,
                        explanation=f"📝 {explanation}\n\n@Quiz_Masterx"
                    )
                    count += 1
                    await asyncio.sleep(2) # Avoid flood
                except Exception as e:
                    logger.error(f"Failed to post migrated poll: {e}")
                    
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
