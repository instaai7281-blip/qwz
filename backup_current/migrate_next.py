import asyncio
import os
from bot import quiz_gen, migrator
import db
from utils import format_poll
from telegram import Bot

# Configuration
SOURCE_CHANNEL = "daily_current_affairs_quiz_hindi"
START_ID = 13341
COUNT = 5
TARGET_CHANNEL = "-1002639135025"
BOT_TOKEN = os.getenv("BOT_TOKEN")

async def main():
    await db.init_db()
    bot = Bot(token=BOT_TOKEN)
    
    print(f"Starting migration of {COUNT} quizzes from {SOURCE_CHANNEL} starting at {START_ID}...")
    
    link = f"https://t.me/{SOURCE_CHANNEL}/{START_ID}"
    
    try:
        quizzes = await migrator.migrate_batch(link, COUNT)
        print(f"Found {len(quizzes)} quizzes.")
        
        for i, q in enumerate(quizzes):
            serial = await db.get_next_serial(TARGET_CHANNEL)
            q_with_serial = q.copy()
            q_with_serial['question'] = f"Q.{serial} | {q['question']}"
            
            poll_data = format_poll(q_with_serial)
            # We don't have a bot_data mapping here but it's okay for a script
            await bot.send_poll(chat_id=TARGET_CHANNEL, **poll_data)
            await db.save_quiz(TARGET_CHANNEL, "migrated", q['question'], q['correct_index'])
            
            print(f"Posted Q.{serial} ({i+1}/{len(quizzes)})")
            await asyncio.sleep(2)
            
        print("Migration complete!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
