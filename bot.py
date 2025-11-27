import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, ConversationHandler, filters
)
from stream_manager import StreamManager, Stream
from utils import get_system_stats

# ------------------------------------------------------------------
# Conversation states
M3U8, RTMP_URL, STREAM_KEY, TITLE, OVERLAY, CONFIRM = range(6)

# ------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
manager = StreamManager()
BOT_START_TIME = asyncio.get_event_loop().time()

TOKEN = "7454188408:AAGnFnyFGDNk2l7NhyhSmoS5BYz0R82ZOTU"

# ------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎥 *TGTV Stream Bot*\n\n"
        "Push any HLS (m3u8) to any RTMP destination.\n"
        "Use /help for commands.",
        parse_mode="Markdown"
    )
    await update.message.reply_text("/help")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "/start - Welcome message\n"
        "/help - This list\n"
        "/ping - Bot & VPS stats\n"
        "/streaminfo - List active streams\n"
        "/stream - Start a new stream"
    )
    await update.message.reply_text(txt)

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime_bot = asyncio.get_event_loop().time() - BOT_START_TIME
    h, rem = divmod(int(uptime_bot), 3600)
    m, s = divmod(rem, 60)
    bot_up = f"{h:02}h {m:02}m {s:02}s"
    stats = await get_system_stats()
    await update.message.reply_text(f"Bot uptime: {bot_up}\n\n{stats}")

# ------------------------------------------------------------------
# Stream creation conversation
async def stream_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("📡 M3U8", callback_data="type_m3u8")]]
    await update.message.reply_text(
        "Choose input type (only M3U8 for now):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return M3U8

async def type_m3u8(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Send the *M3U8 URL*:", parse_mode="Markdown")
    return M3U8

async def get_m3u8(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["m3u8"] = update.message.text.strip()
    await update.message.reply_text("Send the *RTMP base URL* (e.g. rtmp://a.rtmp.youtube.com/live2):", parse_mode="Markdown")
    return RTMP_URL

async def get_rtmp_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["rtmp_url"] = update.message.text.strip()
    await update.message.reply_text("Send the *Stream Key*:", parse_mode="Markdown")
    return STREAM_KEY

async def get_stream_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["stream_key"] = update.message.text.strip()
    await update.message.reply_text("Send the *Stream Title*:", parse_mode="Markdown")
    return TITLE

async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["title"] = update.message.text.strip()
    keyboard = [
        [InlineKeyboardButton("Yes", callback_data="overlay_yes")],
        [InlineKeyboardButton("No", callback_data="overlay_no")]
    ]
    await update.message.reply_text(
        "Overlay logo on top-right?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return OVERLAY

async def overlay_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data.split("_")[1]
    context.user_data["overlay"] = (choice == "yes")

    # Build final RTMP URL
    rtmp = f"{context.user_data['rtmp_url']}/{context.user_data['stream_key']}"
    context.user_data["final_rtmp"] = rtmp

    keyboard = [[InlineKeyboardButton("Start Stream", callback_data="confirm_start")]]
    await query.edit_message_text(
        f"**Ready to start**\n\n"
        f"Title: {context.user_data['title']}\n"
        f"Overlay: {'Yes' if context.user_data['overlay'] else 'No'}\n"
        f"RTMP: {rtmp}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CONFIRM

async def confirm_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    sid = manager.new_id()
    stream = Stream(
        stream_id=sid,
        m3u8=context.user_data["m3u8"],
        rtmp_url=context.user_data["final_rtmp"],
        title=context.user_data["title"],
        overlay=context.user_data["overlay"]
    )
    manager.add(stream)
    await stream.start()

    await query.edit_message_text(f"Stream **{sid}** started!")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

# ------------------------------------------------------------------
async def streaminfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    streams = manager.all()
    if not streams:
        await update.message.reply_text("No active streams.")
        return

    for s in streams:
        keyboard = [
            [InlineKeyboardButton("Screenshot", callback_data=f"ss_{s.id}")],
            [InlineKeyboardButton("Stop Stream", callback_data=f"stop_{s.id}")]
        ]
        text = (
            f"**Stream {s.id}**\n"
            f"Title: {s.title}\n"
            f"Uptime: {s.uptime()}\n"
            f"Overlay: {'Yes' if s.overlay else 'No'}"
        )
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("ss_"):
        sid = data[3:]
        stream = manager.get(sid)
        if not stream:
            await query.edit_message_text("Stream not found.")
            return
        photo = await stream.get_screenshot()
        if photo:
            await query.message.reply_photo(photo, caption=f"Screenshot – {sid}")
        else:
            await query.edit_message_text("Failed to capture screenshot.")
        return

    if data.startswith("stop_"):
        sid = data[5:]
        stream = manager.get(sid)
        if not stream:
            await query.edit_message_text("Stream not found.")
            return
        await stream.stop()
        manager.remove(sid)
        await query.edit_message_text(f"Stream **{sid}** stopped.")
        return

# ------------------------------------------------------------------
def main():
    app = Application.builder().token(TOKEN).build()

    # /stream conversation
    conv = ConversationHandler(
        entry_points=[CommandHandler("stream", stream_entry)],
        states={
            M3U8: [
                CallbackQueryHandler(type_m3u8, pattern="^type_m3u8$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_m3u8)
            ],
            RTMP_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_rtmp_url)],
            STREAM_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_stream_key)],
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_title)],
            OVERLAY: [CallbackQueryHandler(overlay_choice, pattern="^overlay_")],
            CONFIRM: [CallbackQueryHandler(confirm_start, pattern="^confirm_start$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("streaminfo", streaminfo))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
