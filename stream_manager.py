# stream_manager.py
import os
import uuid
import datetime
import subprocess
import threading
import time
import asyncio

class Stream:
    def __init__(self, stream_id: str, input_url: str, rtmp: str, title: str, input_type: str, bot):
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

    def set_chat_id(self, chat_id):
        self.chat_id = chat_id

    def _run_ffmpeg(self):
        while self.running:
            cmd = [
                "ffmpeg", "-y",
                "-fflags", "+genpts+discardcorrupt", "-flags", "+low_delay",
                "-reconnect", "1", "-reconnect_at_eof", "1",
                "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
                "-timeout", "30000000", "-rw_timeout", "30000000",
                "-multiple_requests", "1", "-probesize", "10000000", "-analyzeduration", "10000000"
            ]

            if self.input_type == "yt":
                cmd += ["-stream_loop", "-1"]

            cmd += [
                "-re", "-i", self.input_url,

                # === ADVANCED VIDEO: CRF 18, 4K, HIGH QUALITY ===
                "-c:v", "libx264",
                "-preset", "veryfast", "-tune", "zerolatency",
                "-profile:v", "high", "-level", "5.2",
                "-g", "30", "-keyint_min", "30", "-sc_threshold", "0",
                "-r", "30", "-pix_fmt", "yuv420p",
                "-crf", "18",           # ← EXCELLENT QUALITY
                "-maxrate:v", "35000k", # ← 4K SUPPORT
                "-bufsize:v", "70000k",

                # === AUDIO: STUDIO QUALITY ===
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-af", "aresample=async=1:min_hard_comp=0.001:first_pts=0",

                # === OUTPUT: SMOOTH FLV ===
                "-f", "flv",
                "-flvflags", "+add_keyframe_index",
                "-rtmp_buffer", "1000", "-rtmp_live", "live",
                "-thread_queue_size", "2048",
                self.rtmp
            ]

            print(f"[{self.id}] STARTING: {' '.join(cmd)}")

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True
            )
            self.process = proc

            for line in proc.stderr:
                if "error" in line.lower() or "failed" in line.lower():
                    print(f"[{self.id}] ERROR: {line.strip()}")
                elif "kb/s" in line:
                    print(f"[{self.id}] {line.strip()}")

            proc.wait()

            if not self.running:
                break

            if self.chat_id and self.bot:
                asyncio.create_task(
                    self.bot.send_message(
                        chat_id=self.chat_id,
                        text=f"Stream died. Restarting...\nID: `{self.id}`",
                        parse_mode="Markdown"
                    )
                )

            time.sleep(3)

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
