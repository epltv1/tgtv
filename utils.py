# utils.py
import psutil
import datetime
import asyncio
import subprocess
import re
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
    os.makedirs("/tmp/tgtv_thumbs", exist_ok=True)
    os.makedirs("/home/user/tgtv/streams", exist_ok=True)

# UNIVERSAL RESOLVER
async def resolve_stream_url(url: str) -> str:
    """Resolve ANY link → playable stream (m3u8, ts, mp4, rtmp, dash, etc.)"""
    try:
        # 1. yt-dlp — BEST FOR .php, embed, YouTube, DASH, sites
        proc = await asyncio.create_subprocess_exec(
            "yt-dlp", "--get-url", "--format", "best[height<=1080]", url,
            stdout=asyncio.subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )
        stdout, _ = await proc.communicate()
        resolved = stdout.decode().strip()
        if resolved and resolved.startswith("http"):
            return resolved

        # 2. curl + grep for .ts, .m3u8, .mp4, rtmp in .php or embed
        if "play.php" in url or "embed" in url or "iframe" in url:
            proc = await asyncio.create_subprocess_exec(
                "curl", "-s", "-L", "--max-time", "10", url,
                stdout=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            text = stdout.decode()

            patterns = [
                r'(https?://[^"\']+\.m3u8[^"\']*)',
                r'(https?://[^"\']+\.ts[^"\']*)',
                r'(rtmps?://[^"\']+)',
                r'(https?://[^"\']+\.mp4[^"\']*)',
                r'src=[\'"](https?://[^\'"]+\.m3u8)',
                r'src=[\'"](https?://[^\'"]+\.ts)'
            ]
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return match.group(1)

    except Exception as e:
        print(f"[RESOLVE] Failed: {e}")

    # 3. Fallback: return original URL (FFmpeg might play it)
    return url
