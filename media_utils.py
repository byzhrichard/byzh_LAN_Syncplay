import os
import struct

def get_mp4_duration(filepath):
    """解析 MP4 / MOV / M4V (支持头部 moov 与尾部 moov)"""
    file_size = os.path.getsize(filepath)
    with open(filepath, 'rb') as f:
        head = f.read(2 * 1024 * 1024)
        idx = head.find(b'mvhd')
        data = head[idx:] if idx != -1 else b''

        # 如果头部没有，查文件尾部 2MB
        if not data and file_size > 4 * 1024 * 1024:
            f.seek(file_size - 2 * 1024 * 1024)
            tail = f.read(2 * 1024 * 1024)
            idx = tail.find(b'mvhd')
            if idx != -1: data = tail[idx:]

        if data and len(data) >= 36:
            version = data[4]
            if version == 1:
                timescale, duration = struct.unpack('>IQ', data[24:36])
            else:
                timescale, duration = struct.unpack('>II', data[16:24])
            if timescale > 0:
                return int(duration / timescale)
    return 0

def get_mkv_duration(filepath):
    """解析 MKV / WEBM (修复 EBML 0x84/0x88 变长字节陷阱)"""
    with open(filepath, 'rb') as f:
        chunk = f.read(1024 * 1024)
        idx = chunk.find(b'\x44\x89')
        if idx != -1 and idx + 11 < len(chunk):
            len_byte = chunk[idx + 2]
            # 0x84 (132) 代表 4字节 float, 0x88 (136) 代表 8字节 double
            if len_byte in (0x84, 4):
                val = struct.unpack('>f', chunk[idx + 3:idx + 7])[0]
                return int(val / 1000) if val > 1000 else int(val)
            elif len_byte in (0x88, 8):
                val = struct.unpack('>d', chunk[idx + 3:idx + 11])[0]
                return int(val / 1000) if val > 1000 else int(val)
    return 0

def get_video_duration_fast(filepath):
    """纯 Python 毫秒级读取主流视频时长，无需开启播放器"""
    try:
        ext = os.path.splitext(filepath)[1].lower()
        if ext in ['.mp4', '.m4v', '.mov', '.ts']:
            d = get_mp4_duration(filepath)
            if d > 0: return d
        elif ext in ['.mkv', '.webm']:
            d = get_mkv_duration(filepath)
            if d > 0: return d

        # 兜底通用扫描
        d = get_mkv_duration(filepath)
        if d > 0: return d
        return get_mp4_duration(filepath)
    except Exception:
        return 0

def format_size(bytes_num):
    """文件大小转换为易读格式 (KB, MB, GB)"""
    if bytes_num <= 0: return "--"
    if bytes_num < 1024 * 1024:
        return f"{bytes_num / 1024:.1f} KB"
    elif bytes_num < 1024 * 1024 * 1024:
        return f"{bytes_num / (1024 * 1024):.1f} MB"
    else:
        return f"{bytes_num / (1024 * 1024 * 1024):.2f} GB"

def format_time(seconds):
    """秒数格式化为 HH:MM:SS 或 MM:SS"""
    if seconds <= 0: return "读取中..."
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"