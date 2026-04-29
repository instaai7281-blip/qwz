import asyncio
import logging
import re
import httpx
from bs4 import BeautifulSoup
from typing import List, Dict, Any
from migrate_service import Migrator
import db
from utils import format_poll

logger = logging.getLogger(__name__)

class MonitorService:
    def __init__(self, migrator: Migrator, bot=None):
        self.migrator = migrator
        self.bot = bot
        self.is_running = False

    async def get_latest_id(self, channel: str) -> int:
        """Fetches the latest message ID from a channel's public preview page."""
        url = f"https://t.me/s/{channel}"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    return 0
                
                # Find all data-post attributes
                ids = re.findall(rf'{channel}/(\d+)', response.text)
                if ids:
                    return max(map(int, ids))
        except Exception as e:
            logger.error(f"Failed to get latest ID for {channel}: {e}")
        return 0

    async def scan_and_post(self):
        """Main loop to scan monitored channels."""
        if self.is_running: return
        self.is_running = True
        
        try:
            channels = await db.get_active_monitored_channels()
            for username, target_chat_id, last_id in channels:
                logger.info(f"Monitoring {username}... Current last_id: {last_id}")
                
                latest_id = await self.get_latest_id(username)
                if latest_id > last_id:
                    # Scan from last_id + 1 to latest_id
                    # Limit to 20 messages at a time to avoid flood
                    start = last_id + 1
                    end = min(latest_id, last_id + 20)
                    
                    for msg_id in range(start, end + 1):
                        html = await self.migrator.fetch_message(username, msg_id)
                        poll = self.migrator.parse_poll(html, msg_id)
                        
                        if poll:
                            logger.info(f"Detected new poll in {username} at {msg_id}")
                            # 1. Detect answer
                            poll['correct_index'] = await self.migrator.get_correct_answer_ai(poll['question'], poll['options'])
                            # 2. Generate explanation
                            explanation = await self.migrator.get_explanation_ai(poll['question'], poll['options'], poll['correct_index'])
                            poll['explanation'] = f"📝 {explanation}\n\n✅ Correct: {poll['options'][poll['correct_index']]}\n\n@Quiz_Masterx"
                            
                            # 3. Post to target
                            serial = await db.get_next_serial(target_chat_id)
                            poll['question'] = f"Q.{serial} | {poll['question']}"
                            
                            poll_data = format_poll(poll)
                            if self.bot:
                                try:
                                    await self.bot.send_poll(chat_id=target_chat_id, **poll_data)
                                    await db.save_quiz(target_chat_id, "monitored", poll['question'], poll['correct_index'])
                                    logger.info(f"Posted Q.{serial} to {target_chat_id}")
                                except Exception as e:
                                    logger.error(f"Failed to post poll: {e}")
                            
                            await asyncio.sleep(2)
                        
                    # Update last_id
                    await db.update_last_msg_id(username, end)
                
                await asyncio.sleep(5) # Delay between channels
                
        except Exception as e:
            logger.error(f"Monitor loop error: {e}")
        finally:
            self.is_running = False

    async def start_loop(self, interval: int = 600):
        """Runs the monitor loop every interval seconds."""
        logger.info("Starting Auto-Monitor loop...")
        while True:
            await self.scan_and_post()
            await asyncio.sleep(interval)
