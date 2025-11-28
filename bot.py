# bot.py
import asyncio
import logging
import os
import uuid
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, ConversationHandler, filters
)
from stream_manager import StreamManager, Stream
from utils import ensure_dirs, is_valid_url, get_system_stats

# ------------------------------------------------------------------
# States
INPUT_TYPE, M3U8_URL, YOUTUBE_URL, RTMP_BASE, STREAM_KEY, TITLE, CONFIRM = range(7)

# ------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
manager = StreamManager()
BOT_START_TIME = datetime.utcnow()

TOKEN = "7454188408:AAGnFnyFGDNk2l7NhyhSmoS5BYz0R82ZOTU"

# ------------------------------------------------------------------
async def delete_message(chat_id, message_id, bot, delay=30):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except:
        pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text(
        "*TGTV Stream Bot*\n\n"
        "• M3U8 (auto quality)\n"
        "• YouTube (VOD loops)\n\n"
        "Use /help for commands.",
        parse_mode="Markdown"
    )
    asyncio.create_task(delete_message(update.effective_chat.id, msg.message_id, context.bot, 30))

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text(
        "/start - Welcome\n"
        "/help - Commands\n"
        "/ping - Bot uptime\n"
        "/stats - System\n"
        "/streaminfo - Active streams\n"
        "/stop <id> - Stop stream\n"
        "/stream - Start streaming"
    )
    asyncio.create_task(delete_message(update.effective_chat.id, msg.message_id, context.bot, 30))

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime = datetime.utcnow() - BOT_START_TIME
    h, rem = divmod(int(uptime.total_seconds()), 3600)
    m, s = divmod(rem, 60)
    bot_up = f"{h:02}h {m:02}m {s:02}s"
    msg = await update.message.reply_text(f"Bot Uptime: `{bot_up}`", parse_mode="Markdown")
    asyncio.create_task(delete_message(update.effective_chat.id, msg.message_id, context.bot, 30))

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("Fetching system stats...")
    stats_text = await get_system_stats()
    await msg.edit_text(f"```\n{stats_text}\n```", parse_mode="Markdown")
    asyncio.create_task(delete_message(update.effective_chat.id, msg.message_id, context.bot, 30))

# ------------------------------------------------------------------
async def stream_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["delete_queue"] = []
    asyncio.create_task(update.message.delete())

    keyboard = [
        [InlineKeyboardButton("M3U8", callback_data="type_m3u8")],
        [InlineKeyboardButton("YouTube", callback_data="type_yt")]
    ]
    msg = await update.effective_chat.send_message("Choose input type:", reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data["delete_queue"].append(msg.message_id)
    return INPUT_TYPE

async def choose_input_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    typ = query.data
    context.user_data["input_type"] = typ

    msg_id = context.user_data["delete_queue"].pop()
    try:
        await query.bot.delete_message(query.message.chat_id, msg_id)
    except:
        pass

    if typ == "type_m3u8":
        msg = await query.edit_message_text("Send the *Master M3U8 URL*:", parse_mode="Markdown")
        context.user_data["delete_queue"].append(msg.message_id)
        return M3U8_URL
    elif typ == "type_yt":
        msg = await query.edit_message_text("Send *YouTube URL*:", parse_mode="Markdown")
        context.user_data["delete_queue"].append(msg.message_id)
        return YOUTUBE_URL

# ------------------------------------------------------------------
async def get_m3u8_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    master_url = update.message.text.strip()
    asyncio.create_task(update.message.delete())
    msg_id = context.user_data["delete_queue"].pop()
    try:
        await update.effective_chat.delete_message(msg_id)
    except:
        pass

    msg = await update.effective_chat.send_message("Selecting best quality...")
    context.user_data["delete_queue"].append(msg.message_id)

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(master_url, timeout=10) as resp:
                text = await resp.text()
        lines = text.splitlines()
        best_url = master_url
        best_bw = 0
        base_url = master_url.rsplit("/", 1)[0] + "/"
        for i, line in enumerate(lines):
            if line.startswith("#EXT-X-STREAM-INF"):
                bw_match = re.search(r'BANDWIDTH=(\d+)', line)
                if bw_match and i + 1 < len(lines):
                    bw = int(bw_match.group(1))
                    if bw > best_bw:
                        url = lines[i + 1].strip()
                        if not url.startswith("http"):
                            url = base_url + url
                        best_url = url
                        best_bw = bw
        context.user_data["selected_input"] = best_url
    except:
        context.user_data["selected_input"] = master_url

    await asyncio.sleep(1)
    await ask_rtmp_base(update, context)
    return RTMP_BASE

async def get_youtube_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    asyncio.create_task(update.message.delete())
    msg_id = context.user_data["delete_queue"].pop()
    try:
        await update.effective_chat.delete_message(msg_id)
    except:
        pass

    msg = await update.effective_chat.send_message("Downloading YouTube video...")
    context.user_data["delete_queue"].append(msg.message_id)

    try:
        proc = await asyncio.create_subprocess_exec(
            "yt-dlp", "-f", "best[height<=1080]", "-g", url,
            stdout=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        yt_url = stdout.decode().strip()
        context.user_data["selected_input"] = yt_url
    except:
        context.user_data["selected_input"] = url

    await asyncio.sleep(1)
    await ask_rtmp_base(update, context)
    return RTMP_BASE

# ------------------------------------------------------------------
async def ask_rtmp_base(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    input_url = context.user_data["selected_input"]
    rtmp = context.user_data["final_rtmp"]
    title = context.user_data["title"]
    input_type = context.user_data["input_type"]

    sid = manager.new_id()
    stream = Stream(sid, input_url, rtmp, title, input_type)
    manager.add(stream)

    msg_id = context.user_data["delete_queue"].pop()
    try:
        await query.message.delete()
    except:
        pass

    try:
        await stream.start()
        await query.message.reply_text(
            f"*Stream Started*\n\n"
            f"Title: `{title}`\n"
            f"ID: `{sid}`\n\n"
            f"Use /streaminfo to manage.",
            parse_mode="Markdown"
        )
    except Exception as e:
        await query.message.reply_text(f"Failed: `{e}`", parse_mode="Markdown")

    return ConversationHandler.END

# ------------------------------------------------------------------
async def streaminfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    asyncio.create_task(update.message.delete())

    streams = manager.all()
    if not streams:
        msg = await update.effective_chat.send_message("No active streams.")
        asyncio.create_task(delete_message(update.effective_chat.id, msg.message_id, context.bot, 30))
        return

    for s in streams:
        if s.process and s.process.returncode is not None:
            manager.remove(s.id)
            continue

        await s.take_thumbnail()
        caption = f"*{s.title}*\nID: `{s.id}`\nUptime: `{s.uptime()}`"
        keyboard = [[InlineKeyboardButton("Stop Stream", callback_data=f"stop_{s.id}")]]
        markup = InlineKeyboardMarkup(keyboard)

        if os.path.exists(s.thumb_path):
            await update.effective_chat.send_photo(
                photo=open(s.thumb_path, "rb"),
                caption=caption,
                parse_mode="Markdown",
                reply_markup=markup
            )

# ------------------------------------------------------------------
async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /stop <stream_id>")
        return
    sid = context.args[0]
    stream = manager.get(sid)
    if not stream:
        await update.message.reply_text("Stream not found.")
        return

    await stream.stop()
    manager.remove(sid)
    await update.message.reply_text(f"Stream `{sid}` stopped.", parse_mode="Markdown")

# ------------------------------------------------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("type_"):
        return await choose_input_type(update, context)
    if not query.data.startswith("stop_"):
        return

    sid = query.data[5:]
    stream = manager.get(sid)
    if not stream:
        await query.edit_message_text("Stream already stopped.")
        return

    await stream.stop()
    manager.remove(sid)
    await query.message.delete()
    await query.message.reply_text(f"Stream *{stream.title}* stopped.", parse_mode="Markdown")

# ------------------------------------------------------------------
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

    print("TGTV Bot Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
