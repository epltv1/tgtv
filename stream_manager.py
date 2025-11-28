# stream_manager.py
import asyncio
import subprocess
import datetime
import os
import uuid
import threading
import signal

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
        self.thread = None
        self.running = False

    def take_thumbnail(self):
        if os.path.exists(self.thumb_path):
            os.unlink(self.thumb_path)
        cmd = [
            "ffmpeg", "-y", "-i", self.input_url,
            "-vframes", "1", "-ss", "5", "-s", "640x360",
            "-q:v", "3", self.thumb_path
        ]
        try:
            subprocess.run(cmd, timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            pass

    def _run_ffmpeg(self):
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

        while self.running:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )
            self.process = proc

            # Monitor stderr
            for line in proc.stderr:
                if not proc.poll() is None:
                    break
                line = line.decode().strip()
                if any(err in line for err in ["Broken pipe", "Timeout", "403", "reset"]):
                    break

            proc.wait()
            if not self.running:
                break
            print(f"[STREAM {self.id}] Restarting in 3s...")
            asyncio.run_coroutine_threadsafe(asyncio.sleep(3), asyncio.get_event_loop())

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_ffmpeg, daemon=True)
        self.thread.start()
        threading.Thread(target=self.take_thumbnail, daemon=True).start()

    def stop(self):
        self.running = False
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(5)
            except:
                self.process.kill()
        if os.path.exists(self.thumb_path):
            os.unlink(self.thumb_path)

    def uptime(self) -> str:
        delta = datetime.datetime.utcnow() - self.start_time
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        return f"{h:02}h {m:02}m {s:02}s"


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
        return [s for s in self.streams.values() if s.running]
