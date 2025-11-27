# bot.py
import asyncio
import logging
import os
import uuid
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, ConversationHandler, filters
)
from stream_manager import StreamManager, Stream

# ------------------------------------------------------------------
M3U8, RTMP_BASE, STREAM_KEY, TITLE, CONFIRM = range(5)

# ------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
manager = StreamManager()
BOT_START_TIME = datetime.utcnow()

TOKEN = "7454188408:AAGnFnyFGDNk2l7NhyhSmoS5BYz0R82ZOTU"

# ------------------------------------------------------------------
async def delete_message(update: Update, context: ContextTypes.DEFAULT_TYPE, delay: int = 2):
    """Delete user or bot message after delay"""
    await asyncio.sleep(delay)
    try:
        await update.message.delete()
    except:
        pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text(
        "*TGTV Stream Bot*\n\n"
        "Push M3U8 to RTMP.\n"
        "Use /help for commands.",
        parse_mode="Markdown"
    )
    asyncio.create_task(delete_message(update, context, 30))
    return

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text(
        "/start - Welcome\n"
        "/help - Commands\n"
        "/ping - Stats\n"
        "/streaminfo - Active streams\n"
        "/stream - Start streaming"
    )
    asyncio.create_task(delete_message(update, context, 30))
    return

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime = datetime.utcnow() - BOT_START_TIME
    h, rem = divmod(int(uptime.total_seconds()), 3600)
    m, s = divmod(rem, 60)
    bot_up = f"{h:02}h {m:02}m {s:02}s"
    msg = await update.message.reply_text(f"Bot Uptime: `{bot_up}`", parse_mode="Markdown")
    asyncio.create_task(delete_message(update, context, 15))
    return

# ------------------------------------------------------------------
async def stream_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["delete_queue"] = []  # Track messages to delete

    # Delete /stream command
    asyncio.create_task(update.message.delete())

    keyboard = [[InlineKeyboardButton("M3U8", callback_data="type_m3u8")]]
    msg = await update.effective_chat.send_message("Choose input:", reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data["delete_queue"].append(msg.message_id)
    return M3U8

async def type_m3u8(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Delete previous bot message
    msg_id = context.user_data["delete_queue"].pop()
    try:
        await query.bot.delete_message(query.message.chat_id, msg_id)
    except:
        pass

    msg = await query.edit_message_text("Send the *M3U8 URL*:", parse_mode="Markdown")
    context.user_data["delete_queue"].append(msg.message_id)
    return M3U8

async def get_m3u8(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["m3u8"] = update.message.text.strip()

    # Delete user input
    asyncio.create_task(update.message.delete())

    # Delete previous bot message
    msg_id = context.user_data["delete_queue"].pop()
    try:
        await update.effective_chat.delete_message(msg_id)
    except:
        pass

    msg = await update.effective_chat.send_message(
        "Send *RTMP Base URL* (include `/` if needed):\n"
        "Example: `rtmps://dc4-1.rtmp.t.me/s/`",
        parse_mode="Markdown"
    )
    context.user_data["delete_queue"].append(msg.message_id)
    return RTMP_BASE

async def get_rtmp_base(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["rtmp_base"] = update.message.text.strip()
    asyncio.create_task(update.message.delete())

    msg_id = context.user_data["delete_queue"].pop()
    try:
        await update.effective_chat.delete_message(msg_id)
    except:
        pass

    msg = await update.effective_chat.send_message("Send the *Stream Key*:", parse_mode="Markdown")
    context.user_data["delete_queue"].append(msg.message_id)
    return STREAM_KEY

async def get_stream_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["stream_key"] = update.message.text.strip()
    asyncio.create_task(update.message.delete())

    msg_id = context.user_data["delete_queue"].pop()
    try:
        await update.effective_chat.delete_message(msg_id)
    except:
        pass

    msg = await update.effective_chat.send_message("Send the *Stream Title*:", parse_mode="Markdown")
    context.user_data["delete_queue"].append(msg.message_id)
    return TITLE

async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["title"] = update.message.text.strip()
    asyncio.create_task(update.message.delete())

    msg_id = context.user_data["delete_queue"].pop()
    try:
        await update.effective_chat.delete_message(msg_id)
    except:
        pass

    base = context.user_data["rtmp_base"]
    key = context.user_data["stream_key"]
    final_rtmp = f"{base.rstrip('/')}/{key.lstrip('/')}"
    context.user_data["final_rtmp"] = final_rtmp

    keyboard = [[InlineKeyboardButton("Start Stream", callback_data="confirm_start")]]
    msg = await update.effective_chat.send_message(
        f"*Ready to Start*\n\n"
        f"Title: `{context.user_data['title']}`\n"
        f"RTMP: `{final_rtmp}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data["delete_queue"].append(msg.message_id)
    return CONFIRM

async def confirm_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    m3u8 = context.user_data["m3u8"]
    rtmp = context.user_data["final_rtmp"]
    title = context.user_data["title"]

    sid = manager.new_id()
    stream = Stream(sid, m3u8, rtmp, title)
    manager.add(stream)

    # Delete confirm message
    msg_id = context.user_data["delete_queue"].pop()
    try:
        await query.message.delete()
    except:
        pass

    try:
        await stream.start()
        msg = await query.message.reply_text(
            f"*Stream Started*\n\n"
            f"Title: `{title}`\n"
            f"ID: `{sid}`\n\n"
            f"Use /streaminfo to manage.",
            parse_mode="Markdown"
        )
        # Keep this message
    except Exception as e:
        await query.message.reply_text(f"Failed: `{e}`", parse_mode="Markdown")

    return ConversationHandler.END

# ------------------------------------------------------------------
async def streaminfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Delete /streaminfo command
    asyncio.create_task(update.message.delete())

    streams = manager.all()
    if not streams:
        msg = await update.effective_chat.send_message("No active streams.")
        asyncio.create_task(delete_message(update, context, 10))
        return

    for s in streams:
        await s.take_thumbnail()
        caption = (
            f"*{s.title}*\n"
            f"ID: `{s.id}`\n"
            f"Uptime: `{s.uptime()}`"
        )
        keyboard = [[InlineKeyboardButton("Stop Stream", callback_data=f"stop_{s.id}")]]
        markup = InlineKeyboardMarkup(keyboard)

        if os.path.exists(s.thumb_path):
            msg = await update.effective_chat.send_photo(
                photo=open(s.thumb_path, "rb"),
                caption=caption,
                parse_mode="Markdown",
                reply_markup=markup
            )
            # Keep this message
        else:
            msg = await update.effective_chat.send_message(
                caption + "\n\nScreenshot loading...",
                parse_mode="Markdown",
                reply_markup=markup
            )
            # Keep

# ------------------------------------------------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not query.data.startswith("stop_"):
        return

    sid = query.data[5:]
    stream = manager.get(sid)
    if not stream:
        try:
            await query.edit_message_text("Stream already stopped.")
        except:
            pass
        return

    uptime = stream.uptime()
    title = stream.title

    await stream.stop()
    manager.remove(sid)

    # Delete old streaminfo message
    try:
        await query.message.delete()
    except:
        pass

    # Send final clean message
    await query.message.reply_text(
        f"Stream *{title}* ended after `{uptime}`",
        parse_mode="Markdown"
    )

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
