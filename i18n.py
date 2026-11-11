# 中英文语言对照包 (i18n)

LANGUAGES = {
    "zh": {
        # 窗口与选项卡
        "window_title": "LAN Syncplay (局域网同步播放) - byzh",
        "tab_path": "1. 📁 路径设置",
        "tab_room": "2. 🌐 房间设置",
        "tab_sync": "3. 🔄 同步与控制",
        "tab_ping": "4. 🛠️ 功能-Ping",

        # 菜单
        "menu_language": "语言 (Language)",

        # 栏目 1: 路径设置
        "grp_mpv": "mpv 播放器路径 (推荐 ⭐⭐⭐⭐⭐)",
        "mpv_desc": "mpv 原生支持 JSON-IPC，精准对齐、零延迟、无任何状态误判问题。",
        "mpv_placeholder": "自动检测或手动选择 mpv.exe",
        "grp_vlc": "VLC 播放器路径 (备选)",
        "vlc_desc": "传统 VLC 播放器（基于命令行控制协议）。",
        "vlc_placeholder": "自动检测或手动选择 vlc.exe",
        "btn_auto_find": "自动查找",
        "btn_browse": "浏览...",

        # 栏目 2: 房间设置
        "lbl_nickname": "我的昵称:",
        "nickname_placeholder": "请输入您的昵称（必填）",
        "grp_role": "身份设定",
        "rb_host": "做房主 (掌控播放主权)",
        "rb_client": "加入好友 (观众模式，跟随房主)",
        "grp_net": "连接配置",
        "lbl_listen_ip": "监听 IP:",
        "lbl_host_ip": "房主 IP:",
        "host_ip_placeholder": "房主 IP 地址 (如 192.168.x.x / 10.x.x.x / 172.x.x.x)",
        "lbl_port": "端口:",
        "btn_start_server": "开启房间服务",
        "btn_join_room": "加入好友房间",
        "btn_disband": "🚪 解散房间",
        "btn_leave": "🚪 退出房间",
        "grp_members": "房间成员列表",

        # 栏目 3: 同步与控制
        "grp_video": "视频载入与播放器启动 (可直接将视频文件拖入窗口)",
        "lbl_host_video_prefix": "👑 房主视频：",
        "lbl_host_video_wait": "等待房主载入...",
        "lbl_my_video_prefix": "我的视频：",
        "lbl_my_video_none": "未选择 (支持直接拖拽文件进窗口)",
        "btn_select_video": "选择本地视频",
        "lbl_select_player": "选择播放器:",
        "btn_launch_player": "🚀 启动播放器 (就绪暂停)",
        "btn_relaunch_player": "🔄 重启播放器",
        "grp_console": "控制台",
        "role_hint_host": "👑 当前为【房主模式】：您的播放、暂停、快进快退将直接主导全员进度。",
        "role_hint_client": "🔒 当前为【观众模式】：进度完全跟随房主。",
        "btn_play_pause": "⏯ 同步 播放 / 暂停",
        "btn_force_sync": "🔄 强制所有人对齐到我",
        "lbl_log_title": "实时同步与聊天日志 (全屏观影时，聊天将直接飘在视频画面上方):",
        "chat_placeholder": "在此输入聊天内容，回车发送（文字将直接飘在双方视频屏幕上）...",
        "btn_send": "发送",

        # 栏目 4: Ping 诊断
        "grp_ping": "虚拟局域网连通性检测 (局域网 / VLAN)",
        "lbl_target_ip": "目标 IP:",
        "target_ip_placeholder": "输入对方虚拟局域网 IP (如 192.168.x.x / 10.x.x.x / 172.x.x.x)",
        "lbl_target_port": "目标端口:",
        "btn_ping_icmp": "📡 系统 ICMP Ping (测试网络通不通)",
        "btn_ping_tcp": "🔌 TCP 端口直连探测 (测试 8899 能否连上)",
        "lbl_ping_log": "Ping 诊断输出:",

        # 成员标识
        "role_tag_host_me": "👑 {name} (房主/我)",
        "role_tag_host": "👑 {name} (房主)",
        "role_tag_guest_me": "👤 {name} (我/观众)",
        "role_tag_guest": "👤 {name} (观众)",
    },

    "en": {
        # Window & Tabs
        "window_title": "LAN Syncplay - byzh",
        "tab_path": "1. 📁 Path Settings",
        "tab_room": "2. 🌐 Room Settings",
        "tab_sync": "3. 🔄 Sync & Control",
        "tab_ping": "4. 🛠️ Diagnostics (Ping)",

        # Menu
        "menu_language": "Language (语言)",

        # Tab 1: Path Settings
        "grp_mpv": "mpv Player Path (Recommended ⭐⭐⭐⭐⭐)",
        "mpv_desc": "mpv natively supports JSON-IPC for precise, zero-latency sync without state glitches.",
        "mpv_placeholder": "Auto-detect or manually select mpv.exe",
        "grp_vlc": "VLC Player Path (Alternative)",
        "vlc_desc": "Classic VLC Player (Command-line RC protocol).",
        "vlc_placeholder": "Auto-detect or manually select vlc.exe",
        "btn_auto_find": "Auto Detect",
        "btn_browse": "Browse...",

        # Tab 2: Room Settings
        "lbl_nickname": "Nickname:",
        "nickname_placeholder": "Enter your nickname (Required)",
        "grp_role": "Role Setting",
        "rb_host": "Host (Full Control)",
        "rb_client": "Join Friend (Spectator, Follow Host)",
        "grp_net": "Connection Configuration",
        "lbl_listen_ip": "Listen IP:",
        "lbl_host_ip": "Host IP:",
        "host_ip_placeholder": "Host IP (e.g. 192.168.x.x / 10.x.x.x / 172.x.x.x)",
        "lbl_port": "Port:",
        "btn_start_server": "Start Room Server",
        "btn_join_room": "Join Friend's Room",
        "btn_disband": "🚪 Disband Room",
        "btn_leave": "🚪 Leave Room",
        "grp_members": "Room Members",

        # Tab 3: Sync & Control
        "grp_video": "Load Video & Launch Player (Drag & Drop Supported)",
        "lbl_host_video_prefix": "👑 Host Video: ",
        "lbl_host_video_wait": "Waiting for host to load...",
        "lbl_my_video_prefix": "My Video: ",
        "lbl_my_video_none": "None selected (Drag & drop video into window)",
        "btn_select_video": "Select Local Video",
        "lbl_select_player": "Player:",
        "btn_launch_player": "🚀 Launch Player (Ready & Paused)",
        "btn_relaunch_player": "🔄 Restart Player",
        "grp_console": "Control Console",
        "role_hint_host": "👑 [Host Mode]: Your Play, Pause, and Seek actions control everyone.",
        "role_hint_client": "🔒 [Spectator Mode]: Playback strictly follows the host.",
        "btn_play_pause": "⏯ Sync Play / Pause",
        "btn_force_sync": "🔄 Force Sync Everyone to Me",
        "lbl_log_title": "Real-time Sync & Chat Log (Messages float on video in full-screen):",
        "chat_placeholder": "Type chat message and press Enter (floats on video screen)...",
        "btn_send": "Send",

        # Tab 4: Ping Diagnostics
        "grp_ping": "Virtual LAN Connectivity Diagnostics (LAN / VLAN)",
        "lbl_target_ip": "Target IP:",
        "target_ip_placeholder": "Enter target VLAN IP (e.g. 192.168.x.x / 10.x.x.x / 172.x.x.x)",
        "lbl_target_port": "Target Port:",
        "btn_ping_icmp": "📡 System ICMP Ping (Reachability)",
        "btn_ping_tcp": "🔌 TCP Port Probe (Check port 8899)",
        "lbl_ping_log": "Diagnostics Output:",

        # Member Tags
        "role_tag_host_me": "👑 {name} (Host/Me)",
        "role_tag_host": "👑 {name} (Host)",
        "role_tag_guest_me": "👤 {name} (Me/Spectator)",
        "role_tag_guest": "👤 {name} (Spectator)",
    }
}

def tr(key, lang="zh"):
    """多语言文本查找辅助函数"""
    return LANGUAGES.get(lang, LANGUAGES["zh"]).get(key, key)