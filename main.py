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
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon, QAction, QActionGroup

# 导入播放器模块
from player_mpv import MPVController, auto_detect_mpv
from player_vlc import VLCController, auto_detect_vlc

# 导入视频元数据解析模块
from media_utils import get_video_duration_fast, format_size, format_time

# 导入网络通信与诊断模块
from network import SyncNetwork, NetworkSignals, PingSignals, run_icmp_ping, run_tcp_ping

# 导入多语言国际化模块
from i18n import tr

def resource_path(relative_path):
    """获取资源的绝对路径，完美兼容源码运行与 PyInstaller 单文件打包模式"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

class LaunchSignals(QObject):
    launched_signal = Signal(bool, str)

class SyncplayMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(700, 670)

        # 当前语言 (默认中文)
        self.current_lang = "zh"

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

        self.init_menu_bar()
        self.init_ui()
        self.load_saved_settings()

    def t(self, key):
        """便捷获取当前语言翻译"""
        return tr(key, self.current_lang)

    # ---------------- 顶部菜单栏 (语言切换) ----------------
    def init_menu_bar(self):
        menu_bar = self.menuBar()
        self.menu_lang = menu_bar.addMenu("语言 (Language)")

        action_group = QActionGroup(self)
        action_group.setExclusive(True)

        self.action_zh = QAction("简体中文", self, checkable=True)
        self.action_zh.triggered.connect(lambda: self.switch_language("zh"))
        action_group.addAction(self.action_zh)
        self.menu_lang.addAction(self.action_zh)

        self.action_en = QAction("English", self, checkable=True)
        self.action_en.triggered.connect(lambda: self.switch_language("en"))
        action_group.addAction(self.action_en)
        self.menu_lang.addAction(self.action_en)

    def switch_language(self, lang):
        if self.current_lang == lang:
            return
        self.current_lang = lang
        self.retranslate_ui()

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

        self.tabs.addTab(self.tab_path, "")
        self.tabs.addTab(self.tab_network, "")
        self.tabs.addTab(self.tab_sync, "")
        self.tabs.addTab(self.tab_ping, "")

        self.setCentralWidget(self.tabs)
        self.retranslate_ui()

    def init_path_tab(self):
        layout = QVBoxLayout(self.tab_path)

        self.grp_mpv = QGroupBox()
        v_mpv = QVBoxLayout(self.grp_mpv)
        self.lbl_mpv_desc = QLabel()
        v_mpv.addWidget(self.lbl_mpv_desc)
        h_mpv = QHBoxLayout()
        self.txt_mpv_path = QLineEdit()
        self.btn_find_mpv = QPushButton()
        self.btn_find_mpv.clicked.connect(self.trigger_auto_detect_mpv)
        self.btn_browse_mpv = QPushButton()
        self.btn_browse_mpv.clicked.connect(self.browse_mpv_path)
        h_mpv.addWidget(self.txt_mpv_path)
        h_mpv.addWidget(self.btn_find_mpv)
        h_mpv.addWidget(self.btn_browse_mpv)
        v_mpv.addLayout(h_mpv)
        layout.addWidget(self.grp_mpv)

        self.grp_vlc = QGroupBox()
        v_vlc = QVBoxLayout(self.grp_vlc)
        self.lbl_vlc_desc = QLabel()
        v_vlc.addWidget(self.lbl_vlc_desc)
        h_vlc = QHBoxLayout()
        self.txt_vlc_path = QLineEdit()
        self.btn_find_vlc = QPushButton()
        self.btn_find_vlc.clicked.connect(self.trigger_auto_detect_vlc)
        self.btn_browse_vlc = QPushButton()
        self.btn_browse_vlc.clicked.connect(self.browse_vlc_path)
        h_vlc.addWidget(self.txt_vlc_path)
        h_vlc.addWidget(self.btn_find_vlc)
        h_vlc.addWidget(self.btn_browse_vlc)
        v_vlc.addLayout(h_vlc)
        layout.addWidget(self.grp_vlc)

        layout.addStretch(1)

    def init_network_tab(self):
        layout = QVBoxLayout(self.tab_network)

        h_name = QHBoxLayout()
        self.lbl_my_name_title = QLabel()
        h_name.addWidget(self.lbl_my_name_title)
        self.txt_my_name = QLineEdit()
        h_name.addWidget(self.txt_my_name)
        layout.addLayout(h_name)

        self.grp_role = QGroupBox()
        h_role = QHBoxLayout(self.grp_role)
        self.rb_server = QRadioButton()
        self.rb_client = QRadioButton()
        self.rb_server.setChecked(True)
        self.rb_server.toggled.connect(self.on_mode_change)
        h_role.addWidget(self.rb_server)
        h_role.addWidget(self.rb_client)
        layout.addWidget(self.grp_role)

        self.grp_net = QGroupBox()
        v_net = QVBoxLayout(self.grp_net)
        h_ip = QHBoxLayout()
        self.lbl_ip_desc = QLabel()
        self.txt_ip = QLineEdit("0.0.0.0")
        h_ip.addWidget(self.lbl_ip_desc)
        h_ip.addWidget(self.txt_ip)
        v_net.addLayout(h_ip)

        h_port = QHBoxLayout()
        self.lbl_port_desc = QLabel()
        h_port.addWidget(self.lbl_port_desc)
        self.txt_port = QLineEdit("8899")
        h_port.addWidget(self.txt_port)
        v_net.addLayout(h_port)

        h_conn_btns = QHBoxLayout()
        self.btn_connect = QPushButton()
        self.btn_connect.setFixedHeight(36)
        self.btn_connect.clicked.connect(self.connect_network)

        self.btn_disconnect = QPushButton()
        self.btn_disconnect.setFixedHeight(36)
        self.btn_disconnect.setEnabled(False)
        self.btn_disconnect.clicked.connect(self.disconnect_network)

        h_conn_btns.addWidget(self.btn_connect, stretch=2)
        h_conn_btns.addWidget(self.btn_disconnect, stretch=1)
        v_net.addLayout(h_conn_btns)

        layout.addWidget(self.grp_net)

        self.grp_members = QGroupBox()
        v_mem = QVBoxLayout(self.grp_members)
        self.list_members = QListWidget()
        v_mem.addWidget(self.list_members)
        layout.addWidget(self.grp_members)

    def init_sync_tab(self):
        layout = QVBoxLayout(self.tab_sync)

        # 1. 顶端看板
        self.grp_video_info = QGroupBox()
        v_video = QVBoxLayout(self.grp_video_info)

        self.lbl_host_video_meta = QLabel()
        self.lbl_host_video_meta.setStyleSheet(
            "background-color: #f1f8e9; border: 1px solid #c8e6c9; border-radius: 4px; padding: 6px; font-weight: bold; color: #2e7d32;"
        )
        v_video.addWidget(self.lbl_host_video_meta)

        h_local = QHBoxLayout()
        self.btn_select_file = QPushButton()
        self.btn_select_file.clicked.connect(self.select_file)
        self.lbl_my_video_meta = QLabel()
        h_local.addWidget(self.btn_select_file)
        h_local.addWidget(self.lbl_my_video_meta, stretch=1)
        v_video.addLayout(h_local)

        h_launch = QHBoxLayout()
        self.lbl_select_player_desc = QLabel()
        h_launch.addWidget(self.lbl_select_player_desc)
        self.combo_player = QComboBox()
        self.combo_player.addItem("mpv (Recommended)", "mpv")
        self.combo_player.addItem("VLC", "vlc")
        h_launch.addWidget(self.combo_player)

        self.btn_launch_player = QPushButton()
        self.btn_launch_player.setFixedHeight(38)
        self.btn_launch_player.setEnabled(False)
        self.btn_launch_player.clicked.connect(self.launch_player)
        h_launch.addWidget(self.btn_launch_player, stretch=1)
        v_video.addLayout(h_launch)

        layout.addWidget(self.grp_video_info)

        # 2. 控制台
        self.grp_ctrl = QGroupBox()
        v_ctrl = QVBoxLayout(self.grp_ctrl)

        self.lbl_role_hint = QLabel()
        v_ctrl.addWidget(self.lbl_role_hint)

        h_ctrl_row1 = QHBoxLayout()
        self.btn_toggle_play = QPushButton()
        self.btn_toggle_play.setFixedHeight(38)
        self.btn_toggle_play.clicked.connect(self.host_action_toggle_play)

        self.btn_sync_seek = QPushButton()
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
        self.lbl_log_title_desc = QLabel()
        layout.addWidget(self.lbl_log_title_desc)
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        layout.addWidget(self.txt_log)

        # 4. 聊天输入框
        h_chat = QHBoxLayout()
        self.txt_chat_input = QLineEdit()
        self.txt_chat_input.returnPressed.connect(self.send_chat)
        self.btn_send_chat = QPushButton()
        self.btn_send_chat.clicked.connect(self.send_chat)

        h_chat.addWidget(self.txt_chat_input, stretch=1)
        h_chat.addWidget(self.btn_send_chat)
        layout.addLayout(h_chat)

    def init_ping_tab(self):
        layout = QVBoxLayout(self.tab_ping)
        self.grp_ping = QGroupBox()
        v_ping = QVBoxLayout(self.grp_ping)

        h_target = QHBoxLayout()
        self.lbl_target_ip_desc = QLabel()
        h_target.addWidget(self.lbl_target_ip_desc)
        self.txt_ping_ip = QLineEdit()
        h_target.addWidget(self.txt_ping_ip)

        self.lbl_target_port_desc = QLabel()
        h_target.addWidget(self.lbl_target_port_desc)
        self.txt_ping_port = QLineEdit("8899")
        self.txt_ping_port.setFixedWidth(60)
        h_target.addWidget(self.txt_ping_port)
        v_ping.addLayout(h_target)

        h_btns = QHBoxLayout()
        self.btn_ping_icmp = QPushButton()
        self.btn_ping_tcp = QPushButton()
        self.btn_ping_icmp.clicked.connect(self.start_icmp_ping)
        self.btn_ping_tcp.clicked.connect(self.start_tcp_ping)
        h_btns.addWidget(self.btn_ping_icmp)
        h_btns.addWidget(self.btn_ping_tcp)
        v_ping.addLayout(h_btns)

        layout.addWidget(self.grp_ping)

        self.lbl_ping_log_desc = QLabel()
        layout.addWidget(self.lbl_ping_log_desc)
        self.txt_ping_log = QTextEdit()
        self.txt_ping_log.setReadOnly(True)
        layout.addWidget(self.txt_ping_log)

    # ---------------- 多语言动态刷新机制 (热切换) ----------------
    def retranslate_ui(self):
        # 1. 窗口标题与图标
        self.setWindowTitle(self.t("window_title"))
        self.setWindowIcon(QIcon(resource_path("assets/byzh16x16-256x256.ico")))

        # 2. 菜单栏勾选同步
        self.menu_lang.setTitle(self.t("menu_language"))
        self.action_zh.setChecked(self.current_lang == "zh")
        self.action_en.setChecked(self.current_lang == "en")

        # 3. 选项卡标题
        self.tabs.setTabText(0, self.t("tab_path"))
        self.tabs.setTabText(1, self.t("tab_room"))
        self.tabs.setTabText(2, self.t("tab_sync"))
        self.tabs.setTabText(3, self.t("tab_ping"))

        # 4. 栏目 1 (路径)
        self.grp_mpv.setTitle(self.t("grp_mpv"))
        self.lbl_mpv_desc.setText(self.t("mpv_desc"))
        self.txt_mpv_path.setPlaceholderText(self.t("mpv_placeholder"))
        self.btn_find_mpv.setText(self.t("btn_auto_find"))
        self.btn_browse_mpv.setText(self.t("btn_browse"))

        self.grp_vlc.setTitle(self.t("grp_vlc"))
        self.lbl_vlc_desc.setText(self.t("vlc_desc"))
        self.txt_vlc_path.setPlaceholderText(self.t("vlc_placeholder"))
        self.btn_find_vlc.setText(self.t("btn_auto_find"))
        self.btn_browse_vlc.setText(self.t("btn_browse"))

        # 5. 栏目 2 (房间)
        self.lbl_my_name_title.setText(self.t("lbl_nickname"))
        self.txt_my_name.setPlaceholderText(self.t("nickname_placeholder"))
        self.grp_role.setTitle(self.t("grp_role"))
        self.rb_server.setText(self.t("rb_host"))
        self.rb_client.setText(self.t("rb_client"))
        self.grp_net.setTitle(self.t("grp_net"))
        self.lbl_port_desc.setText(self.t("lbl_port"))
        self.grp_members.setTitle(self.t("grp_members"))

        # 6. 栏目 3 (同步)
        self.grp_video_info.setTitle(self.t("grp_video"))
        self.btn_select_file.setText(self.t("btn_select_video"))
        self.lbl_select_player_desc.setText(self.t("lbl_select_player"))
        self.grp_ctrl.setTitle(self.t("grp_console"))
        self.btn_toggle_play.setText(self.t("btn_play_pause"))
        self.btn_sync_seek.setText(self.t("btn_force_sync"))
        self.lbl_log_title_desc.setText(self.t("lbl_log_title"))
        self.txt_chat_input.setPlaceholderText(self.t("chat_placeholder"))
        self.btn_send_chat.setText(self.t("btn_send"))

        # 7. 栏目 4 (Ping)
        self.grp_ping.setTitle(self.t("grp_ping"))
        self.lbl_target_ip_desc.setText(self.t("lbl_target_ip"))
        self.txt_ping_ip.setPlaceholderText(self.t("target_ip_placeholder"))
        self.lbl_target_port_desc.setText(self.t("lbl_target_port"))
        self.btn_ping_icmp.setText(self.t("btn_ping_icmp"))
        self.btn_ping_tcp.setText(self.t("btn_ping_tcp"))
        self.lbl_ping_log_desc.setText(self.t("lbl_ping_log"))

        # 动态状态与文本
        self.on_mode_change()
        self.update_member_ui()
        self.update_control_permission()

        if not self.video_path:
            self.lbl_my_video_meta.setText(self.t("lbl_my_video_prefix") + self.t("lbl_my_video_none"))
        else:
            file_name = os.path.basename(self.video_path)
            self.lbl_my_video_meta.setText(f"{self.t('lbl_my_video_prefix')}{file_name} | {self.video_size_str} | {self.video_dur_str}")

        if not self.player or not self.player.is_alive():
            self.btn_launch_player.setText(self.t("btn_launch_player"))
        else:
            self.btn_launch_player.setText(self.t("btn_relaunch_player"))

    # --- 拖拽与文件加载 ---
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
            self, "Select Video", "", "Video (*.mp4 *.mkv *.avi *.flv *.ts *.mov *.m4v *.webm)"
        )
        if f: self.load_video_file(f)

    def load_video_file(self, f):
        self.video_path = f
        file_name = os.path.basename(f)
        file_size = os.path.getsize(f)
        self.video_size_str = format_size(file_size)

        fast_dur = get_video_duration_fast(f)
        self.video_dur_str = format_time(fast_dur) if fast_dur > 0 else "--"

        self.lbl_my_video_meta.setText(
            f"{self.t('lbl_my_video_prefix')}{file_name} | {self.video_size_str} | {self.video_dur_str}"
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
            f"{self.t('lbl_host_video_prefix')}《{self.host_video_data['name']}》 | {self.host_video_data['size']} | {self.host_video_data['duration']}"
        )

    def broadcast_host_video_meta(self):
        if self.rb_server.isChecked() and self.network.is_connected():
            my_name = self.txt_my_name.text().strip() or "Host"
            self.network.send_cmd("video_meta_sync", sender=my_name, extra=self.host_video_data)

    def update_control_permission(self):
        is_host = self.rb_server.isChecked()
        for btn in [self.btn_toggle_play, self.btn_sync_seek, self.btn_back_10, 
                    self.btn_back_5, self.btn_fwd_5, self.btn_fwd_10]:
            btn.setEnabled(is_host)

        if is_host:
            self.lbl_role_hint.setText(self.t("role_hint_host"))
            self.lbl_role_hint.setStyleSheet("color: #2e7d32; font-weight: bold;")
        else:
            self.lbl_role_hint.setText(self.t("role_hint_client"))
            self.lbl_role_hint.setStyleSheet("color: #d32f2f; font-weight: bold;")

    def update_member_ui(self):
        my_name = self.txt_my_name.text().strip() or "Anonymous"
        self.list_members.clear()

        if self.rb_server.isChecked():
            self.list_members.addItem(QListWidgetItem(self.t("role_tag_host_me").format(name=my_name)))
            if self.peer_name:
                self.list_members.addItem(QListWidgetItem(self.t("role_tag_guest").format(name=self.peer_name)))
        else:
            if self.peer_name:
                self.list_members.addItem(QListWidgetItem(self.t("role_tag_host").format(name=self.peer_name)))
            self.list_members.addItem(QListWidgetItem(self.t("role_tag_guest_me").format(name=my_name)))

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
                QMessageBox.critical(self, "Error", "mpv.exe not found! Please configure in Tab 1.")
                return
            self.player = MPVController()
        else:
            exe_path = self.txt_vlc_path.text().strip()
            if not os.path.isfile(exe_path):
                QMessageBox.critical(self, "Error", "vlc.exe not found! Please configure in Tab 1.")
                return
            self.player = VLCController()

        self.btn_launch_player.setEnabled(False)
        self.btn_launch_player.setText("⏳ Launching...")

        def run_thread():
            ok, msg = self.player.launch_and_connect(exe_path, self.video_path)
            self.launch_signals.launched_signal.emit(ok, msg)

        threading.Thread(target=run_thread, daemon=True).start()

    def on_player_launched_result(self, ok, msg):
        if ok:
            p_name = self.player_type.upper()
            self.log(f"【OK】{p_name} connected and ready.")
            self.btn_launch_player.setText(self.t("btn_relaunch_player"))
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
                    f"{self.t('lbl_my_video_prefix')}{file_name} | {self.video_size_str} | {self.video_dur_str}"
                )
                if self.rb_server.isChecked():
                    self.host_video_data["duration"] = self.video_dur_str
                    self.update_host_video_banner()
                    self.broadcast_host_video_meta()
        else:
            self.log(f"【Failed】{msg}")
            self.btn_launch_player.setEnabled(True)
            self.btn_launch_player.setText(self.t("btn_launch_player"))

    def monitor_timer_tick(self):
        if self.player and not self.player.is_alive():
            self.player.close()
            self.player = None
            self.btn_launch_player.setEnabled(True)
            self.btn_launch_player.setText(self.t("btn_launch_player"))
            self.log("⚠️ Player closed. Click button to restart.")
            return

        if not self.rb_server.isChecked() or not self.network.is_connected() or not self.player or self.suppress_local_detect:
            return

        curr_playing = self.player.is_playing()
        curr_time = self.player.get_time()
        my_name = self.txt_my_name.text().strip() or "Host"

        if curr_playing != self.last_player_playing:
            self.last_player_playing = curr_playing
            target_state = "playing" if curr_playing else "paused"
            state_str = "Play" if curr_playing else "Pause"
            self.network.send_cmd("host_sync", curr_time, sender=my_name, extra={"state": target_state})
            self.log(f"[{my_name}] {state_str} ({curr_time}s)")

        elif abs(curr_time - self.last_player_time) > 3 and curr_time > 0:
            target_state = "playing" if self.last_player_playing else "paused"
            self.network.send_cmd("host_sync", curr_time, sender=my_name, extra={"state": target_state})
            self.log(f"[{my_name}] Seek -> {curr_time}s")
            self.last_player_time = curr_time

    # --- 房主操作逻辑 ---
    def host_action_toggle_play(self):
        if not self.rb_server.isChecked() or not self.player: return
        self.suppress_local_detect = True
        
        was_playing = self.player.is_playing()
        target_state = "paused" if was_playing else "playing"
        state_str = "Pause" if was_playing else "Play"

        if target_state == "paused":
            self.player.ensure_pause()
        else:
            self.player.ensure_play()

        self.last_player_playing = (target_state == "playing")
        t = self.player.get_time()

        my_name = self.txt_my_name.text().strip() or "Host"
        self.network.send_cmd("host_sync", t, sender=my_name, extra={"state": target_state})
        self.log(f"[{my_name}] {state_str} ({t}s)")
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

        my_name = self.txt_my_name.text().strip() or "Host"
        self.network.send_cmd("host_sync", target_t, sender=my_name, extra={"state": target_state})
        self.log(f"[{my_name}] Seek ({delta:+}s) -> {target_t}s")
        QTimer.singleShot(500, lambda: setattr(self, 'suppress_local_detect', False))

    def host_action_force_sync(self):
        if not self.rb_server.isChecked() or not self.player: return
        t = self.player.get_time()
        is_playing = self.player.is_playing()
        target_state = "playing" if is_playing else "paused"

        my_name = self.txt_my_name.text().strip() or "Host"
        self.network.send_cmd("host_sync", t, sender=my_name, extra={"state": target_state})
        self.log(f"[{my_name}] Force Synced -> {t}s")

    def host_broadcast_tick(self):
        if not self.rb_server.isChecked() or not self.network.is_connected() or not self.player:
            return
        t = self.player.get_time()
        is_playing = self.player.is_playing()
        state_str = "playing" if is_playing else "paused"
        my_name = self.txt_my_name.text().strip() or "Host"
        self.network.send_cmd("host_sync", t, sender=my_name, extra={"state": state_str})

    # --- 观众端响应核心 ---
    def on_net_received(self, msg):
        act = msg.get("action")
        t = msg.get("time", 0)
        sender = msg.get("sender", "Host")

        if act == "handshake":
            self.peer_name = sender
            self.update_member_ui()
            self.log(f"🎉 [{sender}] joined the room.")
            if self.rb_server.isChecked():
                my_name = self.txt_my_name.text().strip() or "Host"
                self.network.send_cmd("handshake_reply", sender=my_name, extra=self.host_video_data)

        elif act == "handshake_reply":
            self.peer_name = sender
            self.update_member_ui()
            self.log(f"🎉 Connected to Host [{sender}]!")
            self.host_video_data["name"] = msg.get("name", "--")
            self.host_video_data["size"] = msg.get("size", "--")
            self.host_video_data["duration"] = msg.get("duration", "--")
            self.update_host_video_banner()

        elif act == "video_meta_sync":
            self.host_video_data["name"] = msg.get("name", "--")
            self.host_video_data["size"] = msg.get("size", "--")
            self.host_video_data["duration"] = msg.get("duration", "--")
            self.update_host_video_banner()
            self.log(f"📢 Host changed video: 《{self.host_video_data['name']}》")

        elif act == "chat":
            chat_text = msg.get('msg', '')
            self.log(f"💬 [{sender}]: {chat_text}")
            if self.player:
                self.player.show_osd(f"💬 {sender}: {chat_text}")

        elif act == "room_disbanded":
            self.log("🚪 Room disbanded by host.")
            QMessageBox.information(self, "Notice", "Host disbanded the room.")
            self.on_disconnected_ok()

        elif act == "member_left":
            self.log(f"👤 [{sender}] left.")
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
        if p: self.txt_mpv_path.setText(p)

    def trigger_auto_detect_vlc(self):
        p = auto_detect_vlc()
        if p: self.txt_vlc_path.setText(p)

    def browse_mpv_path(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select mpv", "", "mpv (mpv.exe mpv);;All (*.*)")
        if f: self.txt_mpv_path.setText(f)

    def browse_vlc_path(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select VLC", "", "VLC (vlc.exe vlc);;All (*.*)")
        if f: self.txt_vlc_path.setText(f)

    def on_mode_change(self):
        if self.rb_server.isChecked():
            self.lbl_ip_desc.setText(self.t("lbl_listen_ip"))
            self.txt_ip.setText("0.0.0.0")
            self.btn_connect.setText(self.t("btn_start_server"))
            self.btn_disconnect.setText(self.t("btn_disband"))
            if self.video_path:
                self.host_video_data["name"] = os.path.basename(self.video_path)
                self.host_video_data["size"] = self.video_size_str
                self.host_video_data["duration"] = self.video_dur_str
                self.update_host_video_banner()
        else:
            self.lbl_ip_desc.setText(self.t("lbl_host_ip"))
            self.txt_ip.clear()
            self.txt_ip.setPlaceholderText(self.t("host_ip_placeholder"))
            self.btn_connect.setText(self.t("btn_join_room"))
            self.btn_disconnect.setText(self.t("btn_leave"))
            self.lbl_host_video_meta.setText(f"{self.t('lbl_host_video_prefix')}({self.t('lbl_host_video_wait')})")

        self.update_control_permission()
        self.update_member_ui()

    def connect_network(self):
        my_name = self.txt_my_name.text().strip()
        if not my_name:
            QMessageBox.warning(self, "Notice", "Please enter nickname first!")
            self.txt_my_name.setFocus()
            return

        port = int(self.txt_port.text().strip())
        ip = self.txt_ip.text().strip()
        self.txt_my_name.setEnabled(False)

        if self.rb_server.isChecked():
            bind_ip = ip if ip else "0.0.0.0"
            self.network.start_server(bind_ip, port)
            self.log(f"Server started on {bind_ip}:{port}. Waiting for peers...")
        else:
            if not ip:
                QMessageBox.warning(self, "Notice", "Please enter host IP!")
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
        my_name = self.txt_my_name.text().strip() or "Me"
        if self.rb_server.isChecked():
            self.network.send_cmd("room_disbanded", sender=my_name)
            self.log("[Network] Room disbanded.")
        else:
            self.network.send_cmd("member_left", sender=my_name)
            self.log("[Network] Left room.")

        self.network.close()
        self.on_disconnected_ok()

    def on_connected_ok(self, addr):
        my_name = self.txt_my_name.text().strip()
        self.network.send_cmd("handshake", sender=my_name)

        if self.rb_server.isChecked():
            self.host_sync_timer.start()
            self.broadcast_host_video_meta()

    def on_disconnected_ok(self):
        self.log("[Network] Disconnected.")
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
        my_name = self.txt_my_name.text().strip() or "Me"
        if not self.network.is_connected():
            return

        self.network.send_cmd("chat", sender=my_name, extra={"msg": text})
        self.log(f"💬 [{my_name}]: {text}")
        
        if self.player:
            self.player.show_osd(f"💬 {my_name}: {text}")

        self.txt_chat_input.clear()

    # --- QSettings ---
    def load_saved_settings(self):
        saved_lang = self.settings.value("lang", "zh")
        self.current_lang = saved_lang

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

        self.retranslate_ui()

    def save_current_settings(self):
        self.settings.setValue("lang", self.current_lang)
        self.settings.setValue("my_name", self.txt_my_name.text().strip())
        if self.rb_client.isChecked():
            self.settings.setValue("last_ip", self.txt_ip.text().strip())
        self.settings.setValue("is_client", "true" if self.rb_client.isChecked() else "false")
        self.settings.setValue("player_idx", self.combo_player.currentIndex())
        self.settings.setValue("mpv_path", self.txt_mpv_path.text().strip())
        self.settings.setValue("vlc_path", self.txt_vlc_path.text().strip())

    # --- Ping ---
    def append_ping_log(self, text):
        self.txt_ping_log.append(f"[{time.strftime('%H:%M:%S')}] {text}")

    def on_ping_finished(self):
        self.btn_ping_icmp.setEnabled(True)
        self.btn_ping_tcp.setEnabled(True)

    def start_icmp_ping(self):
        ip = self.txt_ping_ip.text().strip()
        if not ip: return
        self.btn_ping_icmp.setEnabled(False)
        self.btn_ping_tcp.setEnabled(False)
        self.append_ping_log(f"Ping {ip}...")
        threading.Thread(target=run_icmp_ping, args=(ip, self.ping_signals), daemon=True).start()

    def start_tcp_ping(self):
        ip = self.txt_ping_ip.text().strip()
        try:
            port = int(self.txt_ping_port.text().strip())
        except ValueError:
            return
        if not ip: return

        self.btn_ping_icmp.setEnabled(False)
        self.btn_ping_tcp.setEnabled(False)
        self.append_ping_log(f"Probe {ip}:{port}...")
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