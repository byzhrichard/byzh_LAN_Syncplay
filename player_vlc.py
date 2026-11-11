import sys
import os
import socket
import threading
import subprocess
import time
import shutil

def auto_detect_vlc():
    which_path = shutil.which("vlc")
    if which_path and os.path.isfile(which_path):
        return which_path

    common_paths = [
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
        r"D:\Program Files\VideoLAN\VLC\vlc.exe",
        r"D:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
    ]
    for p in common_paths:
        if os.path.isfile(p):
            return p

    if sys.platform == "win32":
        import winreg
        for root_key, sub_key in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\VideoLAN\VLC"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\VideoLAN\VLC")
        ]:
            try:
                with winreg.OpenKey(root_key, sub_key) as key:
                    install_dir, _ = winreg.QueryValueEx(key, "InstallDir")
                    exe_path = os.path.join(install_dir, "vlc.exe")
                    if os.path.isfile(exe_path):
                        return exe_path
            except Exception:
                pass
    return ""

class VLCController:
    def __init__(self, port=4212):
        self.port = port
        self.sock = None
        self.process = None
        self.lock = threading.Lock()

    def is_alive(self):
        return self.process is not None and self.process.poll() is None

    def launch_and_connect(self, vlc_path, video_file):
        abs_video_path = os.path.abspath(video_file)
        cmd = [
            vlc_path,
            abs_video_path,
            "--start-paused",
            "--no-qt-privacy-ask",
            "--no-one-instance",
            "--extraintf", "rc",
            "--rc-host", f"127.0.0.1:{self.port}",
            "--rc-quiet"
        ]
        try:
            self.process = subprocess.Popen(cmd)
        except Exception as e:
            return False, f"VLC 启动异常: {e}"
        
        for _ in range(30):
            time.sleep(0.3)
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.connect(("127.0.0.1", self.port))
                self.sock.settimeout(0.3)
                return True, "连接成功"
            except Exception:
                continue
        return False, "连接超时，VLC 未开启控制接口。"

    def send(self, cmd):
        with self.lock:
            if self.sock:
                try:
                    self.sock.sendall(f"{cmd}\n".encode('utf-8'))
                except Exception:
                    pass

    def query_int(self, cmd):
        with self.lock:
            if not self.sock: return 0
            try:
                self.sock.setblocking(False)
                try:
                    while self.sock.recv(1024): pass
                except Exception: pass
                self.sock.setblocking(True)
                self.sock.settimeout(0.25)
                self.sock.sendall(f"{cmd}\n".encode('utf-8'))
                res = self.sock.recv(1024).decode('utf-8', errors='ignore')
                for line in res.splitlines():
                    clean = line.replace(">", "").strip()
                    if clean.isdigit(): return int(clean)
            except Exception: pass
            return 0

    def is_playing(self):
        return self.query_int("is_playing") == 1

    def get_time(self):
        return self.query_int("get_time")

    def get_length(self):
        return self.query_int("get_length")

    def seek(self, seconds):
        self.send(f"seek {int(seconds)}")

    def relative_seek(self, delta):
        curr_t = self.get_time()
        self.seek(max(0, curr_t + delta))

    def frame_step(self):
        self.send("frame")

    def ensure_pause(self):
        if self.is_playing(): self.send("pause")

    def ensure_play(self):
        if not self.is_playing(): self.send("pause")

    def show_osd(self, text, duration_ms=3500):
        # VLC 尝试通过 str 命令输出字幕
        self.send(f"str {text}")

    def close(self):
        with self.lock:
            if self.sock:
                try: self.sock.close()
                except: pass
            if self.process:
                try: self.process.terminate()
                except: pass
        self.sock = None
        self.process = None