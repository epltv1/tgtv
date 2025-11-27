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
        self.process: asyncio.subprocess.Process | None = None
        self.pipe_path = f"/tmp/tgtv_pipe_{stream_id}"
        self.reader_task: asyncio.Task | None = None
        self.latest_frame: bytes | None = None
        self.frame_lock = asyncio.Lock()

    async def _download_logo(self):
        if not os.path.exists(LOGO_PATH):
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
                while True:
                    buffer = bytearray()
                    soi_found = False
                    while True:
                        chunk = await f.read(1024)
                        if not chunk:
                            return
                        buffer.extend(chunk)
                        if not soi_found and b'\xff\xd8' in buffer:
                            soi_found = True
                        if soi_found and b'\xff\xd9' in buffer:
                            break
                    async with self.frame_lock:
                        self.latest_frame = bytes(buffer)
        except Exception as e:
            print(f"Frame reader error: {e}")

    async def start(self):
        await self._download_logo()

        if os.path.exists(self.pipe_path):
            os.unlink(self.pipe_path)
        os.mkfifo(self.pipe_path)

        vf_parts = [
            "format=yuv420p",
            "scale=1280:720:force_original_aspect_ratio=decrease",
            "pad=1280:720:(ow-iw)/2:(oh-ih)/2"
        ]
        if self.overlay:
            vf_parts.append(f"movie={LOGO_PATH} [logo]; [in][logo] overlay=W-w-10:10")
        vf = ",".join(vf_parts).replace("[in]", "")

        cmd = [
            "ffmpeg", "-y",
            "-re", "-i", self.m3u8,  # ← FIXED: was "self.m Broom3u8"
            "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
            "-b:v", "4500k", "-maxrate", "5000k", "-bufsize", "10000k",
            "-g", "60", "-r", "30",
            "-c:a", "aac", "-b:a", "128k",
            "-f", "flv", self.rtmp,
            "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "3",
            "-update", "1", self.pipe_path
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
                img.save(bio, format="JPEG", quality=85)
                bio.seek(0)
                return bio
            except Exception:
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
                await asyncio.wait_for(self.process.wait(), timeout=10)
            except asyncio.TimeoutError:
                self.process.kill()
        if os.path.exists(self.pipe_path):
            os.unlink(self.pipe_path)


class StreamManager:
    def __init__(self):
        self.streams: dict[str, Stream] = {}

    def new_id(self) -> str:
        return str(uuid.uuid4())[:8]

    def add(self, stream: Stream):
        self.streams[stream.id] = stream

    def get(self, sid: str) -> Stream | None:
        return self.streams.get(sid)

    def remove(self, sid: str):
        self.streams.pop(sid, None)

    def all(self):
        return list(self.streams.values())
