import psutil
import datetime
import asyncio
import aiofiles
from PIL import Image
from io import BytesIO

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
    """Read a single JPEG frame from FFmpeg pipe."""
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
