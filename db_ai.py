import logging
import os
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from typing import List, Dict, Any, Optional

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "quiz_bot")

client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]

async def init_db():
    """Initializes MongoDB collections and indexes."""
    logger.info("Initializing MongoDB...")
    # Users collection
    await db.users.create_index("user_id", unique=True)
    # Channels collection
    await db.channels.create_index("channel_id", unique=True)
    # Monitored channels
    await db.monitored_channels.create_index("username", unique=True)
    # Quiz history
    await db.quiz_history.create_index([("channel_id", 1), ("topic", 1)])
    logger.info("MongoDB initialized successfully.")

async def add_monitored_channel(username: str, target_chat_id: str):
    username = username.strip().replace("@", "").replace("https://t.me/", "")
    await db.monitored_channels.update_one(
        {"username": username},
        {"$set": {"target_chat_id": target_chat_id, "active": 1}},
        upsert=True
    )

async def get_active_monitored_channels():
    cursor = db.monitored_channels.find({"active": 1})
    results = []
    async for doc in cursor:
        results.append((doc['username'], doc['target_chat_id'], doc.get('last_msg_id', 0)))
    return results

async def update_last_msg_id(username: str, last_msg_id: int):
    await db.monitored_channels.update_one(
        {"username": username},
        {"$set": {"last_msg_id": last_msg_id}}
    )

async def remove_monitored_channel(username: str):
    username = username.strip().replace("@", "").replace("https://t.me/", "")
    await db.monitored_channels.delete_one({"username": username})

async def add_user(user_id: int, username: str):
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"username": username}, "$setOnInsert": {"score": 0, "correct": 0, "total": 0, "joined_at": datetime.now()}},
        upsert=True
    )

async def update_score(user_id: int, is_correct: bool):
    inc = {"total": 1}
    if is_correct:
        inc["score"] = 10
        inc["correct"] = 1
    await db.users.update_one({"user_id": user_id}, {"$inc": inc})

async def get_leaderboard(limit: int = 10):
    cursor = db.users.find().sort("score", -1).limit(limit)
    results = []
    async for doc in cursor:
        results.append((doc.get('username', 'Unknown'), doc.get('score', 0), doc.get('correct', 0), doc.get('total', 0)))
    return results

async def get_stats(user_id: int):
    doc = await db.users.find_one({"user_id": user_id})
    if doc:
        # Calculate rank
        rank = await db.users.count_documents({"score": {"$gt": doc.get('score', 0)}}) + 1
        return {
            "score": doc.get('score', 0),
            "correct": doc.get('correct', 0),
            "total": doc.get('total', 0),
            "rank": rank
        }
    return None

async def add_channel(channel_id: str, channel_name: str, added_by: int):
    await db.channels.update_one(
        {"channel_id": channel_id},
        {"$set": {"channel_name": channel_name, "added_by": added_by, "active": 1}},
        upsert=True
    )

async def get_channels():
    cursor = db.channels.find()
    results = []
    async for doc in cursor:
        results.append((doc['channel_id'], doc['channel_name'], doc.get('active', 1)))
    return results

async def add_schedule(channel_id: str, topic: str, frequency: str, next_run: datetime):
    res = await db.schedules.insert_one({
        "channel_id": channel_id,
        "topic": topic,
        "frequency": frequency,
        "next_run": next_run,
        "active": 1
    })
    return str(res.inserted_id)

async def get_schedules():
    cursor = db.schedules.find({"active": 1})
    results = []
    async for doc in cursor:
        # Convert to tuple for compatibility with existing code
        results.append((str(doc['_id']), doc['channel_id'], doc['topic'], doc['frequency'], doc['next_run'], doc['active']))
    return results

async def remove_schedule(schedule_id: str):
    from bson.objectid import ObjectId
    await db.schedules.update_one({"_id": ObjectId(schedule_id)}, {"$set": {"active": 0}})

async def save_quiz(channel_id: str, topic: str, question: str, correct_index: int):
    await db.quiz_history.insert_one({
        "channel_id": channel_id,
        "topic": topic,
        "question": question,
        "correct_index": correct_index,
        "timestamp": datetime.now()
    })

async def get_next_serial(channel_id: str):
    count = await db.quiz_history.count_documents({"channel_id": channel_id})
    return count + 1
