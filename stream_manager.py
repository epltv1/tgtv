import asyncio
import subprocess
import datetime
import os
from typing import Dict, Optional
from utils import take_screenshot

LOGO_URL = "https://i.postimg.cc/SsLmMd8K/101-170x85.png"
LOGO_PATH = "/tmp/tgtv_logo.png"

class Stream:
    def __init__(self, stream_id: str, m3u8: str, rtmp_url: str, title: str, overlay: bool):
        self.id = stream_id
        self.m3u8 = m3u8
        self.rtmp = rtmp_url
        self.title = title
        self.overlay = overlay
        self.start_time = datetime.datetime.utcnow()
        self.process: Optional[asyncio.subprocess.Process] = None
        self.screenshot_pipe_path = f"/tmp/tgtv_screenshot_{stream_id}.pipe"
        self.screenshot_task: Optional[asyncio.Task] = None

    async def _download_logo(self):
        if not os.path.exists(LOGO_PATH):
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(LOGO_URL) as resp:
                    data = await resp.read()
                    async with aiofiles.open(LOGO_PATH, "wb") as f:
                        await f.write(data)

    async def start(self):
        await self._download_logo()

        # Create named pipe for continuous screenshots
        if os.path.exists(self.screenshot_pipe_path):
            os.unlink(self.screenshot_pipe_path)
        os.mkfifo(self.screenshot_pipe_path)

        # Build FFmpeg command
        cmd = [
            "ffmpeg",
            "-re", "-i", self.m3u8,
            "-vf", f"format=yuv420p,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2"
        ]

        if self.overlay:
            cmd += [
                "-i", LOGO_PATH,
                "-filter_complex",
                "[0:v][1:v]overlay=W-w-10:10"
            ]

        cmd += [
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
            "-b:v", "4500k", "-maxrate", "4500k", "-bufsize", "9000k",
            "-g", "60", "-r", "30",
            "-c:a", "aac", "-b:a", "128k",
            "-f", "flv", self.rtmp,
            # Continuous screenshot pipe
            "-f", "image2pipe", "-vframes", "1", "-q:v", "3",
            "-update", "1", self.screenshot_pipe_path
        ]

        self.process = await asyncio.create_subprocess_exec(*cmd)

        # Start screenshot refresher (every 1 sec)
        self.screenshot_task = asyncio.create_task(self._screenshot_refresher())

    async def _screenshot_refresher(self):
        while True:
            await asyncio.sleep(1)  # FFmpeg already writes every second

    async def get_screenshot(self):
        return await take_screenshot(self.screenshot_pipe_path)

    def uptime(self) -> str:
        delta = datetime.datetime.utcnow() - self.start_time
        h, rem = divmod(delta.seconds, 3600)
        m, s = divmod(rem, 60)
        return f"{delta.days:02}d {h:02}h {m:02}m {s:02}s"

    async def stop(self):
        if self.screenshot_task:
            self.screenshot_task.cancel()
        if self.process:
            self.process.terminate()
            await self.process.wait()
        if os.path.exists(self.screenshot_pipe_path):
            os.unlink(self.screenshot_pipe_path)


class StreamManager:
    def __init__(self):
        self.streams: Dict[str, Stream] = {}

    def new_id(self) -> str:
        import uuid
        return str(uuid.uuid4())[:8]

    def add(self, stream: Stream):
        self.streams[stream.id] = stream

    def get(self, sid: str) -> Optional[Stream]:
        return self.streams.get(sid)

    def remove(self, sid: str):
        self.streams.pop(sid, None)

    def all(self):
        return list(self.streams.values())
