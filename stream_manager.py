# stream_manager.py
import asyncio
import subprocess
import datetime
import os
import uuid

THUMB_DIR = "/tmp/tgtv_thumbs"
os.makedirs(THUMB_DIR, exist_ok=True)

class Stream:
    def __init__(self, stream_id: str, m3u8: str, rtmp: str, title: str):
        self.id = stream_id
        self.m3u8 = m3u8
        self.rtmp = rtmp
        self.title = title
        self.start_time = datetime.datetime.utcnow()
        self.process = None
        self.thumb_path = f"{THUMB_DIR}/thumb_{stream_id}.jpg"
        self.thumb_task = None

    async def take_thumbnail(self):
        if os.path.exists(self.thumb_path):
            os.unlink(self.thumb_path)
        cmd = [
            "ffmpeg", "-y", "-i", self.m3u8,
            "-vframes", "1", "-ss", "3",
            "-s", "640x360", "-q:v", "2",
            self.thumb_path
        ]
        proc = await asyncio.create_subprocess_exec(*cmd)
        await proc.wait()

    async def start(self):
        cmd = [
            "ffmpeg", "-y", "-re", "-i", self.m3u8,
            "-c:v", "libx264", "-preset", "veryfast",
            "-b:v", "4500k", "-maxrate", "5000k", "-bufsize", "10000k",
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
            try:
                self.thumb_task.cancel()
            except:
                pass
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

    def new_id(self):
        return str(uuid.uuid4())[:8]

    def add(self, stream: Stream):
        self.streams[stream.id] = stream

    def get(self, stream_id: str) -> Stream | None:
        return self.streams.get(stream_id)

    def remove(self, stream_id: str):
        self.streams.pop(stream_id, None)

    def all(self):
        return list(self.streams.values())
