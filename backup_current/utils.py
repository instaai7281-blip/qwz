import os
import time
import logging
from typing import Dict, List, Any

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Admin Configuration
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_STR.split(",") if x.strip()]

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def truncate(text: str, max_len: int) -> str:
    if not text:
        return ""
    return text[:max_len-3] + "..." if len(text) > max_len else text

def detect_language(text: str) -> str:
    hindi_range = (0x0900, 0x097F)
    gujarati_range = (0x0A80, 0x0AFF)
    for char in text:
        cp = ord(char)
        if hindi_range[0] <= cp <= hindi_range[1]: return "hindi"
        if gujarati_range[0] <= cp <= gujarati_range[1]: return "gujarati"
    return "english"

def format_poll(quiz_item: Dict[str, Any]) -> Dict[str, Any]:
    question = truncate(quiz_item.get("question", "No question text"), 300)
    options = [truncate(opt, 100) for opt in quiz_item.get("options", ["A", "B", "C", "D"])[:10]]
    correct_index = quiz_item.get("correct_index", 0)
    explanation = truncate(quiz_item.get("explanation", ""), 200)
    if correct_index >= len(options): correct_index = 0
    return {
        "question": question,
        "options": options,
        "correct_option_id": correct_index,
        "explanation": explanation,
        "type": "quiz",
        "is_anonymous": True
    }

class RateLimiter:
    def __init__(self, max_requests: int = 3, interval_seconds: int = 600):
        self.max_requests = max_requests
        self.interval_seconds = interval_seconds
        self.user_history: Dict[int, List[float]] = {}

    def is_rate_limited(self, user_id: int) -> bool:
        if is_admin(user_id): return False
        now = time.time()
        if user_id not in self.user_history:
            self.user_history[user_id] = [now]
            return False
        self.user_history[user_id] = [ts for ts in self.user_history[user_id] if now - ts < self.interval_seconds]
        if len(self.user_history[user_id]) < self.max_requests:
            self.user_history[user_id].append(now)
            return False
        return True

    def get_remaining_time(self, user_id: int) -> int:
        if user_id not in self.user_history or not self.user_history[user_id]: return 0
        now = time.time()
        oldest_ts = self.user_history[user_id][0]
        return max(0, int(self.interval_seconds - (now - oldest_ts)))
