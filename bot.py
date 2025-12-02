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

# === AUTO-DELETE + INSTANT COMMAND DELETE ===
async def auto_delete(chat_id, message_id, bot, delay=30):
    await asyncio.sleep(delay)
    try: await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except: pass

async def delete_command_and_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, reply_text, reply_markup=None):
    await update.message.delete()  # INSTANT DELETE COMMAND
    msg = await update.effective_chat.send_message(reply_text, parse_mode="Markdown", reply_markup=reply_markup)
    asyncio.create_task(auto_delete(update.effective_chat.id, msg.message_id, context.bot))
    return msg

# === /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_command_and_reply(
        update, context,
        "*TGTV Universal*\n\n"
        "/stream - Start\n"
        "/abc - List\n"
        "/stop <id> - Stop\n"
        "/ping - Uptime\n"
        "/stats - System\n\n"
        "Supports: rtmp:// & rtmps://"
    )

# === /ping ===
async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    delta = datetime.utcnow() - BOT_START_TIME
    h, rem = divmod(int(delta.total_seconds()), 3600)
    m, s = divmod(rem, 60)
    await delete_command_and_reply(update, context, f"Uptime: `{h:02}h {m:02}m {s:02}s`")

# === /stats ===
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.delete()
    temp = await update.effective_chat.send_message("Fetching...")
    stats_text = await get_system_stats()
    msg = await temp.edit_text(f"```\n{stats_text}\n```", parse_mode="Markdown")
    asyncio.create_task(auto_delete(update.effective_chat.id, msg.message_id, context.bot))

# === /streaminfo (renamed /abc) ===
async def streaminfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    streams = manager.all()
    if not streams:
        await delete_command_and_reply(update, context, "No active streams.")
        return
    for s in streams:
        msg = await update.effective_chat.send_message(
            f"Title: `{s.title}`\n"
            f"ID: `{s.id}`\n"
            f"Uptime: `{s.uptime()}`\n"
            f"RTMP: `{s.rtmp}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Stop", callback_data=f"stop_{s.id}")]])
        )
        asyncio.create_task(auto_delete(update.effective_chat.id, msg.message_id, context.bot))

# === /stop <id> ===
async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await delete_command_and_reply(update, context, "Usage: /stop <id>")
        return
    sid = context.args[0]
    stream = manager.get(sid)
    if not stream:
        await delete_command_and_reply(update, context, "Not found.")
        return
    stream.stop()
    manager.remove(sid)
    await delete_command_and_reply(update, context, f"Stopped `{sid}`")

# === /stream ===
async def stream_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.delete()

    keyboard = [
        [InlineKeyboardButton("M3U8", callback_data="type_m3u8")],
        [InlineKeyboardButton("YouTube", callback_data="type_yt")]
    ]
    msg = await update.effective_chat.send_message(
        "Choose input type:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data["msg_id"] = msg.message_id
    asyncio.create_task(auto_delete(update.effective_chat.id, msg.message_id, context.bot))
    return INPUT_TYPE

async def choose_input_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    typ = query.data.split("_")[1]
    context.user_data["input_type"] = typ
    text = "Send M3U8 URL:" if typ == "m3u8" else "Send YouTube URL:"
    msg = await query.edit_message_text(text)
    asyncio.create_task(auto_delete(update.effective_chat.id, msg.message_id, context.bot))
    return M3U8_URL if typ == "m3u8" else YOUTUBE_URL

async def get_m3u8_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    await update.message.delete()
    context.user_data["selected_input"] = url
    msg = await update.effective_chat.send_message("RTMP Base URL:\n`rtmp://` or `rtmps://`", parse_mode="Markdown")
    context.user_data["msg_id"] = msg.message_id
    asyncio.create_task(auto_delete(update.effective_chat.id, msg.message_id, context.bot))
    return RTMP_BASE

async def get_youtube_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    await update.message.delete()
    context.user_data["selected_input"] = url
    msg = await update.effective_chat.send_message("RTMP Base URL:\n`rtmp://` or `rtmps://`", parse_mode="Markdown")
    context.user_data["msg_id"] = msg.message_id
    asyncio.create_task(auto_delete(update.effective_chat.id, msg.message_id, context.bot))
    return RTMP_BASE

async def get_rtmp_base(update: Update, context: ContextTypes.DEFAULT_TYPE):
    base = update.message.text.strip()
    await update.message.delete()
    if not base.lower().startswith(("rtmp://", "rtmps://")):
        msg = await update.effective_chat.send_message("Invalid RTMP URL.\nUse `rtmp://` or `rtmps://`", parse_mode="Markdown")
        asyncio.create_task(auto_delete(update.effective_chat.id, msg.message_id, context.bot))
        return RTMP_BASE
    context.user_data["rtmp_base"] = base
    msg = await update.effective_chat.send_message("Stream Key:")
    context.user_data["msg_id"] = msg.message_id
    asyncio.create_task(auto_delete(update.effective_chat.id, msg.message_id, context.bot))
    return STREAM_KEY

async def get_stream_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = update.message.text.strip()
    await update.message.delete()
    context.user_data["stream_key"] = key
    msg = await update.effective_chat.send_message("Title:")
    context.user_data["msg_id"] = msg.message_id
    asyncio.create_task(auto_delete(update.effective_chat.id, msg.message_id, context.bot))
    return TITLE

async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.message.text.strip()
    await update.message.delete()
    context.user_data["title"] = title
    rtmp = f"{context.user_data['rtmp_base'].rstrip('/')}/{context.user_data['stream_key'].lstrip('/')}"
    context.user_data["final_rtmp"] = rtmp
    msg = await update.effective_chat.send_message(
        f"Ready:\nTitle: `{title}`\nRTMP: `{rtmp}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Start", callback_data="confirm_start")]])
    )
    context.user_data["msg_id"] = msg.message_id
    asyncio.create_task(auto_delete(update.effective_chat.id, msg.message_id, context.bot))
    return CONFIRM

async def confirm_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sid = manager.new_id()
    stream = Stream(sid, context.user_data["selected_input"], context.user_data["final_rtmp"],
                    context.user_data["title"], context.user_data["input_type"], context.bot)
    stream.set_chat_id(update.effective_chat.id)
    manager.add(stream)
    stream.start()
    msg = await query.edit_message_text(
        f"Started\nTitle: `{context.user_data['title']}`\nID: `{sid}`\nRTMP: `{context.user_data['final_rtmp']}`",
        parse_mode="Markdown"
    )
    asyncio.create_task(auto_delete(update.effective_chat.id, msg.message_id, context.bot, delay=60))
    return ConversationHandler.END

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("stop_"):
        sid = query.data[5:]
        stream = manager.get(sid)
        if stream:
            stream.stop()
            manager.remove(sid)
            msg = await query.edit_message_text(f"Stopped `{sid}`")
            asyncio.create_task(auto_delete(update.effective_chat.id, msg.message_id, context.bot))
        else:
            msg = await query.edit_message_text("Not found.")
            asyncio.create_task(auto_delete(update.effective_chat.id, msg.message_id, context.bot))

def main():
    ensure_dirs()
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("stream", stream_entry)],
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
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("abc", streaminfo))  # ← /abc = /streaminfo
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(button_handler))

    print("TGTV — ADVANCED FFMPEG + INSTANT CLEAN")
    app.run_polling()

if __name__ == "__main__":
    main()
