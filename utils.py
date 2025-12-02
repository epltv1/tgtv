# utils.py
import psutil
import datetime
import asyncio
import os

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

def ensure_dirs():
    os.makedirs("/home/user/tgtv/streams", exist_ok=True)
