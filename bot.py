# bot.py
import asyncio
import logging
import os
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

async def delete_message(chat_id, message_id, bot, delay=30):
    await asyncio.sleep(delay)
    try: await bot.delete_message(chat_id, message_id)
    except: pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text(
        "*TGTV Pro*\n\n"
        "• M3U8 (auto quality)\n"
        "• YouTube (loop)\n\n"
        "/stream to start",
        parse_mode="Markdown"
    )
    asyncio.create_task(delete_message(update.effective_chat.id, msg.message_id, context.bot, 30))

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("/stream /streaminfo /stop <id> /ping /stats")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime = datetime.utcnow() - BOT_START_TIME
    h, rem = divmod(int(uptime.total_seconds()), 3600)
    m, s = divmod(rem, 60)
    await update.message.reply_text(f"Bot: `{h:02}h {m:02}m {s:02}s`", parse_mode="Markdown")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("Fetching...")
    stats = await get_system_stats()
    await msg.edit_text(f"```\n{stats}\n```", parse_mode="Markdown")

# STREAM
async def stream_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["delete_queue"] = []
    asyncio.create_task(update.message.delete())

    keyboard = [
        [InlineKeyboardButton("M3U8", callback_data="type_m3u8")],
        [InlineKeyboardButton("YouTube", callback_data="type_yt")]
    ]
    msg = await update.effective_chat.send_message("Choose:", reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data["delete_queue"].append(msg.message_id)
    return INPUT_TYPE

async def choose_input_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    typ = query.data.split("_")[1]
    context.user_data["input_type"] = typ

    msg_id = context.user_data["delete_queue"].pop()
    try: await query.bot.delete_message(query.message.chat_id, msg_id)
    except: pass

    if typ == "m3u8":
        msg = await query.edit_message_text("Send *M3U8 URL*:", parse_mode="Markdown")
        context.user_data["delete_queue"].append(msg.message_id)
        return M3U8_URL
    elif typ == "yt":
        msg = await query.edit_message_text("Send *YouTube URL*:", parse_mode="Markdown")
        context.user_data["delete_queue"].append(msg.message_id)
        return YOUTUBE_URL

async def get_m3u8_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    asyncio.create_task(update.message.delete())
    context.user_data["selected_input"] = url
    await ask_rtmp_base(update, context)
    return RTMP_BASE

async def get_youtube_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    asyncio.create_task(update.message.delete())
    context.user_data["selected_input"] = url
    await ask_rtmp_base(update, context)
    return RTMP_BASE

async def ask_rtmp_base(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_id = context.user_data["delete_queue"].pop()
    try: await update.effective_chat.delete_message(msg_id)
    except: pass
    msg = await update.effective_chat.send_message(
        "Send *RTMP Base*:\n`rtmps://dc4-1.rtmp.t.me/s/`",
        parse_mode="Markdown"
    )
    context.user_data["delete_queue"].append(msg.message_id)

async def get_rtmp_base(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["rtmp_base"] = update.message.text.strip()
    asyncio.create_task(update.message.delete())
    msg_id = context.user_data["delete_queue"].pop()
    try: await update.effective_chat.delete_message(msg_id)
    except: pass
    msg = await update.effective_chat.send_message("Send *Key*:", parse_mode="Markdown")
    context.user_data["delete_queue"].append(msg.message_id)
    return STREAM_KEY

async def get_stream_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["stream_key"] = update.message.text.strip()
    asyncio.create_task(update.message.delete())
    msg_id = context.user_data["delete_queue"].pop()
    try: await update.effective_chat.delete_message(msg_id)
    except: pass
    msg = await update.effective_chat.send_message("Send *Title*:", parse_mode="Markdown")
    context.user_data["delete_queue"].append(msg.message_id)
    return TITLE

async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["title"] = update.message.text.strip()
    asyncio.create_task(update.message.delete())
    msg_id = context.user_data["delete_queue"].pop()
    try: await update.effective_chat.delete_message(msg_id)
    except: pass

    rtmp = f"{context.user_data['rtmp_base'].rstrip('/')}/{context.user_data['stream_key'].lstrip('/')}"
    context.user_data["final_rtmp"] = rtmp

    keyboard = [[InlineKeyboardButton("Start", callback_data="confirm_start")]]
    msg = await update.effective_chat.send_message(
        f"*Ready*\nTitle: `{context.user_data['title']}`\nRTMP: `{rtmp}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data["delete_queue"].append(msg.message_id)
    return CONFIRM

async def confirm_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    input_url = context.user_data["selected_input"]
    rtmp = context.user_data["final_rtmp"]
    title = context.user_data["title"]
    input_type = context.user_data["input_type"]
    chat_id = update.effective_chat.id

    sid = manager.new_id()
    stream = Stream(sid, input_url, rtmp, title, input_type, context.bot)
    stream.set_chat_id(chat_id)
    manager.add(stream)

    msg_id = context.user_data["delete_queue"].pop()
    try: await query.message.delete()
    except: pass

    stream.start()

    await query.message.reply_text(
        f"*Started*\nTitle: `{title}`\nID: `{sid}`",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def streaminfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    asyncio.create_task(update.message.delete())
    streams = manager.all()
    if not streams:
        await update.effective_chat.send_message("*No streams.*", parse_mode="Markdown")
        return
    for s in streams:
        keyboard = [[InlineKeyboardButton("Stop", callback_data=f"stop_{s.id}")]]
        await update.effective_chat.send_message(
            f"*{s.title}*\nID: `{s.id}`\nUptime: `{s.uptime()}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /stop <id>")
        return
    sid = context.args[0]
    stream = manager.get(sid)
    if not stream:
        await update.message.reply_text("Not found.")
        return
    stream.stop()
    manager.remove(sid)
    await update.message.reply_text(f"Stopped `{sid}`", parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("type_"):
        return await choose_input_type(update, context)
    if query.data.startswith("stop_"):
        sid = query.data[5:]
        stream = manager.get(sid)
        if stream:
            stream.stop()
            manager.remove(sid)
            await query.edit_message_text(f"Stopped `{sid}`")
        else:
            await query.edit_message_text("Not found.")

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
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("streaminfo", streaminfo))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(button_handler))

    print("TGTV Pro Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
