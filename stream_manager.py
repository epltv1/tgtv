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

    def _run_gstreamer(self):
        while self.running:
            cmd = [
                "gst-launch-1.0", "-e",
                "souphttpsrc", f"location={self.input_url}", "is-live=true",
                "!", "hlsdemux",
                "!", "decodebin", "name=dec",
                "dec.", "!", "queue", "!", "videoconvert", "!", 
                "x264enc", "bitrate=4500", "speed-preset=veryfast", "tune=zerolatency", "key-int=30",
                "!", "video/x-h264,stream-format=byte-stream",
                "!", "flvmux", "streamable=true", "name=mux",
                "dec.", "!", "queue", "!", "audioconvert", "!", "audioresample", "!", 
                "aacenc", "bitrate=128000",
                "!", "mux.",
                "mux.", "!", "rtmpsink", f"location={self.rtmp}"
            ]

            if self.input_type == "yt":
                # For YouTube, use playbin with loop
                cmd = [
                    "gst-launch-1.0", "-e",
                    "playbin", f"uri={self.input_url}", "flags=0x10",
                    "video-sink=videoconvert ! x264enc bitrate=4500 speed-preset=veryfast tune=zerolatency key-int=30 ! flvmux streamable=true ! rtmpsink location=" + self.rtmp,
                    "audio-sink=audioconvert ! audioresample ! aacenc bitrate=128000 ! flvmux streamable=true ! rtmpsink location=" + self.rtmp
                ]

            proc = subprocess.Popen(
                " ".join(cmd),
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )
            self.process = proc
            proc.wait()

            if not self.running:
                break

            # Notify crash
            if self.chat_id and self.bot:
                try:
                    asyncio.create_task(
                        self.bot.send_message(
                            chat_id=self.chat_id,
                            text=f"*Stream Stopped*\n\n"
                                 f"Title: `{self.title}`\n"
                                 f"ID: `{self.id}`\n"
                                 f"Reason: Connection lost",
                            parse_mode="Markdown"
                        )
                    )
                except:
                    pass

            print(f"[STREAM {self.id}] Reconnecting in 3s...")
            time.sleep(3)

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_gstreamer, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(5)
            except:
                self.process.kill()

    def uptime(self) -> str:
        delta = datetime.datetime.utcnow() - self.start_time
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        return f"{h:02}h {m:02}m {s:02}s"

    def is_running(self):
        return self.running and self.process and self.process.poll() is None


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
        dead = [sid for sid, s in self.streams.items() if not s.is_running()]
        for sid in dead:
            del self.streams[sid]
        return list(self.streams.values())
