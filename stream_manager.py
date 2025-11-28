# stream_manager.py
import asyncio
import subprocess
import datetime
import os
import uuid

THUMB_DIR = "/tmp/tgtv_thumbs"
os.makedirs(THUMB_DIR, exist_ok=True)

class Stream:
    def __init__(self, stream_id: str, input_url: str, rtmp: str, title: str, input_type: str):
        self.id = stream_id
        self.input_url = input_url
        self.rtmp = rtmp
        self.title = title
        self.input_type = input_type
        self.start_time = datetime.datetime.utcnow()
        self.process = None
        self.thumb_path = f"{THUMB_DIR}/thumb_{stream_id}.jpg"
        self.thumb_task = None
        self.monitor_task = None

    async def take_thumbnail(self):
        if os.path.exists(self.thumb_path):
            os.unlink(self.thumb_path)

        cmd = [
            "ffmpeg", "-y", "-i", self.input_url,
            "-vframes", "1", "-ss", "5", "-s", "640x360",
            "-q:v", "3", "-f", "image2", self.thumb_path
        ]

        proc = await asyncio.create_subprocess_exec(*cmd)
        try:
            await asyncio.wait_for(proc.wait(), timeout=10)
        except asyncio.TimeoutError:
            proc.kill()
            print(f"[STREAM {self.id}] Thumbnail timeout → skipped")

    async def start(self):
        cmd = [
            "ffmpeg", "-y",
            "-fflags", "+genpts+nobuffer", "-avoid_negative_ts", "make_zero",
            "-itsoffset", "0.0", "-copyts", "-start_at_zero"
        ]

        if self.input_type == "yt":
            cmd += ["-stream_loop", "-1"]

        cmd += [
            "-re", "-i", self.input_url,
            "-map", "0:v", "-map", "0:a",
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
            "-g", "30", "-keyint_min", "30", "-sc_threshold", "0",
            "-r", "30", "-pix_fmt", "yuv420p",
            "-b:v", "4500k", "-maxrate", "4500k", "-bufsize", "9000k",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            "-af", "aresample=async=1:first_pts=0",
            "-f", "flv", "-flvflags", "+add_keyframe_index",
            "-rtmp_buffer", "1000", "-rtmp_live", "live",
            self.rtmp
        ]

        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        self.thumb_task = asyncio.create_task(self.take_thumbnail())
        self.monitor_task = asyncio.create_task(self._monitor())

    async def _monitor(self):
        while True:
            if self.process.returncode is not None:
                print(f"[STREAM {self.id}] FFmpeg died → RESTARTING")
                await asyncio.sleep(3)
                await self.start()
                return

            line = await self.process.stderr.readline()
            if not line:
                continue

            line = line.decode().strip()
            if any(err in line for err in ["Broken pipe", "Conversion failed", "Timeout", "403", "reset"]):
                print(f"[STREAM {self.id}] RTMP ERROR → RESTART")
                await self.stop()
                await asyncio.sleep(3)
                await self.start()
                return

    def uptime(self) -> str:
        delta = datetime.datetime.utcnow() - self.start_time
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        return f"{h:02}h {m:02}m {s:02}s"

    async def stop(self):
        if self.thumb_task and not self.thumb_task.done():
            self.thumb_task.cancel()
        if self.monitor_task and not self.monitor_task.done():
            self.monitor_task.cancel()
        if self.process and self.process.returncode is None:
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
