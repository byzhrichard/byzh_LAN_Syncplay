import sys
import os
import time
import threading

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QPushButton, QLabel, QLineEdit, 
                               QFileDialog, QTextEdit, QRadioButton, QMessageBox,
                               QTabWidget, QGroupBox, QListWidget, QListWidgetItem,
                               QComboBox)
from PySide6.QtCore import Signal, QObject, QTimer, QSettings
from PySide6.QtGui import QDragEnterEvent, QDropEvent

# 导入播放器模块
from player_mpv import MPVController, auto_detect_mpv
from player_vlc import VLCController, auto_detect_vlc

# 导入视频元数据解析模块
from media_utils import get_video_duration_fast, format_size, format_time

# 导入网络通信与诊断模块
from network import SyncNetwork, NetworkSignals, PingSignals, run_icmp_ping, run_tcp_ping

class LaunchSignals(QObject):
    launched_signal = Signal(bool, str)

class SyncplayMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Syncplay Lite (多放映厅增强版)")
        self.resize(700, 650)

        # 开启文件拖拽进窗口载入支持
        self.setAcceptDrops(True)

        self.player = None
        self.player_type = "mpv"

        self.video_path = ""
        self.video_size_str = "--"
        self.video_dur_str = "--"
        self.peer_name = ""

        self.host_video_data = {"name": "等待房主载入...", "size": "--", "duration": "--"}
        self.last_player_playing = False
        self.last_player_time = 0
        self.suppress_local_detect = False

        # 网络信号
        self.net_signals = NetworkSignals()
        self.net_signals.received.connect(self.on_net_received)
        self.net_signals.connected.connect(self.on_connected_ok)
        self.net_signals.disconnected.connect(self.on_disconnected_ok)
        self.network = SyncNetwork(self.net_signals)

        # 房主每 2 秒广播一次基准
        self.host_sync_timer = QTimer(self)
        self.host_sync_timer.setInterval(2000)
        self.host_sync_timer.timeout.connect(self.host_broadcast_tick)

        # 播放器存活与按键监听（300ms 一次）
        self.monitor_timer = QTimer(self)
        self.monitor_timer.setInterval(300)
        self.monitor_timer.timeout.connect(self.monitor_timer_tick)

        # Ping 信号
        self.ping_signals = PingSignals()
        self.ping_signals.log_signal.connect(self.append_ping_log)
        self.ping_signals.finished_signal.connect(self.on_ping_finished)

        self.launch_signals = LaunchSignals()
        self.launch_signals.launched_signal.connect(self.on_player_launched_result)

        self.settings = QSettings("SyncplayLite", "Config")

        self.init_ui()
        self.load_saved_settings()

    def init_ui(self):
        self.tabs = QTabWidget()

        self.tab_path = QWidget()
        self.tab_network = QWidget()
        self.tab_sync = QWidget()
        self.tab_ping = QWidget()

        self.init_path_tab()
        self.init_network_tab()
        self.init_sync_tab()
        self.init_ping_tab()

        self.tabs.addTab(self.tab_path, "1. 📁 路径设置")
        self.tabs.addTab(self.tab_network, "2. 🌐 房间设置")
        self.tabs.addTab(self.tab_sync, "3. 🔄 同步与控制")
        self.tabs.addTab(self.tab_ping, "4. 🛠️ 功能-Ping")

        self.setCentralWidget(self.tabs)
        self.update_control_permission()

    def init_path_tab(self):
        layout = QVBoxLayout(self.tab_path)

        grp_mpv = QGroupBox("mpv 播放器路径 (推荐 ⭐⭐⭐⭐⭐)")
        v_mpv = QVBoxLayout(grp_mpv)
        v_mpv.addWidget(QLabel("mpv 原生支持 JSON-IPC，精准对齐、零延迟、无任何状态误判问题。"))
        h_mpv = QHBoxLayout()
        self.txt_mpv_path = QLineEdit()
        self.txt_mpv_path.setPlaceholderText("自动检测或手动选择 mpv.exe")
        btn_find_mpv = QPushButton("自动查找")
        btn_find_mpv.clicked.connect(self.trigger_auto_detect_mpv)
        btn_browse_mpv = QPushButton("浏览...")
        btn_browse_mpv.clicked.connect(self.browse_mpv_path)
        h_mpv.addWidget(self.txt_mpv_path)
        h_mpv.addWidget(btn_find_mpv)
        h_mpv.addWidget(btn_browse_mpv)
        v_mpv.addLayout(h_mpv)
        layout.addWidget(grp_mpv)

        grp_vlc = QGroupBox("VLC 播放器路径 (备选)")
        v_vlc = QVBoxLayout(grp_vlc)
        v_vlc.addWidget(QLabel("传统 VLC 播放器。"))
        h_vlc = QHBoxLayout()
        self.txt_vlc_path = QLineEdit()
        self.txt_vlc_path.setPlaceholderText("自动检测或手动选择 vlc.exe")
        btn_find_vlc = QPushButton("自动查找")
        btn_find_vlc.clicked.connect(self.trigger_auto_detect_vlc)
        btn_browse_vlc = QPushButton("浏览...")
        btn_browse_vlc.clicked.connect(self.browse_vlc_path)
        h_vlc.addWidget(self.txt_vlc_path)
        h_vlc.addWidget(btn_find_vlc)
        h_vlc.addWidget(btn_browse_vlc)
        v_vlc.addLayout(h_vlc)
        layout.addWidget(grp_vlc)

        layout.addStretch(1)

    def init_network_tab(self):
        layout = QVBoxLayout(self.tab_network)

        h_name = QHBoxLayout()
        h_name.addWidget(QLabel("我的昵称:"))
        self.txt_my_name = QLineEdit()
        self.txt_my_name.setPlaceholderText("请输入您的昵称（必填）")
        h_name.addWidget(self.txt_my_name)
        layout.addLayout(h_name)

        grp_role = QGroupBox("身份设定")
        h_role = QHBoxLayout(grp_role)
        self.rb_server = QRadioButton("做房主 (掌控播放主权)")
        self.rb_client = QRadioButton("加入好友 (观众模式，跟随房主)")
        self.rb_server.setChecked(True)
        self.rb_server.toggled.connect(self.on_mode_change)
        h_role.addWidget(self.rb_server)
        h_role.addWidget(self.rb_client)
        layout.addWidget(grp_role)

        grp_net = QGroupBox("连接配置")
        v_net = QVBoxLayout(grp_net)
        h_ip = QHBoxLayout()
        self.lbl_ip_desc = QLabel("监听 IP:")
        self.txt_ip = QLineEdit("0.0.0.0")
        h_ip.addWidget(self.lbl_ip_desc)
        h_ip.addWidget(self.txt_ip)
        v_net.addLayout(h_ip)

        h_port = QHBoxLayout()
        h_port.addWidget(QLabel("端口:"))
        self.txt_port = QLineEdit("8899")
        h_port.addWidget(self.txt_port)
        v_net.addLayout(h_port)

        h_conn_btns = QHBoxLayout()
        self.btn_connect = QPushButton("开启房间服务")
        self.btn_connect.setFixedHeight(36)
        self.btn_connect.clicked.connect(self.connect_network)

        self.btn_disconnect = QPushButton("🚪 解散房间")
        self.btn_disconnect.setFixedHeight(36)
        self.btn_disconnect.setEnabled(False)
        self.btn_disconnect.clicked.connect(self.disconnect_network)

        h_conn_btns.addWidget(self.btn_connect, stretch=2)
        h_conn_btns.addWidget(self.btn_disconnect, stretch=1)
        v_net.addLayout(h_conn_btns)

        layout.addWidget(grp_net)

        grp_members = QGroupBox("房间成员列表")
        v_mem = QVBoxLayout(grp_members)
        self.list_members = QListWidget()
        v_mem.addWidget(self.list_members)
        layout.addWidget(grp_members)

    def init_sync_tab(self):
        layout = QVBoxLayout(self.tab_sync)

        # 1. 顶端看板
        grp_video_info = QGroupBox("视频载入与播放器启动 (可直接将视频文件拖入窗口)")
        v_video = QVBoxLayout(grp_video_info)

        self.lbl_host_video_meta = QLabel("👑 房主视频：等待房主载入...")
        self.lbl_host_video_meta.setStyleSheet(
            "background-color: #f1f8e9; border: 1px solid #c8e6c9; border-radius: 4px; padding: 6px; font-weight: bold; color: #2e7d32;"
        )
        v_video.addWidget(self.lbl_host_video_meta)

        h_local = QHBoxLayout()
        self.btn_select_file = QPushButton("选择本地视频")
        self.btn_select_file.clicked.connect(self.select_file)
        self.lbl_my_video_meta = QLabel("我的视频：未选择 (支持直接拖拽文件进窗口)")
        h_local.addWidget(self.btn_select_file)
        h_local.addWidget(self.lbl_my_video_meta, stretch=1)
        v_video.addLayout(h_local)

        h_launch = QHBoxLayout()
        h_launch.addWidget(QLabel("选择播放器:"))
        self.combo_player = QComboBox()
        self.combo_player.addItem("mpv (推荐 - 极度丝滑)", "mpv")
        self.combo_player.addItem("VLC (备选)", "vlc")
        h_launch.addWidget(self.combo_player)

        self.btn_launch_player = QPushButton("🚀 启动播放器 (就绪暂停)")
        self.btn_launch_player.setFixedHeight(38)
        self.btn_launch_player.setEnabled(False)
        self.btn_launch_player.clicked.connect(self.launch_player)
        h_launch.addWidget(self.btn_launch_player, stretch=1)
        v_video.addLayout(h_launch)

        layout.addWidget(grp_video_info)

        # 2. 控制台
        self.grp_ctrl = QGroupBox("控制台")
        v_ctrl = QVBoxLayout(self.grp_ctrl)

        self.lbl_role_hint = QLabel()
        v_ctrl.addWidget(self.lbl_role_hint)

        h_ctrl_row1 = QHBoxLayout()
        self.btn_toggle_play = QPushButton("⏯ 同步 播放 / 暂停")
        self.btn_toggle_play.setFixedHeight(38)
        self.btn_toggle_play.clicked.connect(self.host_action_toggle_play)

        self.btn_sync_seek = QPushButton("🔄 强制所有人对齐到我")
        self.btn_sync_seek.setFixedHeight(38)
        self.btn_sync_seek.clicked.connect(self.host_action_force_sync)

        h_ctrl_row1.addWidget(self.btn_toggle_play, stretch=2)
        h_ctrl_row1.addWidget(self.btn_sync_seek, stretch=1)
        v_ctrl.addLayout(h_ctrl_row1)

        h_ctrl_row2 = QHBoxLayout()
        self.btn_back_10 = QPushButton("<-10s")
        self.btn_back_5 = QPushButton("<-5s")
        self.btn_fwd_5 = QPushButton("5s->")
        self.btn_fwd_10 = QPushButton("10s->")

        self.btn_back_10.clicked.connect(lambda: self.host_action_relative_seek(-10))
        self.btn_back_5.clicked.connect(lambda: self.host_action_relative_seek(-5))
        self.btn_fwd_5.clicked.connect(lambda: self.host_action_relative_seek(5))
        self.btn_fwd_10.clicked.connect(lambda: self.host_action_relative_seek(10))

        h_ctrl_row2.addWidget(self.btn_back_10)
        h_ctrl_row2.addWidget(self.btn_back_5)
        h_ctrl_row2.addWidget(self.btn_fwd_5)
        h_ctrl_row2.addWidget(self.btn_fwd_10)
        v_ctrl.addLayout(h_ctrl_row2)

        layout.addWidget(self.grp_ctrl)

        # 3. 日志框
        layout.addWidget(QLabel("实时同步与聊天日志 (全屏观影时，聊天将直接飘在视频画面上方):"))
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        layout.addWidget(self.txt_log)

        # 4. 聊天输入框
        h_chat = QHBoxLayout()
        self.txt_chat_input = QLineEdit()
        self.txt_chat_input.setPlaceholderText("在此输入聊天内容，回车发送（文字将直接飘在双方视频屏幕上）...")
        self.txt_chat_input.returnPressed.connect(self.send_chat)
        self.btn_send_chat = QPushButton("发送")
        self.btn_send_chat.clicked.connect(self.send_chat)

        h_chat.addWidget(self.txt_chat_input, stretch=1)
        h_chat.addWidget(self.btn_send_chat)
        layout.addLayout(h_chat)

    def init_ping_tab(self):
        layout = QVBoxLayout(self.tab_ping)
        grp_ping = QGroupBox("虚拟局域网连通性检测 (局域网 / VLAN)")
        v_ping = QVBoxLayout(grp_ping)

        h_target = QHBoxLayout()
        h_target.addWidget(QLabel("目标 IP:"))
        self.txt_ping_ip = QLineEdit()
        self.txt_ping_ip.setPlaceholderText("输入对方虚拟局域网 IP (如 192.168.x.x / 10.x.x.x / 172.x.x.x)")
        h_target.addWidget(self.txt_ping_ip)

        h_target.addWidget(QLabel("目标端口:"))
        self.txt_ping_port = QLineEdit("8899")
        self.txt_ping_port.setFixedWidth(60)
        h_target.addWidget(self.txt_ping_port)
        v_ping.addLayout(h_target)

        h_btns = QHBoxLayout()
        self.btn_ping_icmp = QPushButton("📡 系统 ICMP Ping (测试网络通不通)")
        self.btn_ping_tcp = QPushButton("🔌 TCP 端口直连探测 (测试 8899 能否连上)")
        self.btn_ping_icmp.clicked.connect(self.start_icmp_ping)
        self.btn_ping_tcp.clicked.connect(self.start_tcp_ping)
        h_btns.addWidget(self.btn_ping_icmp)
        h_btns.addWidget(self.btn_ping_tcp)
        v_ping.addLayout(h_btns)

        layout.addWidget(grp_ping)

        layout.addWidget(QLabel("Ping 诊断输出:"))
        self.txt_ping_log = QTextEdit()
        self.txt_ping_log.setReadOnly(True)
        layout.addWidget(self.txt_ping_log)

    # --- 拖拽载入文件 ---
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            f = urls[0].toLocalFile()
            ext = os.path.splitext(f)[1].lower()
            if ext in ['.mp4', '.mkv', '.avi', '.flv', '.ts', '.mov', '.m4v', '.webm']:
                self.load_video_file(f)

    def select_file(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "选择视频文件", "", "视频 (*.mp4 *.mkv *.avi *.flv *.ts *.mov *.m4v *.webm)"
        )
        if f: self.load_video_file(f)

    def load_video_file(self, f):
        self.video_path = f
        file_name = os.path.basename(f)
        file_size = os.path.getsize(f)
        self.video_size_str = format_size(file_size)

        fast_dur = get_video_duration_fast(f)
        self.video_dur_str = format_time(fast_dur) if fast_dur > 0 else "待启动后确认"

        self.lbl_my_video_meta.setText(
            f"我的视频：{file_name} | 大小: {self.video_size_str} | 时长: {self.video_dur_str}"
        )
        self.btn_launch_player.setEnabled(True)

        if self.rb_server.isChecked():
            self.host_video_data["name"] = file_name
            self.host_video_data["size"] = self.video_size_str
            self.host_video_data["duration"] = self.video_dur_str
            self.update_host_video_banner()
            self.broadcast_host_video_meta()

    def update_host_video_banner(self):
        self.lbl_host_video_meta.setText(
            f"👑 房主视频：《{self.host_video_data['name']}》 | 大小: {self.host_video_data['size']} | 时长: {self.host_video_data['duration']}"
        )

    def broadcast_host_video_meta(self):
        if self.rb_server.isChecked() and self.network.is_connected():
            my_name = self.txt_my_name.text().strip() or "房主"
            self.network.send_cmd("video_meta_sync", sender=my_name, extra=self.host_video_data)

    def update_control_permission(self):
        is_host = self.rb_server.isChecked()
        for btn in [self.btn_toggle_play, self.btn_sync_seek, self.btn_back_10, 
                    self.btn_back_5, self.btn_fwd_5, self.btn_fwd_10]:
            btn.setEnabled(is_host)

        if is_host:
            self.lbl_role_hint.setText("👑 当前为【房主模式】：您的播放、暂停、快进快退将直接主导全员进度。")
            self.lbl_role_hint.setStyleSheet("color: #2e7d32; font-weight: bold;")
        else:
            self.lbl_role_hint.setText("🔒 当前为【观众模式】：进度完全跟随房主。")
            self.lbl_role_hint.setStyleSheet("color: #d32f2f; font-weight: bold;")

    def update_member_ui(self):
        my_name = self.txt_my_name.text().strip() or "未命名"
        self.list_members.clear()

        if self.rb_server.isChecked():
            self.list_members.addItem(QListWidgetItem(f"👑 {my_name} (房主/我)"))
            if self.peer_name:
                self.list_members.addItem(QListWidgetItem(f"👤 {self.peer_name} (观众)"))
        else:
            if self.peer_name:
                self.list_members.addItem(QListWidgetItem(f"👑 {self.peer_name} (房主)"))
            self.list_members.addItem(QListWidgetItem(f"👤 {my_name} (我/观众)"))

    def log(self, text):
        self.txt_log.append(f"[{time.strftime('%H:%M:%S')}] {text}")

    # --- 启动播放器 ---
    def launch_player(self):
        if self.player:
            try: self.player.close()
            except: pass
            self.player = None

        self.player_type = self.combo_player.currentData()
        if self.player_type == "mpv":
            exe_path = self.txt_mpv_path.text().strip()
            if not os.path.isfile(exe_path):
                QMessageBox.critical(self, "错误", "未找到 mpv.exe，请在【1. 路径设置】中指定正确的 mpv 路径！")
                return
            self.player = MPVController()
        else:
            exe_path = self.txt_vlc_path.text().strip()
            if not os.path.isfile(exe_path):
                QMessageBox.critical(self, "错误", "未找到 vlc.exe，请在【1. 路径设置】中指定正确的 VLC 路径！")
                return
            self.player = VLCController()

        self.btn_launch_player.setEnabled(False)
        self.btn_launch_player.setText("⏳ 正在拉起播放器...")
        self.log(f"正在拉起本地 {self.player_type.upper()} 播放器...")

        def run_thread():
            ok, msg = self.player.launch_and_connect(exe_path, self.video_path)
            self.launch_signals.launched_signal.emit(ok, msg)

        threading.Thread(target=run_thread, daemon=True).start()

    def on_player_launched_result(self, ok, msg):
        if ok:
            p_name = self.player_type.upper()
            self.log(f"【成功】{p_name} 挂载就绪！画面处于暂停状态。")
            self.btn_launch_player.setText(f"🔄 重启 {p_name}")
            self.btn_launch_player.setEnabled(True)
            self.monitor_timer.start()

            time.sleep(0.3)
            if self.last_player_time > 0:
                self.player.seek(self.last_player_time)
            self.player.ensure_pause()

            dur = self.player.get_length()
            if dur > 0:
                self.video_dur_str = format_time(dur)
                file_name = os.path.basename(self.video_path)
                self.lbl_my_video_meta.setText(
                    f"我的视频：{file_name} | 大小: {self.video_size_str} | 时长: {self.video_dur_str}"
                )
                if self.rb_server.isChecked():
                    self.host_video_data["duration"] = self.video_dur_str
                    self.update_host_video_banner()
                    self.broadcast_host_video_meta()
        else:
            self.log(f"【失败】{msg}")
            self.btn_launch_player.setEnabled(True)
            self.btn_launch_player.setText("🚀 重新启动播放器")

    def monitor_timer_tick(self):
        if self.player and not self.player.is_alive():
            self.player.close()
            self.player = None
            self.btn_launch_player.setEnabled(True)
            self.btn_launch_player.setText("🚀 重新启动播放器")
            self.log("⚠️ 检测到播放器已被关闭，点击启动按钮可立刻拉起！")
            return

        if not self.rb_server.isChecked() or not self.network.is_connected() or not self.player or self.suppress_local_detect:
            return

        curr_playing = self.player.is_playing()
        curr_time = self.player.get_time()
        my_name = self.txt_my_name.text().strip() or "房主"

        if curr_playing != self.last_player_playing:
            self.last_player_playing = curr_playing
            target_state = "playing" if curr_playing else "paused"
            state_str = "播放" if curr_playing else "按空格暂停"
            self.network.send_cmd("host_sync", curr_time, sender=my_name, extra={"state": target_state})
            self.log(f"[{my_name}] 在播放器中触发 {state_str} (进度: {curr_time}秒)")

        elif abs(curr_time - self.last_player_time) > 3 and curr_time > 0:
            target_state = "playing" if self.last_player_playing else "paused"
            self.network.send_cmd("host_sync", curr_time, sender=my_name, extra={"state": target_state})
            self.log(f"[{my_name}] 拖动进度至 {curr_time}秒 (保持{target_state})")
            self.last_player_time = curr_time

    # --- 房主操作逻辑 ---
    def host_action_toggle_play(self):
        if not self.rb_server.isChecked() or not self.player: return
        self.suppress_local_detect = True
        
        was_playing = self.player.is_playing()
        target_state = "paused" if was_playing else "playing"
        state_str = "暂停" if was_playing else "播放"

        if target_state == "paused":
            self.player.ensure_pause()
        else:
            self.player.ensure_play()

        self.last_player_playing = (target_state == "playing")
        t = self.player.get_time()

        my_name = self.txt_my_name.text().strip() or "房主"
        self.network.send_cmd("host_sync", t, sender=my_name, extra={"state": target_state})
        self.log(f"[{my_name}] 触发 {state_str} (进度: {t}秒)")
        QTimer.singleShot(500, lambda: setattr(self, 'suppress_local_detect', False))

    def host_action_relative_seek(self, delta):
        if not self.rb_server.isChecked() or not self.player: return
        self.suppress_local_detect = True
        
        was_playing = self.player.is_playing()
        target_state = "playing" if was_playing else "paused"

        self.player.relative_seek(delta)
        time.sleep(0.05)
        target_t = self.player.get_time()

        if not was_playing:
            self.player.ensure_pause()

        my_name = self.txt_my_name.text().strip() or "房主"
        self.network.send_cmd("host_sync", target_t, sender=my_name, extra={"state": target_state})
        action_name = f"快进 {delta}s" if delta > 0 else f"快退 {abs(delta)}s"
        self.log(f"[{my_name}] {action_name} -> 目标: {target_t}秒 (保持{target_state})")
        QTimer.singleShot(500, lambda: setattr(self, 'suppress_local_detect', False))

    def host_action_force_sync(self):
        if not self.rb_server.isChecked() or not self.player: return
        t = self.player.get_time()
        is_playing = self.player.is_playing()
        target_state = "playing" if is_playing else "paused"

        my_name = self.txt_my_name.text().strip() or "房主"
        self.network.send_cmd("host_sync", t, sender=my_name, extra={"state": target_state})
        self.log(f"[{my_name}] 强制对齐所有人 -> {t}秒 ({'播放中' if is_playing else '暂停中'})")

    def host_broadcast_tick(self):
        if not self.rb_server.isChecked() or not self.network.is_connected() or not self.player:
            return
        t = self.player.get_time()
        is_playing = self.player.is_playing()
        state_str = "playing" if is_playing else "paused"
        my_name = self.txt_my_name.text().strip() or "房主"
        self.network.send_cmd("host_sync", t, sender=my_name, extra={"state": state_str})

    # --- 观众端响应核心 ---
    def on_net_received(self, msg):
        act = msg.get("action")
        t = msg.get("time", 0)
        sender = msg.get("sender", "房主")

        if act == "handshake":
            self.peer_name = sender
            self.update_member_ui()
            self.log(f"🎉 [{sender}] 加入房间！")
            if self.rb_server.isChecked():
                my_name = self.txt_my_name.text().strip() or "房主"
                self.network.send_cmd("handshake_reply", sender=my_name, extra=self.host_video_data)

        elif act == "handshake_reply":
            self.peer_name = sender
            self.update_member_ui()
            self.log(f"🎉 连入房主 [{sender}]！")
            self.host_video_data["name"] = msg.get("name", "未获取")
            self.host_video_data["size"] = msg.get("size", "--")
            self.host_video_data["duration"] = msg.get("duration", "--")
            self.update_host_video_banner()

        elif act == "video_meta_sync":
            self.host_video_data["name"] = msg.get("name", "未获取")
            self.host_video_data["size"] = msg.get("size", "--")
            self.host_video_data["duration"] = msg.get("duration", "--")
            self.update_host_video_banner()
            self.log(f"📢 房主更换了视频: 《{self.host_video_data['name']}》")

        elif act == "chat":
            chat_text = msg.get('msg', '')
            self.log(f"💬 [{sender}]: {chat_text}")
            if self.player:
                self.player.show_osd(f"💬 {sender}: {chat_text}")

        elif act == "room_disbanded":
            self.log("🚪 房主已解散房间。")
            QMessageBox.information(self, "提示", "房主已解散房间！")
            self.on_disconnected_ok()

        elif act == "member_left":
            self.log(f"👤 [{sender}] 已离开房间。")
            self.peer_name = ""
            self.update_member_ui()

        elif act == "host_sync":
            if self.rb_server.isChecked() or not self.player: return
            
            target_state = msg.get("state", "paused")
            curr_t = self.player.get_time()

            if abs(curr_t - t) > 2:
                self.player.seek(t)
                self.last_player_time = t

            if target_state == "paused":
                self.player.ensure_pause()
            elif target_state == "playing":
                self.player.ensure_play()

    # --- 路径与探测 ---
    def trigger_auto_detect_mpv(self):
        p = auto_detect_mpv()
        if p:
            self.txt_mpv_path.setText(p)
            self.log(f"已找到 mpv 路径: {p}")

    def trigger_auto_detect_vlc(self):
        p = auto_detect_vlc()
        if p:
            self.txt_vlc_path.setText(p)
            self.log(f"已找到 VLC 路径: {p}")

    def browse_mpv_path(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择 mpv 程序", "", "mpv (mpv.exe mpv);;所有文件 (*.*)")
        if f: self.txt_mpv_path.setText(f)

    def browse_vlc_path(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择 VLC 程序", "", "VLC (vlc.exe vlc);;所有文件 (*.*)")
        if f: self.txt_vlc_path.setText(f)

    def on_mode_change(self):
        if self.rb_server.isChecked():
            self.lbl_ip_desc.setText("监听 IP:")
            self.txt_ip.setText("0.0.0.0")
            self.btn_connect.setText("开启房间服务")
            self.btn_disconnect.setText("🚪 解散房间")
            if self.video_path:
                self.host_video_data["name"] = os.path.basename(self.video_path)
                self.host_video_data["size"] = self.video_size_str
                self.host_video_data["duration"] = self.video_dur_str
                self.update_host_video_banner()
        else:
            self.lbl_ip_desc.setText("房主 IP:")
            self.txt_ip.clear()
            self.txt_ip.setPlaceholderText("房主 IP 地址 (如 192.168.x.x / 10.x.x.x / 172.x.x.x)")
            self.btn_connect.setText("加入好友房间")
            self.btn_disconnect.setText("🚪 退出房间")
            self.lbl_host_video_meta.setText("👑 房主视频：(等待连入房间后获取...)")

        self.update_control_permission()
        self.update_member_ui()

    def connect_network(self):
        my_name = self.txt_my_name.text().strip()
        if not my_name:
            QMessageBox.warning(self, "提示", "请先在上方输入【我的昵称】再进行连接！")
            self.txt_my_name.setFocus()
            return

        port = int(self.txt_port.text().strip())
        ip = self.txt_ip.text().strip()
        self.txt_my_name.setEnabled(False)

        if self.rb_server.isChecked():
            bind_ip = ip if ip else "0.0.0.0"
            self.network.start_server(bind_ip, port)
            self.log(f"服务已启动 (监听 {bind_ip}:{port})，等待好友加入...")
        else:
            if not ip:
                QMessageBox.warning(self, "警告", "请先输入房主 IP 地址！")
                self.txt_my_name.setEnabled(True)
                return
            self.network.start_client(ip, port)
            self.txt_ping_ip.setText(ip)

        self.btn_connect.setEnabled(False)
        self.btn_disconnect.setEnabled(True)
        self.rb_server.setEnabled(False)
        self.rb_client.setEnabled(False)
        self.update_member_ui()

    def disconnect_network(self):
        my_name = self.txt_my_name.text().strip() or "我"
        if self.rb_server.isChecked():
            self.network.send_cmd("room_disbanded", sender=my_name)
            self.log("[网络] 房间已解散，服务已停止。")
        else:
            self.network.send_cmd("member_left", sender=my_name)
            self.log("[网络] 已主动退出房间。")

        self.network.close()
        self.on_disconnected_ok()

    def on_connected_ok(self, addr):
        my_name = self.txt_my_name.text().strip()
        self.network.send_cmd("handshake", sender=my_name)

        if self.rb_server.isChecked():
            self.host_sync_timer.start()
            self.broadcast_host_video_meta()

    def on_disconnected_ok(self):
        self.log("[网络] 连接断开")
        self.host_sync_timer.stop()
        self.peer_name = ""
        self.update_member_ui()

        self.btn_connect.setEnabled(True)
        self.btn_disconnect.setEnabled(False)
        self.txt_my_name.setEnabled(True)
        self.rb_server.setEnabled(True)
        self.rb_client.setEnabled(True)

    def send_chat(self):
        text = self.txt_chat_input.text().strip()
        if not text: return
        my_name = self.txt_my_name.text().strip() or "我"
        if not self.network.is_connected():
            self.log("⚠️ 尚未连入房间，无法发送聊天。")
            return

        self.network.send_cmd("chat", sender=my_name, extra={"msg": text})
        self.log(f"💬 [{my_name}]: {text}")
        
        if self.player:
            self.player.show_osd(f"💬 {my_name}: {text}")

        self.txt_chat_input.clear()

    # --- QSettings 配置记忆 ---
    def load_saved_settings(self):
        saved_name = self.settings.value("my_name", "")
        if saved_name: self.txt_my_name.setText(saved_name)

        saved_ip = self.settings.value("last_ip", "")
        if saved_ip:
            self.txt_ip.setText(saved_ip)
            self.txt_ping_ip.setText(saved_ip)

        is_client = self.settings.value("is_client", "false") == "true"
        if is_client:
            self.rb_client.setChecked(True)
            self.on_mode_change()

        player_idx = int(self.settings.value("player_idx", 0))
        self.combo_player.setCurrentIndex(player_idx)

        saved_mpv = self.settings.value("mpv_path", "")
        if saved_mpv and os.path.isfile(saved_mpv):
            self.txt_mpv_path.setText(saved_mpv)
        else:
            self.trigger_auto_detect_mpv()

        saved_vlc = self.settings.value("vlc_path", "")
        if saved_vlc and os.path.isfile(saved_vlc):
            self.txt_vlc_path.setText(saved_vlc)
        else:
            self.trigger_auto_detect_vlc()

    def save_current_settings(self):
        self.settings.setValue("my_name", self.txt_my_name.text().strip())
        if self.rb_client.isChecked():
            self.settings.setValue("last_ip", self.txt_ip.text().strip())
        self.settings.setValue("is_client", "true" if self.rb_client.isChecked() else "false")
        self.settings.setValue("player_idx", self.combo_player.currentIndex())
        self.settings.setValue("mpv_path", self.txt_mpv_path.text().strip())
        self.settings.setValue("vlc_path", self.txt_vlc_path.text().strip())

    # --- Ping 诊断调用 ---
    def append_ping_log(self, text):
        self.txt_ping_log.append(f"[{time.strftime('%H:%M:%S')}] {text}")

    def on_ping_finished(self):
        self.btn_ping_icmp.setEnabled(True)
        self.btn_ping_tcp.setEnabled(True)

    def start_icmp_ping(self):
        ip = self.txt_ping_ip.text().strip()
        if not ip:
            QMessageBox.warning(self, "警告", "请先输入要 Ping 的目标 IP！")
            return
        self.btn_ping_icmp.setEnabled(False)
        self.btn_ping_tcp.setEnabled(False)
        self.append_ping_log(f"开始对 {ip} 发起系统 Ping 测试...")
        threading.Thread(target=run_icmp_ping, args=(ip, self.ping_signals), daemon=True).start()

    def start_tcp_ping(self):
        ip = self.txt_ping_ip.text().strip()
        try:
            port = int(self.txt_ping_port.text().strip())
        except ValueError:
            QMessageBox.warning(self, "警告", "端口号必须为整数！")
            return

        if not ip:
            QMessageBox.warning(self, "警告", "请先输入目标 IP！")
            return

        self.btn_ping_icmp.setEnabled(False)
        self.btn_ping_tcp.setEnabled(False)
        self.append_ping_log(f"正在对 {ip}:{port} 进行 TCP 握手测速...")
        threading.Thread(target=run_tcp_ping, args=(ip, port, self.ping_signals), daemon=True).start()

    def closeEvent(self, event):
        self.save_current_settings()
        self.host_sync_timer.stop()
        self.monitor_timer.stop()
        self.network.close()
        if self.player: self.player.close()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = SyncplayMainWindow()
    win.show()
    sys.exit(app.exec())