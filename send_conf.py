import asyncio
from telegram import Bot

BOT_TOKEN = "8053658721:AAE85g1ewKAqzs0QDWzhPO51dZlvW9sIn8A"
USER_ID = "6947378236"

async def main():
    bot = Bot(token=BOT_TOKEN)
    await bot.send_message(
        chat_id=USER_ID,
        text="🚀 *Bot is now LIVE and Fully Responsive!*\n\nI have updated your bot with a premium Main Menu and bilingual support. Check it out by typing /start!",
        parse_mode="Markdown"
    )
    print("Confirmation message sent to owner.")

if __name__ == "__main__":
    asyncio.run(main())
