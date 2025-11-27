# bot.py
import asyncio
import logging
import os
import uuid
import json
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, ConversationHandler, filters
)
from stream_manager import StreamManager, Stream

# ------------------------------------------------------------------
# States
INPUT_TYPE, M3U8_URL, MPD_URL, DRM_KEY, QUALITY, RTMP_BASE, STREAM_KEY, TITLE, CONFIRM = range(9)

# ------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
manager = StreamManager()
BOT_START_TIME = datetime.utcnow()

TOKEN = "7454188408:AAGnFnyFGDNk2l7NhyhSmoS5BYz0R82ZOTU"

# ------------------------------------------------------------------
async def delete_message(chat_id, message_id, bot):
    await asyncio.sleep(2)
    try:
        await bot.delete_message(chat_id, message_id)
    except:
        pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text(
        "*TGTV Stream Bot*\n\n"
        "M3U8 + MPD (DRM)\n"
        "Auto quality fallback\n"
        "Use /help for commands.",
        parse_mode="Markdown"
    )
    asyncio.create_task(delete_message(update.effective_chat.id, msg.message_id, context.bot))

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text(
        "/start - Welcome\n"
        "/help - Commands\n"
        "/ping - Stats\n"
        "/streaminfo - Active streams\n"
        "/stream - Start streaming"
    )
    asyncio.create_task(delete_message(update.effective_chat.id, msg.message_id, context.bot))

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime = datetime.utcnow() - BOT_START_TIME
    h, rem = divmod(int(uptime.total_seconds()), 3600)
    m, s = divmod(rem, 60)
    bot_up = f"{h:02}h {m:02}m {s:02}s"
    msg = await update.message.reply_text(f"Bot Uptime: `{bot_up}`", parse_mode="Markdown")
    asyncio.create_task(delete_message(update.effective_chat.id, msg.message_id, context.bot))

# ------------------------------------------------------------------
async def stream_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["delete_queue"] = []

    asyncio.create_task(update.message.delete())

    keyboard = [
        [InlineKeyboardButton("M3U8", callback_data="type_m3u8")],
        [InlineKeyboardButton("MPD (DRM)", callback_data="type_mpd")]
    ]
    msg = await update.effective_chat.send_message("Choose input type:", reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data["delete_queue"].append(msg.message_id)
    return INPUT_TYPE

async def choose_input_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data["input_type"] = "m3u8" if query.data == "type_m3u8" else "mpd"

    msg_id = context.user_data["delete_queue"].pop()
    try:
        await query.bot.delete_message(query.message.chat_id, msg_id)
    except:
        pass

    if context.user_data["input_type"] == "m3u8":
        msg = await query.edit_message_text("Send the *Master M3U8 URL*:", parse_mode="Markdown")
        context.user_data["delete_queue"].append(msg.message_id)
        return M3U8_URL
    else:
        msg = await query.edit_message_text("Send the *MPD URL*:", parse_mode="Markdown")
        context.user_data["delete_queue"].append(msg.message_id)
        return MPD_URL

# ------------------------------------------------------------------
async def get_m3u8_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["m3u8_master"] = update.message.text.strip()
    asyncio.create_task(update.message.delete())

    msg_id = context.user_data["delete_queue"].pop()
    try:
        await update.effective_chat.delete_message(msg_id)
    except:
        pass

    msg = await update.effective_chat.send_message("Detecting qualities...")
    context.user_data["delete_queue"].append(msg.message_id)
    await detect_m3u8_qualities(update, context)
    return QUALITY

async def detect_m3u8_qualities(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = context.user_data["m3u8_master"]
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                text = await resp.text()
        lines = text.splitlines()
        qualities = []
        base_url = url.rsplit("/", 1)[0] + "/"
        for i, line in enumerate(lines):
            if line.startswith("#EXT-X-STREAM-INF"):
                bandwidth = re.search(r'BANDWIDTH=(\d+)', line)
                resolution = re.search(r'RESOLUTION=(\d+x\d+)', line)
                if i + 1 < len(lines):
                    playlist_url = lines[i + 1].strip()
                    if not playlist_url.startswith("http"):
                        playlist_url = base_url + playlist_url
                    label = resolution.group(1) if resolution else "Unknown"
                    bw = int(bandwidth.group(1)) // 1000 if bandwidth else 0
                    qualities.append((label, bw, playlist_url))

        if len(qualities) == 1:
            # AUTO USE SINGLE QUALITY
            context.user_data["selected_input"] = qualities[0][2]
            context.user_data["qualities"] = []
            await auto_proceed(update, context, "No multi-qualities detected. Using default.")
            return RTMP_BASE
        elif len(qualities) > 1:
            context.user_data["qualities"] = qualities
            await show_quality_buttons(update, context)
        else:
            context.user_data["selected_input"] = url
            await auto_proceed(update, context, "No video tracks. Using master URL.")
            return RTMP_BASE
    except Exception as e:
        context.user_data["selected_input"] = url
        await auto_proceed(update, context, f"Error: {e}. Using direct URL.")
        return RTMP_BASE

async def get_mpd_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mpd_url"] = update.message.text.strip()
    asyncio.create_task(update.message.delete())

    msg_id = context.user_data["delete_queue"].pop()
    try:
        await update.effective_chat.delete_message(msg_id)
    except:
        pass

    msg = await update.effective_chat.send_message("Send DRM Key (KID:KEY):", parse_mode="Markdown")
    context.user_data["delete_queue"].append(msg.message_id)
    return DRM_KEY

async def get_drm_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["drm_key"] = update.message.text.strip()
    asyncio.create_task(update.message.delete())

    msg_id = context.user_data["delete_queue"].Ipop()
    try:
        await update.effective_chat.delete_message(msg_id)
    except:
        pass

    msg = await update.effective_chat.send_message("Detecting MPD qualities...")
    context.user_data["delete_queue"].append(msg.message_id)
    await detect_mpd_qualities(update, context)
    return QUALITY

async def detect_mpd_qualities(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = context.user_data["mpd_url"]
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", url,
            stdout=asyncio.subprocess.PIPE, timeout=15
        )
        stdout, _ = await proc.communicate()
        data = json.loads(stdout)
        qualities = []
        for i, stream in enumerate(data.get("streams", [])):
            if stream.get("codec_type") == "video":
                w = stream.get("width")
                h = stream.get("height")
                br = stream.get("bit_rate")
                if w and h:
                    label = f"{w}x{h}"
                    bw = int(br) // 1000 if br else 0
                    qualities.append((label, bw, i))

        if len(qualities) == 1:
            context.user_data["selected_input"] = url
            context.user_data["map_index"] = qualities[0][2]
            context.user_data["qualities"] = []
            await auto_proceed(update, context, "Only one quality. Using it.")
            return RTMP_BASE
        elif len(qualities) > 1:
            context.user_data["qualities"] = qualities
            await show_quality_buttons(update, context)
        else:
            context.user_data["selected_input"] = url
            await auto_proceed(update, context, "No video tracks. Using full MPD.")
            return RTMP_BASE
    except Exception as e:
        context.user_data["selected_input"] = url
        await auto_proceed(update, context, f"Error: {e}. Using full MPD.")
        return RTMP_BASE

async def auto_proceed(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    msg_id = context.user_data["delete_queue"].pop()
    try:
        await update.effective_chat.delete_message(msg_id)
    except:
        pass
    msg = await update.effective_chat.send_message(text)
    context.user_data["delete_queue"].append(msg.message_id)
    await asyncio.sleep(1.5)
    await ask_rtmp_base(update, context)

async def show_quality_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_id = context.user_data["delete_queue"].pop()
    try:
        await update.effective_chat.delete_message(msg_id)
    except:
        pass

    qualities = context.user_data["qualities"]
    keyboard = []
    for label, bw, _ in qualities:
        text = f"{label} – {bw} kbps" if bw else label
        keyboard.append([InlineKeyboardButton(text, callback_data=f"q_{len(keyboard)}")])
    msg = await update.effective_chat.send_message("Choose quality:", reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data["delete_queue"].append(msg.message_id)
    return QUALITY

async def choose_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split("_")[1])
    qualities = context.user_data["qualities"]
    label, bw, extra = qualities[idx]

    if context.user_data["input_type"] == "m3u8":
        context.user_data["selected_input"] = extra
    else:
        context.user_data["selected_input"] = context.user_data["mpd_url"]
        context.user_data["map_index"] = extra

    msg_id = context.user_data["delete_queue"].pop()
    try:
        await query.message.delete()
    except:
        pass

    await ask_rtmp_base(update, context)
    return RTMP_BASE

async def ask_rtmp_base(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    drm_key = context.user_data.get("drm_key")
    map_index = context.user_data.get("map_index")

    sid = manager.new_id()
    stream = Stream(sid, input_url, rtmp, title, input_type, drm_key, map_index)
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
        asyncio.create_task(delete_message(update.effective_chat.id, msg.message_id, context.bot))
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
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("type_"):
        return await choose_input_type(update, context)
    if query.data.startswith("q_"):
        return await choose_quality(update, context)
    if not query.data.startswith("stop_"):
        return

    sid = query.data[5:]
    stream = manager.get(sid)
    if not stream:
        await query.edit_message_text("Stream already stopped.")
        return

    uptime = stream.uptime()
    title = stream.title

    await stream.stop()
    manager.remove(sid)

    await query.message.delete()
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
            INPUT_TYPE: [CallbackQueryHandler(choose_input_type, "^type_")],
            M3U8_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_m3u8_url)],
            MPD_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_mpd_url)],
            DRM_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_drm_key)],
            QUALITY: [CallbackQueryHandler(choose_quality, "^q_")],
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
