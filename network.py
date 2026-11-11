import sys
import json
import socket
import threading
import subprocess
import time
from PySide6.QtCore import Signal, QObject

class NetworkSignals(QObject):
    received = Signal(dict)
    connected = Signal(str)
    disconnected = Signal()

class SyncNetwork:
    """局域网/虚拟局域网 TCP 通信引擎"""
    def __init__(self, signals: NetworkSignals):
        self.signals = signals
        self.sock = None
        self.conn = None
        self.running = False

    def start_server(self, host_ip="0.0.0.0", port=8899):
        self.running = True
        threading.Thread(target=self._server_thread, args=(host_ip, port), daemon=True).start()

    def start_client(self, host_ip, port=8899):
        self.running = True
        threading.Thread(target=self._client_thread, args=(host_ip, port), daemon=True).start()

    def _server_thread(self, host_ip, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.bind((host_ip, port))
            self.sock.listen(1)
            while self.running:
                conn, addr = self.sock.accept()
                self.conn = conn
                self.signals.connected.emit(f"{addr[0]}")
                self._receive_loop(self.conn)
        except Exception: pass

    def _client_thread(self, host_ip, port):
        try:
            self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.conn.connect((host_ip, port))
            self.signals.connected.emit(f"{host_ip}")
            self._receive_loop(self.conn)
        except Exception:
            self.signals.disconnected.emit()

    def _receive_loop(self, conn):
        buf = ""
        while self.running:
            try:
                data = conn.recv(4096).decode('utf-8')
                if not data: break
                buf += data
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    if line.strip():
                        self.signals.received.emit(json.loads(line.strip()))
            except Exception: break
        self.signals.disconnected.emit()

    def send_cmd(self, action, t=0, sender="", extra=None):
        if self.conn:
            try:
                msg = {"action": action, "time": t, "sender": sender}
                if extra: msg.update(extra)
                self.conn.sendall((json.dumps(msg) + "\n").encode('utf-8'))
            except Exception: pass

    def is_connected(self):
        return self.conn is not None

    def close(self):
        self.running = False
        if self.conn:
            try: self.conn.close()
            except: pass
            self.conn = None
        if self.sock:
            try: self.sock.close()
            except: pass
            self.sock = None

# ----------------- Ping 诊断与测速功能 -----------------
class PingSignals(QObject):
    log_signal = Signal(str)
    finished_signal = Signal()

def run_icmp_ping(ip, signals: PingSignals):
    param = "-n" if sys.platform == "win32" else "-c"
    cmd = ["ping", param, "4", ip]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            if line.strip(): signals.log_signal.emit(line.strip())
    except Exception as e:
        signals.log_signal.emit(f"Ping 异常: {e}")
    signals.finished_signal.emit()

def run_tcp_ping(ip, port, signals: PingSignals):
    success = 0
    for i in range(1, 4):
        start = time.perf_counter()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2.0)
            s.connect((ip, port))
            s.close()
            elapsed = (time.perf_counter() - start) * 1000
            signals.log_signal.emit(f"第 {i} 次连接成功: 延迟 = {elapsed:.1f} ms")
            success += 1
        except ConnectionRefusedError:
            signals.log_signal.emit(f"第 {i} 次失败: 对方拒绝连接 (端口未开启，请确认房主已开启服务)")
        except socket.timeout:
            signals.log_signal.emit(f"第 {i} 次失败: 连接超时 (请确认填的是房主 IP，且未被防火墙拦截)")
        except Exception as e:
            signals.log_signal.emit(f"第 {i} 次失败: {e}")
        time.sleep(0.5)

    if success > 0:
        signals.log_signal.emit("✅ 诊断结果: 端口完全畅通！")
    else:
        signals.log_signal.emit("❌ 诊断结果: 端口不可达，请核实房主服务与防火墙设置。")
    signals.finished_signal.emit()