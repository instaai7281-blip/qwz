import asyncio
from telegram import Bot

BOT_TOKEN = "8053658721:AAE85g1ewKAqzs0QDWzhPO51dZlvW9sIn8A"
USER_ID = "6947378236"

async def main():
    bot = Bot(token=BOT_TOKEN)
    await bot.send_message(
        chat_id=USER_ID,
        text="✨ *Migration Feature Added!*\n\nI have added a powerful migration tool to your Admin Panel.\n\n🛠️ *How to use:*\n1. Go to **Admin Panel**.\n2. Click **🚀 Migrate Quizzes**.\n3. Send the link and count (e.g., `/migrate https://t.me/channel/123 10`).\n\nI will extract the quizzes and use AI to automatically detect the correct answers for you! 🤖",
        parse_mode="Markdown"
    )
    print("Migration confirmation sent.")

if __name__ == "__main__":
    asyncio.run(main())
