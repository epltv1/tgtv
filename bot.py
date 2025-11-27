# bot.py
import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, ConversationHandler, filters
)
from stream_manager import StreamManager, Stream

# ------------------------------------------------------------------
M3U8, RTMP_BASE, STREAM_KEY, TITLE, OVERLAY, CONFIRM = range(6)

# ------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
manager = StreamManager()
BOT_START_TIME = datetime.utcnow()

TOKEN = "7454188408:AAGnFnyFGDNk2l7NhyhSmoS5BYz0R82ZOTU"

# ------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*TGTV Stream Bot*\n\n"
        "Push M3U8 to RTMP.\n"
        "Use /help for commands.",
        parse_mode="Markdown"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start - Welcome\n"
        "/help - Commands\n"
        "/ping - Stats\n"
        "/streaminfo - Active streams\n"
        "/stream - Start streaming"
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime = datetime.utcnow() - BOT_START_TIME
    h, rem = divmod(int(uptime.total_seconds()), 3600)
    m, s = divmod(rem, 60)
    bot_up = f"{h:02}h {m:02}m {s:02}s"
    await update.message.reply_text(f"Bot Uptime: `{bot_up}`", parse_mode="Markdown")

# ------------------------------------------------------------------
async def stream_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    keyboard = [[InlineKeyboardButton("M3U8", callback_data="type_m3u8")]]
    await update.message.reply_text("Choose input:", reply_markup=InlineKeyboardMarkup(keyboard))
    return M3U8

async def type_m3u8(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Send the *M3U8 URL*:", parse_mode="Markdown")
    return M3U8

async def get_m3u8(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["m3u8"] = update.message.text.strip()
    await update.message.reply_text(
        "Send *RTMP Base URL* (include `/` if needed):\n"
        "Example: `rtmps://dc4-1.rtmp.t.me/s/`",
        parse_mode="Markdown"
    )
    return RTMP_BASE

async def get_rtmp_base(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["rtmp_base"] = update.message.text.strip()
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
    await update.message.reply_text("Overlay logo?", reply_markup=InlineKeyboardMarkup(keyboard))
    return OVERLAY

async def overlay_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["overlay"] = query.data.endswith("yes")

    base = context.user_data["rtmp_base"]
    key = context.user_data["stream_key"]
    final_rtmp = f"{base.rstrip('/')}/{key.lstrip('/')}"  # SAFE JOIN

    context.user_data["final_rtmp"] = final_rtmp

    keyboard = [[InlineKeyboardButton("Start Stream", callback_data="confirm_start")]]
    await query.edit_message_text(
        f"*Ready to Start*\n\n"
        f"Title: `{context.user_data['title']}`\n"
        f"Overlay: `{'Yes' if context.user_data['overlay'] else 'No'}`\n"
        f"RTMP: `{final_rtmp}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CONFIRM

async def confirm_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    m3u8 = context.user_data["m3u8"]
    rtmp = context.user_data["final_rtmp"]
    title = context.user_data["title"]
    overlay = context.user_data["overlay"]

    sid = manager.new_id()
    stream = Stream(sid, m3u8, rtmp, title, overlay)
    manager.add(stream)

    try:
        await stream.start()
        await query.edit_message_text(
            f"*Stream Started*\n\n"
            f"Title: `{title}`\n"
            f"ID: `{sid}`\n\n"
            f"Use /streaminfo to manage.",
            parse_mode="Markdown"
        )
    except Exception as e:
        manager.remove(sid)
        await query.edit_message_text(f"Failed: `{e}`", parse_mode="Markdown")

    return ConversationHandler.END

# ------------------------------------------------------------------
async def streaminfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    streams = manager.all()
    if not streams:
        await update.message.reply_text("No active streams.")
        return

    for s in streams:
        # Force thumbnail
        await s.take_thumbnail()
        photo_path = s.thumb_path

        caption = (
            f"*{s.title}*\n"
            f"ID: `{s.id}`\n"
            f"Uptime: `{s.uptime()}`\n"
            f"Overlay: `{'Yes' if s.overlay else 'No'}`"
        )
        keyboard = [[InlineKeyboardButton("Stop Stream", callback_data=f"stop_{s.id}")]]
        markup = InlineKeyboardMarkup(keyboard)

        if photo_path and os.path.exists(photo_path):
            await update.message.reply_photo(
                photo=open(photo_path, "rb"),
                caption=caption,
                parse_mode="Markdown",
                reply_markup=markup
            )
        else:
            await update.message.reply_text(
                caption + "\n\nScreenshot loading...",
                parse_mode="Markdown",
                reply_markup=markup
            )

# ------------------------------------------------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not query.data.startswith("stop_"):
        return

    sid = query.data[5:]
    stream = manager.get(sid)
    if not stream:
        await query.edit_message_text("Stream not found.")
        return

    await stream.stop()
    manager.remove(sid)
    await query.edit_message_text(f"Stream *{stream.title}* stopped.", parse_mode="Markdown")

# ------------------------------------------------------------------
def main():
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("stream", stream_entry)],
        states={
            M3U8: [CallbackQueryHandler(type_m3u8, "^type_m3u8$"), MessageHandler(filters.TEXT & ~filters.COMMAND, get_m3u8)],
            RTMP_BASE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_rtmp_base)],
            STREAM_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_stream_key)],
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_title)],
            OVERLAY: [CallbackQueryHandler(overlay_choice, "^overlay_")],
            CONFIRM: [CallbackQueryHandler(confirm_start, "^confirm_start$")],
        },
        fallbacks=[],
        allow_reentry=True
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("streaminfo", streaminfo))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(button_handler))

    print("TGTV Bot Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
