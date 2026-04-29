import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

logging.basicConfig(level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello!")

if __name__ == '__main__':
    application = ApplicationBuilder().token("8053658721:AAE85g1ewKAqzs0QDWzhPO51dZlvW9sIn8A").build()
    application.add_handler(CommandHandler('start', start))
    print("Running...")
    application.run_polling()
