from dotenv import load_dotenv
load_dotenv(override=True)

import logging
import os
import asyncio
import re
from typing import Dict

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    Poll, 
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    BotCommand
)
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    ContextTypes, 
    CallbackQueryHandler, 
    PollAnswerHandler,
    MessageHandler,
    filters
)

import db
from quiz_generator import QuizGenerator, TOPICS
from utils import RateLimiter, is_admin, format_poll, detect_language, truncate
import scheduler
from migrate_service import Migrator
from monitor_service import MonitorService
from pdf_service import PDFService

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constants
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# Initialize AI and Services
quiz_gen = QuizGenerator()
rate_limiter = RateLimiter()
migrator = Migrator(quiz_gen)
monitor = MonitorService(migrator)
pdf_service = PDFService(quiz_gen)

# --- Keyboards ---

def get_main_menu_keyboard(user_id):
    keyboard = [
        [KeyboardButton("📚 Available Topics"), KeyboardButton("📊 My Statistics")],
        [KeyboardButton("🏆 Leaderboard"), KeyboardButton("❓ Help & About")]
    ]
    if is_admin(user_id):
        keyboard.append([KeyboardButton("⚙️ Admin Panel")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_keyboard():
    keyboard = [
        [KeyboardButton("📢 List Channels"), KeyboardButton("📅 View Schedules")],
        [KeyboardButton("➕ Add Channel"), KeyboardButton("🚀 Migrate Quizzes")],
        [KeyboardButton("🏠 Back to Main Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        await db.add_user(user.id, user.username or user.first_name)
    except Exception as e:
        logger.error(f"DB Error in start: {e}")

    welcome_text = (
        f"👋 *Welcome {user.first_name} to the Quiz Master AI!* 🚀\n\n"
        "I am your premium AI-powered assistant for GPSC, UPSC, SSC, and Banking exams.\n\n"
        "✨ *Features:*\n"
        "• High-quality MCQ quizzes\n"
        "• Real-time stats and leaderboard\n"
        "• Automated channel posting\n"
        "• Bilingual support (English & Gujarati/Hindi)\n\n"
        "👇 *Use the menu below to navigate!*"
    )
    
    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard(user.id)
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if text == "📚 Available Topics":
        await show_topics(update, context)
    elif text == "📊 My Statistics":
        await stats_command(update, context)
    elif text == "🏆 Leaderboard":
        await leaderboard_command(update, context)
    elif text == "❓ Help & About":
        await help_command(update, context)
    elif text == "⚙️ Admin Panel":
        if is_admin(user_id):
            await update.message.reply_text("🛠️ *Admin Control Panel*", parse_mode="Markdown", reply_markup=get_admin_keyboard())
        else:
            await update.message.reply_text("❌ Access denied.")
    elif text == "📢 List Channels":
        await list_channels(update, context)
    elif text == "➕ Add Channel":
        if is_admin(user_id):
            await update.message.reply_text(
                "➕ *Add a New Channel*\n\n"
                "Please use the command below to link a channel:\n"
                "`/setchannel <ID/Link> <Name>`\n\n"
                "Example:\n`/setchannel -1002639135025 My Channel`",
                parse_mode="Markdown"
            )
    elif text == "📅 View Schedules":
        await list_schedules(update, context)
    elif text == "🚀 Migrate Quizzes":
        if is_admin(user_id):
            await update.message.reply_text(
                "🚀 *Migration Tool*\n\n"
                "Send the starting quiz link and number of quizzes to migrate.\n\n"
                "Format: `/migrate <link> <count>`\n"
                "Example: `/migrate https://t.me/channel/12345 10`",
                parse_mode="Markdown"
            )
    elif text == "🏠 Back to Main Menu":
        await update.message.reply_text("🏠 Returning to Main Menu...", reply_markup=get_main_menu_keyboard(user_id))
    else:
        # Check if it looks like a link for migration
        if is_admin(user_id) and "t.me/" in text:
            parts = text.split()
            if len(parts) >= 1:
                link = parts[0]
                count = int(parts[1]) if len(parts) > 1 else 5
                context.args = [link, str(count)]
                await migrate_command(update, context)
        else:
            await update.message.reply_text("🤖 Please use the buttons below to interact with me!")

async def show_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_text = "📚 *Select a topic to generate a quiz:*"
    keyboard = []
    topics_list = list(TOPICS.items())
    for i in range(0, len(topics_list), 2):
        row = []
        key1, name1 = topics_list[i]
        row.append(InlineKeyboardButton(name1.split(' ')[0], callback_data=f"gen_topic_{key1}"))
        if i + 1 < len(topics_list):
            key2, name2 = topics_list[i+1]
            row.append(InlineKeyboardButton(name2.split(' ')[0], callback_data=f"gen_topic_{key2}"))
        keyboard.append(row)
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(msg_text, parse_mode="Markdown", reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg_text, parse_mode="Markdown", reply_markup=reply_markup)

async def topic_gen_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    topic = query.data.replace("gen_topic_", "")
    context.args = [topic, "medium", "5"]
    await generate_command(update, context)

async def generate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    is_callback = update.callback_query is not None
    msg = update.callback_query.message if is_callback else update.message

    if rate_limiter.is_rate_limited(user_id):
        wait_time = rate_limiter.get_remaining_time(user_id)
        return await msg.reply_text(f"⏳ *Rate Limited!* wait {wait_time}s", parse_mode="Markdown")

    if not args:
        return await msg.reply_text("❌ Usage: `/generate <topic>`", parse_mode="Markdown")

    topic = args[0]
    num = int(args[2]) if len(args) > 2 else 5
    topic_display = TOPICS.get(topic, topic)
    status_msg = await msg.reply_text(f"⚙️ *AI is thinking...*\nGenerating {num} questions on *{topic_display}*...", parse_mode="Markdown")

    try:
        questions = await quiz_gen.generate_quiz(topic, "medium", num, "bilingual")
        context.user_data['temp_quiz'] = questions
        context.user_data['temp_topic'] = topic
        preview_text = f"✅ *Success!*\nGenerated {len(questions)} questions on *{topic_display}*."
        keyboard = []
        if is_admin(user_id):
            channels = await db.get_channels()
            for ch_id, ch_name, active in channels:
                if active:
                    keyboard.append([InlineKeyboardButton(f"🚀 Post to {ch_name}", callback_data=f"post_to_{ch_id}")])
        keyboard.append([InlineKeyboardButton("❌ Dismiss", callback_data="cancel_gen")])
        await status_msg.edit_text(preview_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"Generation error: {e}")
        await status_msg.edit_text("❌ *AI Generation Failed*")

async def migrate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /migrate <link> <count>"""
    if not is_admin(update.effective_user.id): return
    args = context.args
    if len(args) < 1:
        return await update.message.reply_text("❌ Usage: `/migrate <telegram_link> [count]`")

    link = args[0]
    count = int(args[1]) if len(args) > 1 else 5
    count = min(count, 30) # Max 30 at a time

    status_msg = await update.message.reply_text(f"🔍 *Scanning for quizzes...*\nLink: `{link}`", parse_mode="Markdown")

    async def progress_callback(found, searched):
        if searched % 3 == 0:
            try:
                await status_msg.edit_text(f"🔍 *Scanning...*\nDetected: `{found}/{count}` quizzes\nChecked: `{searched}` messages", parse_mode="Markdown")
            except: pass

    try:
        quizzes = await migrator.migrate_batch(link, count, progress_callback)
        if not quizzes:
            return await status_msg.edit_text("❌ No quizzes found. Make sure the link is correct and contains public polls.")

        context.user_data['temp_quiz'] = quizzes
        context.user_data['temp_topic'] = "migrated"
        
        preview_text = (
            f"✅ *Extraction Complete!*\n\n"
            f"📊 Found: `{len(quizzes)}` Quizzes\n"
            f"🤖 AI Answer Detection: Active\n\n"
            "Would you like to post these quizzes to your channel?"
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ Yes, Post them now", callback_data="confirm_migration")],
            [InlineKeyboardButton("❌ No, Cancel", callback_data="cancel_gen")]
        ]
        
        await status_msg.edit_text(preview_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"Migration error: {e}")
        await status_msg.edit_text(f"❌ *Migration Failed*\nError: {str(e)}")

async def confirm_migration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    channels = await db.get_channels()
    if not channels:
        return await query.edit_message_text("❌ No channels found. Use `/setchannel` first.")
    
    keyboard = []
    for ch_id, ch_name, active in channels:
        if active:
            keyboard.append([InlineKeyboardButton(f"📤 Post to {ch_name}", callback_data=f"post_to_{ch_id}")])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_gen")])
    
    await query.edit_message_text("📍 *Select target channel:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    stats = await db.get_stats(user_id)
    if not stats: text = "❌ *No data found.*"
    else:
        acc = (stats['correct'] / stats['total'] * 100) if stats['total'] > 0 else 0
        text = f"📊 *Stats*\n🏅 Rank: `#{stats['rank']}`\n✨ Score: `{stats['score']}`"
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lb = await db.get_leaderboard()
    text = "🏆 *Leaderboard*\n\n"
    for i, (name, score, correct, total) in enumerate(lb):
        text += f"{i+1}. *{name}*: `{score}` pts\n"
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")

async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    channels = await db.get_channels()
    text = "📢 *Channels:*\n\n"
    for ch_id, ch_name, active in channels: text += f"• `{ch_id}` - {ch_name}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def list_schedules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    schedules = await db.get_schedules()
    text = "📅 *Schedules:*\n\n"
    for sch in schedules: text += f"• `{sch[1]}`: {sch[2]}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def set_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /setchannel <ID or Link> <Name>"""
    if not is_admin(update.effective_user.id): return
    args = context.args
    
    if len(args) < 2:
        help_text = (
            "❌ *Usage Error*\n\n"
            "Format: `/setchannel <ID/Link> <Name>`\n\n"
            "💡 *Examples:*\n"
            "• `/setchannel -1002639135025 My Study Group` (Private ID)\n"
            "• `/setchannel @MyPublicChannel Current Affairs` (Public Username)\n"
            "• `/setchannel https://t.me/MyChannel News Feed` (Link)"
        )
        return await update.message.reply_text(help_text, parse_mode="Markdown")

    raw_id = args[0]
    ch_name = " ".join(args[1:])
    
    # Try to extract ID/Username from link if provided
    if "t.me/" in raw_id:
        # Public link: https://t.me/username -> @username
        # Private link: https://t.me/c/123456789/1 -> -100123456789
        if "/c/" in raw_id:
            match = re.search(r'/c/(\d+)', raw_id)
            if match:
                raw_id = f"-100{match.group(1)}"
        else:
            match = re.search(r't\.me/([^/]+)', raw_id)
            if match:
                raw_id = f"@{match.group(1)}"

    # Validate numeric IDs (ensure they start with -100 for channels)
    if raw_id.isdigit():
        raw_id = f"-100{raw_id}"
    elif raw_id.startswith("-") and raw_id[1:].isdigit() and not raw_id.startswith("-100"):
        # If it's a negative number but not -100, might be a group, let's keep it but warn? 
        # Actually, most channels are -100.
        pass

    try:
        await db.add_channel(raw_id, ch_name, update.effective_user.id)
        await update.message.reply_text(
            f"✅ *Channel Saved!*\n\n"
            f"📍 *ID:* `{raw_id}`\n"
            f"🏷️ *Name:* {ch_name}\n\n"
            "I can now post quizzes to this channel.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error in set_channel: {e}")
        await update.message.reply_text(f"❌ Failed to save channel: {str(e)}")

async def post_to_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Prevent double clicks
    if context.user_data.get('is_posting'):
        return
    context.user_data['is_posting'] = True
    
    channel_id = query.data.replace("post_to_", "")
    questions = context.user_data.get('temp_quiz')
    if not questions: return
    
    total = len(questions)
    topic = context.user_data.get('temp_topic', 'migrated')
    
    for i, q in enumerate(questions):
        # Get next serial number for this channel
        serial = await db.get_next_serial(channel_id)
        
        try:
            await query.edit_message_text(
                f"🚀 *Live Posting Update*\n\n"
                f"📍 Channel: `{channel_id}`\n"
                f"🔢 Serial: `Q.{serial}`\n"
                f"📊 Progress: `{i+1}/{total}` Quizzes\n\n"
                f"⏳ *Status:* Posting quiz...",
                parse_mode="Markdown"
            )
        except Exception: pass 
        
        # Add serial number to the question text
        q_with_serial = q.copy()
        q_with_serial['question'] = f"Q.{serial} | {q['question']}"
        
        poll_data = format_poll(q_with_serial)
        await send_poll_tracked(context.bot, chat_id=channel_id, **poll_data)
        await db.save_quiz(channel_id, topic, q['question'], q['correct_index'])
        
        await asyncio.sleep(2)
        
    await query.edit_message_text(
        f"✅ *Posting Complete!*\n\n"
        f"🏁 Successfully posted `{total}` quizzes to `{channel_id}`.",
        parse_mode="Markdown"
    )
    context.user_data.pop('temp_quiz', None)
    context.user_data['is_posting'] = False

async def cancel_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Cancelled.")
    context.user_data.pop('temp_quiz', None)

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll_mapping = context.bot_data.get("poll_mapping", {})
    if answer.poll_id in poll_mapping:
        is_correct = poll_mapping[answer.poll_id] in answer.option_ids
        await db.update_score(answer.user.id, is_correct)

async def send_poll_tracked(bot, *args, **kwargs):
    poll = await bot.send_poll(*args, **kwargs)
    if poll.poll.type == "quiz":
        mapping = bot.bot_data.get("poll_mapping", {})
        mapping[poll.poll.id] = poll.poll.correct_option_id
        bot.bot_data["poll_mapping"] = mapping
    return poll

async def post_init(application):
    await db.init_db()
    await scheduler.start_scheduler(application.bot)
    
    # Pass bot instance to monitor service
    monitor.bot = application.bot
    # Start monitor loop
    asyncio.create_task(monitor.start_loop())
    logger.info("Auto-Monitor loop started.")
    
    # Set public commands (visible to everyone)
    commands = [
        BotCommand("start", "🚀 Start the bot & Main Menu"),
        BotCommand("stats", "📊 View my quiz statistics"),
        BotCommand("leaderboard", "🏆 View top rankers"),
        BotCommand("migrate", "📦 Migrate quizzes from link"),
        BotCommand("monitor", "📡 Setup auto-monitoring"),
        BotCommand("monitors", "📋 List active monitors"),
        BotCommand("stop_monitor", "🛑 Stop auto-monitoring"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands registered automatically.")

async def monitor_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to add a channel to auto-monitor."""
    if not is_admin(update.effective_user.id): return
    
    if not context.args:
        await update.message.reply_text(
            "❌ *Usage:* `/monitor <channel_link>`\n\n"
            "Example: `/monitor https://t.me/QUIZPANEL`",
            parse_mode="Markdown"
        )
        return
        
    link = context.args[0]
    # Extract username
    username = link.strip().replace("@", "").replace("https://t.me/", "").split("/")[0]
    
    # Get first channel from DB as target
    channels = await db.get_channels()
    if not channels:
        await update.message.reply_text("❌ Please add a target channel first using `/setchannel`.")
        return
    target_chat_id = channels[0][0]

    await db.add_monitored_channel(username, target_chat_id)
    
    # Get latest ID to start from now (so we don't post old history)
    latest_id = await monitor.get_latest_id(username)
    await db.update_last_msg_id(username, latest_id)
    
    await update.message.reply_text(
        f"📡 *Auto-Monitor Setup Complete!*\n\n"
        f"📍 *Source:* `@{username}`\n"
        f"🎯 *Target:* `{target_chat_id}`\n"
        f"🔢 *Starting from ID:* `{latest_id}`\n\n"
        f"The bot will check this channel every 10 minutes and auto-post any new quizzes found.",
        parse_mode="Markdown"
    )

async def stop_monitor_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to stop monitoring a channel."""
    if not is_admin(update.effective_user.id): return
    
    if not context.args:
        await update.message.reply_text("Usage: `/stop_monitor <channel_username>`", parse_mode="Markdown")
        return
        
    source = context.args[0]
    await db.remove_monitored_channel(source)
    await update.message.reply_text(f"🛑 *Monitoring Stopped* for `{source}`.", parse_mode="Markdown")

async def monitors_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all active monitors."""
    if not is_admin(update.effective_user.id): return
    
    monitors = await db.get_active_monitored_channels()
    if not monitors:
        await update.message.reply_text("ℹ️ No active monitors found.")
        return
        
    text = "📡 *Active Channel Monitors:*\n\n"
    for m in monitors:
        text += f"🔹 `@{m[0]}` ➔ `{m[1]}` (Last ID: {m[2]})\n"
        
    await update.message.reply_text(text, parse_mode="Markdown")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles PDF uploads to generate quizzes."""
    doc = update.message.document
    if doc.mime_type != 'application/pdf':
        await update.message.reply_text("❌ Please send a PDF file.")
        return
        
    msg = await update.message.reply_text("⏳ *Extracting text from PDF...*", parse_mode="Markdown")
    
    file = await context.bot.get_file(doc.file_id)
    file_path = f"temp_{doc.file_id}.pdf"
    await file.download_to_drive(file_path)
    
    try:
        text = pdf_service.extract_text(file_path)
        if not text.strip():
            await msg.edit_text("❌ Could not extract any text from this PDF.")
            return
            
        await msg.edit_text("🧠 *AI is generating quizzes from your PDF...*", parse_mode="Markdown")
        quizzes = await pdf_service.generate_quizzes_from_text(text, count=10)
        
        if not quizzes:
            await msg.edit_text("❌ Failed to generate quizzes. The text might be too complex or too short.")
            return
            
        context.user_data['temp_quiz'] = quizzes
        
        keyboard = [
            [InlineKeyboardButton("✅ Yes, Post them now", callback_data="confirm_migration")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_gen")]
        ]
        
        await msg.edit_text(
            f"✅ *Successfully extracted {len(quizzes)} quizzes!*\n\n"
            "Would you like to post them to your channel?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"PDF processing failed: {e}")
        await msg.edit_text(f"❌ Error processing PDF: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

def main():
    if not BOT_TOKEN: return
    application = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("generate", generate_command))
    application.add_handler(CommandHandler("migrate", migrate_command))
    application.add_handler(CommandHandler("monitor", monitor_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("leaderboard", leaderboard_command))
    application.add_handler(CommandHandler("setchannel", set_channel))
    application.add_handler(CommandHandler("channels", list_channels))
    application.add_handler(CommandHandler("schedules", list_schedules))
    application.add_handler(CallbackQueryHandler(topic_gen_callback, pattern="^gen_topic_"))
    application.add_handler(CallbackQueryHandler(confirm_migration_callback, pattern="^confirm_migration$"))
    application.add_handler(CallbackQueryHandler(post_to_channel_callback, pattern="^post_to_"))
    application.add_handler(CallbackQueryHandler(cancel_gen, pattern="^cancel_gen$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    application.add_handler(PollAnswerHandler(handle_poll_answer))
    application.run_polling()

if __name__ == "__main__":
    main()
