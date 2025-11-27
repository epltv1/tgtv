# utils.py
import psutil
import datetime
import asyncio
import aiofiles
from PIL import Image
from io import BytesIO
import os
import subprocess
import re

# ——— YOUR ORIGINAL CODE ———
def format_bytes(b: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if b < 1024:
            return f"{b:.2f} {unit}"
        b /= 1024
    return f"{b:.2f} PB"

async def get_system_stats():
    uptime = datetime.datetime.now() - datetime.datetime.fromtimestamp(psutil.boot_time())
    d = uptime.days
    h, rem = divmod(uptime.seconds, 3600)
    m, s = divmod(rem, 60)
    uptime_str = f"{d}d {h:02}h {m:02}m {s:02}s"

    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    return (
        f"Uptime: {uptime_str}\n"
        f"RAM: {mem.percent}% ({format_bytes(mem.used)} / {format_bytes(mem.total)})\n"
        f"CPU: {psutil.cpu_percent(interval=1)}%\n"
        f"Disk: {disk.percent}% ({format_bytes(disk.used)} / {format_bytes(disk.total)})"
    )

async def take_screenshot(ffmpeg_pipe, width=640, height=360):
    try:
        async with aiofiles.open(ffmpeg_pipe, "rb") as f:
            data = await f.read()
        img = Image.open(BytesIO(data))
        img = img.resize((width, height), Image.LANCZOS)
        bio = BytesIO()
        img.save(bio, format="JPEG", quality=85)
        bio.seek(0)
        return bio
    except Exception:
        return None

# ——— OUR ADDITIONS ———
async def run_command(cmd):
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    return stdout.decode().strip(), stderr.decode().strip(), proc.returncode

def ensure_dirs():
    os.makedirs("/tmp/tgtv_thumbs", exist_ok=True)

def is_valid_url(url: str) -> bool:
    regex = re.compile(
        r'^(?:http|ftp)s?://'
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'
        r'localhost|'
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r'(?::\d+)?'
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return re.match(regex, url) is not None
