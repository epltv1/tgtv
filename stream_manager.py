# stream_manager.py
import os
import uuid
import datetime
import subprocess
import threading
import time
import asyncio

class Stream:
    def __init__(self, stream_id: str, input_url: str, rtmp: str, title: str, input_type: str, bot, log_file=None):
        self.id = stream_id
        self.input_url = input_url
        self.rtmp = rtmp
        self.title = title
        self.input_type = input_type
        self.start_time = datetime.datetime.utcnow()
        self.process = None
        self.thread = None
        self.running = False
        self.bot = bot
        self.chat_id = None
        self.log_file = log_file

    def set_chat_id(self, chat_id):
        self.chat_id = chat_id

    def _run_ffmpeg(self):
        while self.running:
            cmd = [
                "ffmpeg",
                "-analyzeduration", "1000000",
                "-probesize", "1000000",
                "-re", "-i", self.input_url,
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-b:v", "1200k",
                "-maxrate", "1400k",
                "-bufsize", "2000k",
                "-c:a", "aac",
                "-b:a", "128k",
                # REMOVED: -vf "scale=-1:720,fps=15"
                "-f", "flv",
                self.rtmp
            ]

            print(f"[{self.id}] STARTING: {' '.join(cmd)} >> {self.log_file}")

            with open(self.log_file, "w") as log:
                log.write(f"[{datetime.datetime.utcnow()}] STREAM STARTED: {self.title}\n")
                log.write(f"RTMP: {self.rtmp}\n")
                log.write(f"INPUT: {self.input_url}\n")
                log.write("-" * 50 + "\n")
                log.flush()

                proc = subprocess.Popen(
                    cmd,
                    stdout=log,
                    stderr=log,
                    text=True
                )
            self.process = proc

            # Wait for exit
            proc.wait()

            if not self.running:
                break

            # Auto-restart after 1 second
            with open(self.log_file, "a") as log:
                log.write(f"\n[{datetime.datetime.utcnow()}] FFMPEG STOPPED. RESTARTING IN 1s...\n")
                log.write("-" * 50 + "\n")
                log.flush()

            time.sleep(1)

    def start(self):
        if self.running: return
        self.running = True
        self.thread = threading.Thread(target=self._run_ffmpeg, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.process:
            self.process.terminate()
            try: self.process.wait(3)
            except: self.process.kill()

    def uptime(self):
        delta = datetime.datetime.utcnow() - self.start_time
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        return f"{h:02}h {m:02}m {s:02}s"

    def is_running(self):
        return self.running and self.process and self.process.poll() is None


class StreamManager:
    def __init__(self):
        self.streams = {}
    def new_id(self): return str(uuid.uuid4())[:8]
    def add(self, s): self.streams[s.id] = s
    def get(self, sid): return self.streams.get(sid)
    def remove(self, sid): self.streams.pop(sid, None)
    def all(self):
        dead = [sid for sid, s in self.streams.items() if not s.is_running()]
        for sid in dead: del self.streams[sid]
        return list(self.streams.values())
