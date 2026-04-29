import logging
import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot
import db
from quiz_generator import QuizGenerator
from utils import format_poll

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
generator = QuizGenerator()

async def post_scheduled_quiz(bot: Bot, channel_id: str, topic: str):
    logger.info(f"Triggered scheduled quiz for {channel_id} on {topic}")
    try:
        questions = await generator.generate_quiz(topic, "medium", 5, "english")
        for q in questions:
            poll_data = format_poll(q)
            await bot.send_poll(chat_id=channel_id, **poll_data)
            await db.save_quiz(channel_id, topic, q['question'], q['correct_index'])
            await asyncio.sleep(3)
    except Exception as e:
        logger.error(f"Error posting scheduled quiz: {e}")

async def start_scheduler(bot: Bot):
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started.")
    schedules = await db.get_schedules()
    for sch in schedules:
        sch_id, channel_id, topic, freq, _, _ = sch
        add_scheduler_job(bot, sch_id, channel_id, topic, freq)

def add_scheduler_job(bot: Bot, sch_id: int, channel_id: str, topic: str, frequency: str):
    trigger = None
    if frequency == "hourly": trigger = CronTrigger(minute=0)
    elif frequency == "daily": trigger = CronTrigger(hour=9, minute=0)
    elif frequency == "weekly": trigger = CronTrigger(day_of_week='mon', hour=9, minute=0)
    if trigger:
        scheduler.add_job(
            post_scheduled_quiz,
            trigger=trigger,
            args=[bot, channel_id, topic],
            id=str(sch_id),
            replace_existing=True
        )
        logger.info(f"Added job {sch_id} for {channel_id} ({frequency})")

async def add_new_schedule(bot: Bot, channel_id: str, topic: str, frequency: str):
    next_run = datetime.now()
    sch_id = await db.add_schedule(channel_id, topic, frequency, next_run)
    add_scheduler_job(bot, sch_id, channel_id, topic, frequency)
    return sch_id

async def remove_schedule(sch_id: int):
    try:
        scheduler.remove_job(str(sch_id))
    except: pass
    await db.remove_schedule(sch_id)
    logger.info(f"Removed schedule {sch_id}")
