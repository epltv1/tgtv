# bot.py
import asyncio
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, ConversationHandler, filters
)
from stream_manager import StreamManager, Stream
from utils import ensure_dirs, get_system_stats

# STATES
INPUT_TYPE, M3U8_URL, YOUTUBE_URL, RTMP_BASE, STREAM_KEY, TITLE, CONFIRM = range(7)

logging.basicConfig(level=logging.INFO)
manager = StreamManager()
BOT_START_TIME = datetime.utcnow()
TOKEN = "7454188408:AAGnFnyFGDNk2l7NhyhSmoS5BYz0R82ZOTU"

STUDIO_LOGO = "https://i.postimg.cc/gkfNSFPv/lqo4nv.jpg"  # ← Your logo
PRIMARY = "FUTBOL+"
LIVE = "LIVE"
STOPPED = "OFFLINE"

# === /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("M3U8", callback_data="type_m3u8")],
        [InlineKeyboardButton("YouTube", callback_data="type_yt")],
        [InlineKeyboardButton("Studio Panel", callback_data="info")]
    ]
    await update.message.reply_photo(
        photo=STUDIO_LOGO,
        caption=(
            f"*{PRIMARY} STUDIO*\n"
            f"┌{'─'*38}┐\n"
            f"│  BROADCAST CONTROL CENTER        │\n"
            f"│                                  │\n"
            f"│  4K • ADAPTIVE • 24/7            │\n"
            f"│  No Lag • No Freeze              │\n"
            f"└{'─'*38}┘\n\n"
            f"Use /stream or buttons below"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# === /ping ===
async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime = datetime.utcnow() - BOT_START_TIME
    h, rem = divmod(int(uptime.total_seconds()), 3600)
    m, s = divmod(rem, 60)
    await update.message.reply_text(f"Bot Uptime: `{h:02}h {m:02}m {s:02}s`", parse_mode="Markdown")

# === /stats ===
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("Fetching stats...")
    stats = await get_system_stats()
    await msg.edit_text(f"```\n{stats}\n```", parse_mode="Markdown")

# === /streaminfo ===
async def streaminfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    streams = manager.all()
    if not streams:
        await update.message.reply_text("*No active streams.*", parse_mode="Markdown")
        du = asyncio.create_task(update.message.delete(delay=10))
        return

    for s in streams:
        keyboard = [[InlineKeyboardButton("Stop", callback_data=f"stop_{s.id}")]]
        await update.message.reply_text(
            f"*{s.title}*\nID: `{s.id}`\nUptime: `{s.uptime()}`\nStatus: `{LIVE}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# === /stop <id> ===
async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /stop <id>")
        return
    sid = context.args[0]
    stream = manager.get(sid)
    if not stream:
        await update.message.reply_text("Stream not found.")
        return
    stream.stop()
    manager.remove(sid)
    await update.message.reply_text(f"Stopped `{sid}`", parse_mode="Markdown")

# === /stream (QUICK START) ===
async def stream_entry_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["delete_queue"] = []
    await update.message.delete()

    keyboard = [
        [InlineKeyboardButton("M3U8", callback_data="type_m3u8")],
        [InlineKeyboardButton("YouTube", callback_data="type_yt")],
        [InlineKeyboardButton("Back", callback_data="info")]
    ]
    msg = await update.effective_chat.send_message(
        f"*{PRIMARY} SELECT SOURCE*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data["msg_id"] = msg.message_id
    return INPUT_TYPE

# === STUDIO PANEL ===
async def studio_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    streams = manager.all()

    if not streams:
        await query.edit_message_caption(
            caption=(
                f"*{PRIMARY} STUDIO*\n"
                f"┌{'─'*38}┐\n"
                f"│  NO ACTIVE BROADCAST             │\n"
                f"│                                  │\n"
                f"│  Status: {STOPPED}               │\n"
                f"└{'─'*38}┘"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Start New", callback_data="new_stream")]
            ])
        )
        return

    s = streams[0]
    await query.edit_message_caption(
        caption=(
            f"*{PRIMARY} LIVE*\n"
            f"┌{'─'*38}┐\n"
            f"│  {s.title[:30]:<30} │\n"
            f"│                                  │\n"
            f"│  ID: `{s.id}`                    │\n"
            f"│  Uptime: {s.uptime():<18} │\n"
            f"│  Quality: ADAPTIVE               │\n"
            f"└{'─'*38}┘"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Stop", callback_data=f"stop_{s.id}")],
            [InlineKeyboardButton("New Stream", callback_data="new_stream")]
        ])
    )

# === STREAM FLOW (SAME AS BEFORE) ===
async def choose_input_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    typ = query.data.split("_")[1]
    context.user_data["input_type"] = typ

    if typ == "m3u8":
        await query.edit_message_caption(caption="M3U8 INPUT\nSend playlist URL:")
        return M3U8_URL
    elif typ == "yt":
        await query.edit_message_caption(caption="YOUTUBE INPUT\nSend video URL:")
        return YOUTUBE_URL

async def get_m3u8_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    await update.message.delete()
    context.user_data["selected_input"] = url
    msg = await update.effective_chat.send_message("RTMP TARGET\nBase URL:\n`rtmps://dc4-1.rtmp.t.me/s/`", parse_mode="Markdown")
    context.user_data["msg_id"] = msg.message_id
    return RTMP_BASE

async def get_youtube_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    await update.message.delete()
    context.user_data["selected_input"] = url
    msg = await update.effective_chat.send_message("RTMP TARGET\nBase URL:\n`rtmps://dc4-1.rtmp.t.me/s/`", parse_mode="Markdown")
    context.user_data["msg_id"] = msg.message_id
    return RTMP_BASE

async def get_rtmp_base(update: Update, context: ContextTypes.DEFAULT_TYPE):
    base = update.message.text.strip()
    await update.message.delete()
    context.user_data["rtmp_base"] = base
    msg = await update.effective_chat.send_message("STREAM KEY\nEnter key:")
    context.user_data["msg_id"] = msg.message_id
    return STREAM_KEY

async def get_stream_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = update.message.text.strip()
    await update.message.delete()
    context.user_data["stream_key"] = key
    msg = await update.effective_chat.send_message("TITLE\nEnter broadcast name:")
    context.user_data["msg_id"] = msg.message_id
    return TITLE

async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.message.text.strip()
    await update.message.delete()
    context.user_data["title"] = title
    rtmp = f"{context.user_data['rtmp_base'].rstrip('/')}/{context.user_data['stream_key'].lstrip('/')}"
    context.user_data["final_rtmp"] = rtmp

    await update.effective_chat.send_message(
        f"*{PRIMARY} CONFIRM*\nTitle: `{title}`\nRTMP: `{rtmp}`\nReady?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("GO LIVE", callback_data="confirm_start")]])
    )
    return CONFIRM

async def confirm_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    input_url = context.user_data["selected_input"]
    rtmp = context.user_data["final_rtmp"]
    title = context.user_data["title"]
    input_type = context.user_data["input_type"]

    sid = manager.new_id()
    stream = Stream(sid, input_url, rtmp, title, input_type, context.bot)
    stream.set_chat_id(update.effective_chat.id)
    manager.add(stream)
    stream.start()

    await query.edit_message_text(
        f"*{PRIMARY} BROADCAST LIVE*\n"
        f"┌{'─'*38}┐\n"
        f"│  {title[:30]:<30} │\n"
        f"│  ID: `{sid}`                     │\n"
        f"│  Status: {LIVE} 00:00:01         │\n"
        f"└{'─'*38}┘",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Stop", callback_data=f"stop_{sid}")],
            [InlineKeyboardButton("Studio", callback_data="info")]
        ])
    )
    return ConversationHandler.END

# === BUTTONS ===
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "info":
        await studio_panel(update, context)
    elif data == "new_stream":
        return await stream_entry_cmd(update, context)
    elif data.startswith("type_"):
        return await choose_input_type(update, context)
    elif data.startswith("stop_"):
        sid = data[5:]
        stream = manager.get(sid)
        if stream:
            stream.stop()
            manager.remove(sid)
            await query.edit_message_text(f"Stream `{sid}` stopped.")
        else:
            await query.edit_message_text("Not found.")

# === MAIN ===
def main():
    ensure_dirs()
    app = Application.builder().token(TOKEN).build()

    # Conversation for /stream
    conv = ConversationHandler(
        entry_points=[CommandHandler("stream", stream_entry_cmd)],
        states={
            INPUT_TYPE: [CallbackQueryHandler(choose_input_type, "^type_")],
            M3U8_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_m3u8_url)],
            YOUTUBE_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_youtube_url)],
            RTMP_BASE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_rtmp_base)],
            STREAM_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_stream_key)],
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_title)],
            CONFIRM: [CallbackQueryHandler(confirm_start, "^confirm_start$")],
        },
        fallbacks=[],
        allow_reentry=True
    )

    # COMMANDS
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("streaminfo", streaminfo))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(studio_panel, "^info$"))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("FUTBOL-X STUDIO + COMMANDS = READY")
    app.run_polling()

if __name__ == "__main__":
    main()
