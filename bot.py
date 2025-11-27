# bot.py
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
M3U8, RTMP_URL, STREAM_KEY, TITLE, OVERLAY, CONFIRM = range(6)

# ------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
manager = StreamManager()
BOT_START_TIME = asyncio.get_event_loop().time()

TOKEN = "7454188408:AAGnFnyFGDNk2l7NhyhSmoS5BYz0R82ZOTU"

# ------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*TGTV Stream Bot*\n\n"
        "Push any HLS (m3u8) stream to RTMP destinations.\n"
        "Use /help for commands.",
        parse_mode="Markdown"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start - Welcome message\n"
        "/help - This list\n"
        "/ping - Bot & VPS stats\n"
        "/streaminfo - View & manage active streams\n"
        "/stream - Start a new stream"
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime_bot = asyncio.get_event_loop().time() - BOT_START_TIME
    h, rem = divmod(int(uptime_bot), 3600)
    m, s = divmod(rem, 60)
    bot_up = f"{h:02}h {m:02}m {s:02}s"
    stats = await get_system_stats()
    await update.message.reply_text(f"Bot Uptime: `{bot_up}`\n\n{stats}", parse_mode="Markdown")

# ------------------------------------------------------------------
# Stream creation
async def stream_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Cancel any ongoing conversation
    if context.user_data:
        context.user_data.clear()

    keyboard = [[InlineKeyboardButton("M3U8", callback_data="type_m3u8")]]
    await update.message.reply_text(
        "Choose input type:",
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
    await update.message.reply_text("Send the *RTMP base URL* (e.g. `rtmp://a.rtmp.youtube.com/live2`):", parse_mode="Markdown")
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
    await update.message.reply_text("Overlay logo on top-right?", reply_markup=InlineKeyboardMarkup(keyboard))
    return OVERLAY

async def overlay_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data.split("_")[1]
    context.user_data["overlay"] = (choice == "yes")

    rtmp = f"{context.user_data['rtmp_url'].rstrip('/')}/{context.user_data['stream_key']}"
    context.user_data["final_rtmp"] = rtmp

    keyboard = [[InlineKeyboardButton("Start Stream", callback_data="confirm_start")]]
    await query.edit_message_text(
        f"*Ready to Start*\n\n"
        f"Title: `{context.user_data['title']}`\n"
        f"Overlay: `{'Yes' if context.user_data['overlay'] else 'No'}`\n"
        f"RTMP: `{rtmp}`\n\n"
        f"Click below to begin streaming.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CONFIRM

async def confirm_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    m3u8 = context.user_data["m3u8"]
    rtmp_base = context.user_data["rtmp_url"]
    key = context.user_data["stream_key"]
    title = context.user_data["title"]
    overlay = context.user_data["overlay"]

    rtmp_url = f"{rtmp_base.rstrip('/')}/{key}"

    sid = manager.new_id()
    stream = Stream(sid, m3u8, rtmp_url, title, overlay)
    manager.add(stream)

    try:
        await stream.start()
        await query.edit_message_text(
            f"*Stream Started*\n\n"
            f"Title: `{title}`\n"
            f"ID: `{sid}`\n\n"
            f"Click /streaminfo to manage your streams.",
            parse_mode="Markdown"
        )
    except Exception as e:
        manager.remove(sid)
        await query.edit_message_text(f"Failed to start stream:\n`{e}`", parse_mode="Markdown")

    return ConversationHandler.END

# ------------------------------------------------------------------
async def streaminfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Cancel any ongoing conversation
    if context.user_data:
        context.user_data.clear()

    streams = manager.all()
    if not streams:
        await update.message.reply_text("No active streams.\nUse /stream to start one.")
        return

    for s in streams:
        photo = await s.get_screenshot()
        caption = (
            f"*{s.title}*\n"
            f"ID: `{s.id}`\n"
            f"Uptime: `{s.uptime()}`\n"
            f"Overlay: `{'Yes' if s.overlay else 'No'}`"
        )
        keyboard = [[InlineKeyboardButton("Stop Stream", callback_data=f"stop_{s.id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if photo:
            await update.message.reply_photo(photo, caption=caption, parse_mode="Markdown", reply_markup=reply_markup)
        else:
            await update.message.reply_text(caption + "\n\nScreenshot loading...", parse_mode="Markdown", reply_markup=reply_markup)

# ------------------------------------------------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("stop_"):
        sid = data[5:]
        stream = manager.get(sid)
        if not stream:
            await query.edit_message_text("Stream not found.")
            return
        await stream.stop()
        manager.remove(sid)
        await query.edit_message_text(f"Stream *{stream.title}* (`{sid}`) stopped.", parse_mode="Markdown")

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
        fallbacks=[],
        allow_reentry=True  # Allows restarting /stream anytime
    )

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("streaminfo", streaminfo))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(button_handler))

    print("TGTV Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
