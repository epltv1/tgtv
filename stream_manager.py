# stream_manager.py
import asyncio
import subprocess
import datetime
import os
import uuid

THUMB_DIR = "/tmp/tgtv_thumbs"
os.makedirs(THUMB_DIR, exist_ok=True)

class Stream:
    def __init__(self, stream_id: str, input_url: str, rtmp: str, title: str, input_type: str, logo_url=None, logo_pos=None):
        self.id = stream_id
        self.input_url = input_url
        self.rtmp = rtmp
        self.title = title
        self.input_type = input_type
        self.logo_url = logo_url
        self.logo_pos = logo_pos
        self.start_time = datetime.datetime.utcnow()
        self.process = None
        self.thumb_path = f"{THUMB_DIR}/thumb_{stream_id}.jpg"
        self.thumb_task = None
        self.monitor_task = None

    async def take_thumbnail(self):
        if os.path.exists(self.thumb_path):
            os.unlink(self.thumb_path)
        cmd = ["ffmpeg", "-y", "-i", self.input_url, "-vframes", "1", "-ss", "3", "-s", "640x360", "-q:v", "2", self.thumb_path]
        proc = await asyncio.create_subprocess_exec(*cmd)
        await proc.wait()

    async def start(self):
        # Base command
        cmd = [
            "ffmpeg", "-y",
            "-fflags", "+genpts", "-stream_loop", "-1", "-re", "-i", self.input_url,
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
            "-g", "30", "-keyint_min", "30",
            "-b:v", "4500k", "-maxrate", "5000k", "-bufsize", "10000k",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            "-f", "flv", "-rtmp_buffer", "1000", "-rtmp_live", "live",
            "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "10",
            self.rtmp
        ]

        # === LOGO OVERLAY ONLY IF LOGO EXISTS ===
        if self.logo_url and self.logo_pos:
            # Determine position
            if self.logo_pos == "top_left":
                overlay = "10:10"
            elif self.logo_pos == "top_right":
                overlay = "main_w-overlay_w-10:10"
            elif self.logo_pos == "bottom_left":
                overlay = "10:main_h-overlay_h-10"
            elif self.logo_pos == "bottom_right":
                overlay = "main_w-overlay_w-10:main_h-overlay_h-10"

            # Insert logo input and filter
            cmd.insert(2, "-i")
            cmd.insert(3, self.logo_url)
            cmd.insert(4, "-filter_complex")
            cmd.insert(5, f"[0:v][1:v]overlay={overlay}[v]")
            cmd.insert(6, "-map")
            cmd.insert(7, "[v]")
            cmd.insert(8, "-map")
            cmd.insert(9, "0:a")
        else:
            # NO LOGO → Clean mapping
            cmd.insert(2, "-map")
            cmd.insert(3, "0:v")
            cmd.insert(4, "-map")
            cmd.insert(5, "0:a")

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
                break
            line = await self.process.stderr.readline()
            if not line:
                break
            line = line.decode().strip()
            if any(x in line for x in ["Connection timed out", "Server error", "Failed to connect"]):
                print(f"[STREAM {self.id}] RTMP DISCONNECTED → RESTARTING")
                await self.stop()
                await asyncio.sleep(2)
                await self.start()
                return
        await self._on_exit()

    async def _on_exit(self):
        pass

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
        if self.monitor_task:
            try:
                self.monitor_task.cancel()
            except:
                pass
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
