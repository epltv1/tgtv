# stream_manager.py
import asyncio
import subprocess
import datetime
import os
import uuid
import aiofiles
from PIL import Image
from io import BytesIO

LOGO_URL = "https://i.postimg.cc/SsLmMd8K/101-170x85.png"
LOGO_PATH = "/tmp/tgtv_logo.png"
THUMB_DIR = "/tmp/tgtv_thumbs"
os.makedirs(THUMB_DIR, exist_ok=True)

class Stream:
    def __init__(self, stream_id: str, m3u8: str, rtmp: str, title: str, overlay: bool):
        self.id = stream_id
        self.m3u8 = m3u8
        self.rtmp = rtmp
        self.title = title
        self.overlay = overlay
        self.start_time = datetime.datetime.utcnow()
        self.process = None
        self.thumb_path = f"{THUMB_DIR}/thumb_{stream_id}.jpg"
        self.thumb_task = None

    async def _download_logo(self):
        if os.path.exists(LOGO_PATH):
            return
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(LOGO_URL) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    async with aiofiles.open(LOGO_PATH, "wb") as f:
                        await f.write(data)

    async def take_thumbnail(self):
        if os.path.exists(self.thumb_path):
            os.unlink(self.thumb_path)
        cmd = [
            "ffmpeg", "-y", "-i", self.m3u8,
            "-vframes", "1", "-ss", "3", "-q:v", "2",
            "-s", "640x360", self.thumb_path
        ]
        proc = await asyncio.create_subprocess_exec(*cmd)
        await proc.wait()

    async def start(self):
        await self._download_logo()

        vf = "format=yuv420p,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2"
        if self.overlay:
            vf += f",movie={LOGO_PATH}[l];[in][l]overlay=W-w-10:10"

        cmd = [
            "ffmpeg", "-y", "-re", "-i", self.m3u8,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
            "-b:v", "4500k", "-maxrate", "5000k", "-bufsize", "10000k",
            "-r", "30", "-g", "30",
            "-c:a", "aac", "-b:a", "128k",
            "-f", "flv", self.rtmp
        ]

        self.process = await asyncio.create_subprocess_exec(*cmd)
        self.thumb_task = asyncio.create_task(self.take_thumbnail())

    def uptime(self) -> str:
        delta = datetime.datetime.utcnow() - self.start_time
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        return f"{h:02}h {m:02}m {s:02}s"

    async def stop(self):
        if self.thumb_task:
            self.thumb_task.cancel()
        if self.process:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 5)
            except:
                self.process.kill()
        if os.path.exists(self.thumb_path):
            os.unlink(self.thumb_path)


class StreamManager:
    def __init__(self):
        self.streams = {}

    def new_id(self): return str(uuid.uuid4())[:8]
    def add(self, s): self.streams[s.id] = s
    def get(self, sid): return self.streams.get(sid)
    def remove(self, sid): self.streams.pop(sid, None)
    def all(self): return list(self.streams.values())
