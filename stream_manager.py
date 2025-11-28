# stream_manager.py
import os
import uuid
import datetime
import subprocess

STREAM_DIR = "/home/user/tgtv/streams"
os.makedirs(STREAM_DIR, exist_ok=True)

class Stream:
    def __init__(self, stream_id: str, input_url: str, rtmp: str, title: str, input_type: str):
        self.id = stream_id
        self.input_url = input_url
        self.rtmp = rtmp
        self.title = title
        self.input_type = input_type
        self.start_time = datetime.datetime.utcnow()
        self.script_path = f"{STREAM_DIR}/{stream_id}.sh"
        self.log_path = f"{STREAM_DIR}/{stream_id}.log"
        self.process = None

    def start(self):
        loop_flag = "-stream_loop -1" if self.input_type == "yt" else ""
        script = f'''#!/bin/bash
echo "[{self.id}] Starting stream..." > "{self.log_path}"
while true; do
  ffmpeg -analyzeduration 1000000 -probesize 1000000 -re -i "{self.input_url}" {loop_flag} \\
    -c:v libx264 -preset veryfast -tune zerolatency \\
    -b:v 4500k -maxrate 5000k -bufsize 10000k \\
    -g 30 -keyint_min 30 -r 30 -pix_fmt yuv420p \\
    -c:a aac -b:a 128k -ar 44100 \\
    -af "aresample=async=1:first_pts=0" \\
    -f flv -flvflags +add_keyframe_index \\
    "{self.rtmp}" >> "{self.log_path}" 2>&1
  echo "[{self.id}] FFmpeg crashed. Restarting in 2s..." >> "{self.log_path}"
  sleep 2
done
'''
        with open(self.script_path, "w") as f:
            f.write(script)
        os.chmod(self.script_path, 0o755)
        self.process = subprocess.Popen([self.script_path])

    def stop(self):
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(5)
            except:
                self.process.kill()
        if os.path.exists(self.script_path):
            os.unlink(self.script_path)
        if os.path.exists(self.log_path):
            os.unlink(self.log_path)

    def uptime(self) -> str:
        delta = datetime.datetime.utcnow() - self.start_time
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        return f"{h:02}h {m:02}m {s:02}s"

    def is_running(self):
        return self.process and self.process.poll() is None


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
        return [s for s in self.streams.values() if s.is_running()]
