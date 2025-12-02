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

# STUDIO LOGO
STUDIO_LOGO = "https://i.postimg.cc/SsLmMd8K/101-170x85.png"  # ← Upload your logo

# STUDIO COLORS
PRIMARY = "🔴"
LIVE = "LIVE"
STOPPED = "OFFLINE"

async def delete_message(chat_id, message_id, bot, delay=45):
    await asyncio.sleep(delay)
    try: await bot.delete_message(chat_id, message_id)
    except: pass

# === STUDIO COMMANDS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("M3U8", callback_data="type_m3u8")],
        [InlineKeyboardButton("YouTube", callback_data="type_yt")],
        [InlineKeyboardButton("Stream Info", callback_data="info")]
    ]
    await update.message.reply_photo(
        photo=STUDIO_LOGO,
        caption=(
            f"*{PRIMARY} TGTV STUDIO*\n"
            f"┌{'─'*38}┐\n"
            f"│  BROADCAST CONTROL CENTER        │\n"
            f"│                                  │\n"
            f"│  Ultra-Smooth • 4K • 24/7        │\n"
            f"│  Adaptive Encoding • No Lag      │\n"
            f"│                                  │\n"
            f"└{'─'*38}┘\n\n"
            f"Choose source to go LIVE"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def studio_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    streams = manager.all()
    if not streams:
        await update.effective_message.edit_caption(
            caption=(
                f"*{PRIMARY} TGTV STUDIO*\n"
                f"┌{'─'*38}┐\n"
                f"│  NO ACTIVE BROADCAST             │\n"
                f"│                                  │\n"
                f"│  Status: {STOPPED}               │\n"
                f"│  Uptime: {BOT_START_TIME.strftime('%Hh %Mm')} │\n"
                f"└{'─'*38}┘"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Start New", callback_data="new_stream")]
            ])
        )
        return

    s = streams[0]  # Show first stream
    uptime = s.uptime()
    status = f"{LIVE} {uptime}"
    await update.effective_message.edit_caption(
        caption=(
            f"*{PRIMARY} TGTV STUDIO*\n"
            f"┌{'─'*38}┐\n"
            f"│  {s.title[:30]:<30} │\n"
            f"│                                  │\n"
            f"│  ID: `{s.id}`                    │\n"
            f"│  Status: {status:<20} │\n"
            f"│  Quality: ADAPTIVE               │\n"
            f"│  Encoder: x264 CRF 18            │\n"
            f"└{'─'*38}┘"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Stop", callback_data=f"stop_{s.id}")],
            [InlineKeyboardButton("Switch Source", callback_data="new_stream")]
        ])
    )

# === STREAM FLOW ===
async def stream_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["delete_queue"] = []
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("M3U8", callback_data="type_m3u8")],
        [InlineKeyboardButton("YouTube", callback_data="type_yt")],
        [InlineKeyboardButton("Back to Studio", callback_data="info")]
    ]
    await query.edit_message_caption(
        caption=(
            f"*{PRIMARY} SELECT SOURCE*\n"
            f"┌{'─'*38}┐\n"
            f"│  Choose input type               │\n"
            f"└{'─'*38}┘"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return INPUT_TYPE

async def choose_input_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    typ = query.data.split("_")[1]
    context.user_data["input_type"] = typ

    if typ == "m3u8":
        await query.edit_message_caption(
            caption=f"*{PRIMARY} M3U8 INPUT*\nSend playlist URL:",
            parse_mode="Markdown"
        )
        return M3U8_URL
    elif typ == "yt":
        await query.edit_message_caption(
            caption=f"*{PRIMARY} YOUTUBE INPUT*\nSend video URL:",
            parse_mode="Markdown"
        )
        return YOUTUBE_URL

async def get_m3u8_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    await update.message.delete()
    context.user_data["selected_input"] = url
    await ask_rtmp(update, context)
    return RTMP_BASE

async def get_youtube_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    await update.message.delete()
    context.user_data["selected_input"] = url
    await ask_rtmp(update, context)
    return RTMP_BASE

async def ask_rtmp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.edit_text(
        f"*{PRIMARY} RTMP TARGET*\n"
        f"Base URL:\n`rtmps://dc4-1.rtmp.t.me/s/`",
        parse_mode="Markdown"
    )

async def get_rtmp_base(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["rtmp_base"] = update.message.text.strip()
    await update.message.delete()
    await update.effective_message.edit_text(f"*{PRIMARY} STREAM KEY*\nEnter key:")
    return STREAM_KEY

async def get_stream_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["stream_key"] = update.message.text.strip()
    await update.message.delete()
    await update.effective_message.edit_text(f"*{PRIMARY} TITLE*\nEnter broadcast name:")
    return TITLE

async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["title"] = update.message.text.strip()
    await update.message.delete()
    rtmp = f"{context.user_data['rtmp_base'].rstrip('/')}/{context.user_data['stream_key'].lstrip('/')}"
    context.user_data["final_rtmp"] = rtmp

    await update.effective_message.edit_text(
        f"*{PRIMARY} CONFIRM & GO LIVE*\n"
        f"Title: `{context.user_data['title']}`\n"
        f"RTMP: `{rtmp}`\n\n"
        f"Ready to broadcast?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("GO LIVE", callback_data="confirm_start")]
        ])
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

    await query.edit_message_caption(
        caption=(
            f"*{PRIMARY} BROADCAST LIVE*\n"
            f"┌{'─'*38}┐\n"
            f"│  {title[:30]:<30} │\n"
            f"│                                  │\n"
            f"│  ID: `{sid}`                     │\n"
            f"│  Status: {LIVE} 00:00:01         │\n"
            f"│  Quality: ADAPTIVE               │\n"
            f"└{'─'*38}┘"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Stop", callback_data=f"stop_{sid}")],
            [InlineKeyboardButton("Studio Panel", callback_data="info")]
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
        await stream_entry(update, context)
    elif data.startswith("type_"):
        return await choose_input_type(update, context)
    elif data.startswith("stop_"):
        sid = data[5:]
        stream = manager.get(sid)
        if stream:
            stream.stop()
            manager.remove(sid)
            await query.edit_message_caption(
                caption=f"*{PRIMARY} BROADCAST STOPPED*\nStream `{sid}` terminated.",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_caption(caption="Stream not found.")

# === MAIN ===
def main():
    ensure_dirs()
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(stream_entry, "^new_stream$")],
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

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(studio_panel, "^info$"))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(button_handler))

    print("TGTV STUDIO IS LIVE")
    app.run_polling()

if __name__ == "__main__":
    main()
