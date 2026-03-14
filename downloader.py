import os
import uuid
import yt_dlp
from config import DOWNLOAD_DIR

def ensure_download_dir():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def format_speed(speed_bps: float) -> str:
    if speed_bps is None:
        return "—"
    if speed_bps >= 1024 * 1024:
        return f"{speed_bps / (1024 * 1024):.1f} MB/s"
    if speed_bps >= 1024:
        return f"{speed_bps / 1024:.1f} KB/s"
    return f"{speed_bps:.0f} B/s"

def format_size(size_bytes: float) -> str:
    if size_bytes is None:
        return "—"
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 ** 3):.2f} GB"
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 ** 2):.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes:.0f} B"

def format_eta(eta_sec) -> str:
    if eta_sec is None:
        return "—"
    eta_sec = int(eta_sec)
    h = eta_sec // 3600
    m = (eta_sec % 3600) // 60
    s = eta_sec % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

def build_progress_bar(percent: float, width: int = 16) -> str:
    filled = int(width * percent / 100)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {percent:.1f}%"

def make_progress_hook(on_progress):
    def hook(d: dict):
        if d["status"] == "downloading":
            downloaded = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            speed = d.get("speed")
            eta = d.get("eta")
            percent = (downloaded / total * 100) if total else 0
            on_progress(
                percent=percent,
                downloaded=downloaded,
                total=total,
                speed=speed,
                eta=eta,
            )
    return hook

def download_video(url: str, progress_hook=None) -> str | None:
    ensure_download_dir()
    uid = uuid.uuid4().hex[:8]
    output_template = os.path.join(DOWNLOAD_DIR, f"%(title)s_{uid}.%(ext)s")

    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "restrictfilenames": True,
        "nooverwrites": False,
    }

    if progress_hook:
        ydl_opts["progress_hooks"] = [progress_hook]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if not filename.endswith(".mp4"):
                base = os.path.splitext(filename)[0]
                filename = base + ".mp4"
            return filename if os.path.exists(filename) else None
    except Exception:
        return None

def download_audio(url: str, progress_hook=None) -> str | None:
    ensure_download_dir()
    uid = uuid.uuid4().hex[:8]
    output_template = os.path.join(DOWNLOAD_DIR, f"%(title)s_{uid}.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "restrictfilenames": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }

    if progress_hook:
        ydl_opts["progress_hooks"] = [progress_hook]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            base = os.path.splitext(filename)[0]
            final_filename = base + ".mp3"
            return final_filename if os.path.exists(final_filename) else None
    except Exception:
        return None
