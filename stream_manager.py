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

class Stream:
    def __init__(self, stream_id: str, m3u8: str, rtmp: str, title: str, overlay: bool):
        self.id = stream_id
        self.m3u8 = m3u8
        self.rtmp = rtmp
        self.title = title
        self.overlay = overlay
        self.start_time = datetime.datetime.utcnow()
        self.process = None
        self.pipe_path = f"/tmp/tgtv_pipe_{stream_id}"
        self.reader_task = None
        self.latest_frame = None
        self.frame_lock = asyncio.Lock()

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

    async def _frame_reader(self):
        try:
            async with aiofiles.open(self.pipe_path, "rb") as f:
                buffer = bytearray()
                while True:
                    chunk = await f.read(8192)
                    if not chunk:
                        break
                    buffer.extend(chunk)
                    # Find JPEG
                    start = buffer.find(b'\xff\xd8')
                    end = buffer.find(b'\xff\xd9', start)
                    if start != -1 and end != -1:
                        frame = buffer[start:end+2]
                        async with self.frame_lock:
                            self.latest_frame = bytes(frame)
                        buffer = buffer[end+2:]
                    await asyncio.sleep(0.05)
        except Exception as e:
            print(f"Reader error: {e}")

    async def start(self):
        await self._download_logo()
        if os.path.exists(self.pipe_path):
            os.unlink(self.pipe_path)
        os.mkfifo(self.pipe_path)

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
            "-f", "flv", self.rtmp,
            "-an", "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "3",
            "-vf", "fps=1", self.pipe_path
        ]

        self.process = await asyncio.create_subprocess_exec(*cmd)
        self.reader_task = asyncio.create_task(self._frame_reader())

    async def get_screenshot(self) -> BytesIO | None:
        async with self.frame_lock:
            if not self.latest_frame:
                return None
            try:
                img = Image.open(BytesIO(self.latest_frame))
                img = img.resize((640, 360), Image.Resampling.LANCZOS)
                bio = BytesIO()
                img.save(bio, "JPEG", quality=80)
                bio.seek(0)
                return bio
            except:
                return None

    def uptime(self) -> str:
        delta = datetime.datetime.utcnow() - self.start_time
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        return f"{h:02}h {m:02}m {s:02}s"

    async def stop(self):
        if self.reader_task:
            self.reader_task.cancel()
        if self.process:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 8)
            except:
                self.process.kill()
        if os.path.exists(self.pipe_path):
            os.unlink(self.pipe_path)


class StreamManager:
    def __init__(self):
        self.streams = {}

    def new_id(self): return str(uuid.uuid4())[:8]
    def add(self, s): self.streams[s.id] = s
    def get(self, sid): return self.streams.get(sid)
    def remove(self, sid): self.streams.pop(sid, None)
    def all(self): return list(self.streams.values())
