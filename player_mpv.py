import sys
import os
import json
import threading
import subprocess
import time
import shutil
import ctypes
if sys.platform == "win32":
    import msvcrt

def has_pipe_data(pipe_file):
    if sys.platform != "win32" or not pipe_file:
        return True
    try:
        handle = msvcrt.get_osfhandle(pipe_file.fileno())
        avail = ctypes.c_ulong(0)
        res = ctypes.windll.kernel32.PeekNamedPipe(handle, None, 0, None, ctypes.byref(avail), None)
        return res != 0 and avail.value > 0
    except Exception:
        return False

def auto_detect_mpv():
    which_path = shutil.which("mpv")
    if which_path and os.path.isfile(which_path):
        return which_path

    local_mpv = os.path.abspath("mpv.exe")
    if os.path.isfile(local_mpv):
        return local_mpv

    common_paths = [
        r"C:\Program Files\mpv\mpv.exe",
        r"C:\Program Files (x86)\mpv\mpv.exe",
        r"D:\mpv\mpv.exe",
        r"D:\Program Files\mpv\mpv.exe"
    ]
    for p in common_paths:
        if os.path.isfile(p):
            return p
    return ""

class MPVController:
    def __init__(self, pipe_name="mpv_syncplay_pipe"):
        self.pipe_path = f"\\\\.\\pipe\\{pipe_name}" if sys.platform == "win32" else f"/tmp/{pipe_name}"
        self.pipe = None
        self.process = None
        self.lock = threading.Lock()
        self.running = False

        self.is_paused = True
        self.time_pos = 0
        self.duration = 0

    def is_alive(self):
        return self.process is not None and self.process.poll() is None

    def launch_and_connect(self, mpv_path, video_file):
        abs_video_path = os.path.abspath(video_file)
        cmd = [
            mpv_path,
            abs_video_path,
            "--idle=yes",
            "--pause=yes",
            "--keep-open=yes",
            f"--input-ipc-server={self.pipe_path}"
        ]
        try:
            self.process = subprocess.Popen(cmd)
        except Exception as e:
            return False, f"mpv 启动异常: {e}"

        for _ in range(30):
            time.sleep(0.2)
            try:
                self.pipe = open(self.pipe_path, "r+b", buffering=0)
                self.running = True
                threading.Thread(target=self._ipc_listen_loop, daemon=True).start()

                self.send_command(["observe_property", 1, "pause"])
                self.send_command(["observe_property", 2, "time-pos"])
                self.send_command(["observe_property", 3, "duration"])
                return True, "连接成功"
            except Exception:
                continue
        return False, "连接 mpv 命名管道超时。"

    def send_command(self, cmd_list):
        with self.lock:
            if self.pipe:
                try:
                    payload = json.dumps({"command": cmd_list}) + "\n"
                    self.pipe.write(payload.encode("utf-8"))
                except Exception:
                    pass

    def _ipc_listen_loop(self):
        while self.running and self.pipe:
            try:
                if has_pipe_data(self.pipe):
                    line = self.pipe.readline()
                    if not line: break
                    msg = json.loads(line.decode("utf-8", errors="ignore").strip())
                    if msg.get("event") == "property-change":
                        name = msg.get("name")
                        data = msg.get("data")
                        if name == "pause":
                            self.is_paused = bool(data)
                        elif name == "time-pos" and data is not None:
                            self.time_pos = int(data)
                        elif name == "duration" and data is not None:
                            self.duration = int(data)
                else:
                    time.sleep(0.04)
            except Exception:
                break

    def is_playing(self):
        return not self.is_paused

    def get_time(self):
        return self.time_pos

    def get_length(self):
        return self.duration

    def ensure_pause(self):
        self.send_command(["set_property", "pause", True])

    def ensure_play(self):
        self.send_command(["set_property", "pause", False])

    def seek(self, seconds):
        self.send_command(["seek", seconds, "absolute"])

    def relative_seek(self, delta):
        self.send_command(["seek", delta, "relative"])

    def show_osd(self, text, duration_ms=3500):
        """原生悬浮弹幕：直接在视频画面上方展示文字"""
        self.send_command(["show-text", text, duration_ms])

    def close(self):
        self.running = False
        with self.lock:
            if self.pipe:
                try: self.pipe.close()
                except: pass
            if self.process:
                try: self.process.terminate()
                except: pass
        self.pipe = None
        self.process = None