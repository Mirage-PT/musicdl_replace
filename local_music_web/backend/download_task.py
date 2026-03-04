# Download task: sequential download, overwrite original file with 歌名-歌手.ext
import sys
import os
import threading
from datetime import datetime
from typing import Optional
import urllib.request
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

from pathvalidate import sanitize_filename

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from .library import load_library, save_library
from .models import LibraryData, SongEntry, DownloadTaskState

_download_lock = threading.Lock()
_download_library_id: Optional[str] = None
_download_paused = threading.Event()
_download_stop = threading.Event()

# All downloaded files will be stored under this project's "downloads" directory
_DOWNLOAD_DIR = os.path.join(_PROJECT_ROOT, "downloads")
os.makedirs(_DOWNLOAD_DIR, exist_ok=True)


def _target_path(entry: SongEntry, song_name: str, singers: str, ext: str) -> str:
    """Target file path: project downloads dir, name = 歌名-歌手.ext"""
    safe_name = sanitize_filename(f"{song_name}-{singers}.{ext}", replacement_text="_")
    return os.path.join(_DOWNLOAD_DIR, safe_name)


def _netease_suffix(url: str) -> str:
    """Extract stable suffix part from Netease url for matching refreshed links.

    关键稳定部分其实是 /obj/.../xxx.flac，所以优先从 /obj/ 开始截取；
    若没有 /obj/ 再回退到 /jdymusic/ 或 /ymusic/。
    """
    try:
        p = urlparse(str(url))
        path = p.path or ""
        # 优先从 /obj/ 开始（最稳定）
        obj_idx = path.find("/obj/")
        if obj_idx >= 0:
            return path[obj_idx:]
        # 回退到 /jdymusic/ 或 /ymusic/
        for marker in ("/jdymusic/", "/ymusic/"):
            idx = path.find(marker)
            if idx >= 0:
                return path[idx:]
        return path
    except Exception:
        return str(url)


def _mark_entry_error(library_id: str, entry_id: str, message: str) -> None:
    """在库文件中将指定歌曲标记为 error，并推进已完成计数。"""
    with _download_lock:
        lib = load_library(library_id)
        if not lib:
            return
        for e in lib.songs:
            if e.id == entry_id:
                e.status = "error"
                e.error_message = message
                break
        lib.download_task.completed_count += 1
        lib.download_task.current_index = lib.download_task.completed_count
        save_library(lib)


def _run_download_worker(library_id: str) -> None:
    """Background worker: download all songs with best_choice into project downloads dir."""
    global _download_library_id

    lib = load_library(library_id)
    if not lib or lib.download_task.status != "running":
        with _download_lock:
            _download_library_id = None
        return

    # Build list of songs that have best_choice and are not yet downloaded
    to_download: list[tuple[int, SongEntry]] = []
    for i, entry in enumerate(lib.songs):
        if entry.status == "downloaded" or entry.downloaded_at:
            continue
        if not entry.best_choice or not entry.best_choice.raw:
            continue
        to_download.append((i, entry))

    if not to_download:
        with _download_lock:
            lib = load_library(library_id)
            if lib:
                lib.download_task.status = "idle"
                lib.download_task.current_song_name = None
                save_library(lib)
            _download_library_id = None
        return

    def _process_one(idx: int, entry: SongEntry) -> None:
        # 停止 / 暂停控制
        if _download_stop.is_set():
            return
        while _download_paused.is_set() and not _download_stop.is_set():
            import time
            time.sleep(0.3)
        if _download_stop.is_set():
            return

        raw = entry.best_choice.raw or {}
        # 取基础信息
        song_name = (raw.get("song_name") or entry.song_name or "unknown").strip()
        singers = (raw.get("singers") or entry.singers or "").strip()
        ext = (str(raw.get("ext") or "mp3")).strip().lstrip(".")
        url = raw.get("download_url") or raw.get("final_url")
        if not url or not str(url).startswith("http"):
            _mark_entry_error(library_id, entry.id, "download url missing")
            return

        target = _target_path(entry, song_name, singers, ext)
        os.makedirs(os.path.dirname(target), exist_ok=True)

        # 更新“正在下载”显示
        with _download_lock:
            lib_local = load_library(library_id)
            if lib_local:
                lib_local.download_task.current_song_name = f"{song_name} - {singers}"
                save_library(lib_local)

        # 实际下载（若失败且为网易云，则尝试自动刷新链接再重试一次）
        def _download_once(d_url: str) -> None:
            headers = {"User-Agent": "Mozilla/5.0 (compatible; LocalMusic/1.0)"}
            req = urllib.request.Request(str(d_url), headers=headers)
            with urllib.request.urlopen(req, timeout=60) as resp, open(target, "wb") as fp:
                while True:
                    chunk = resp.read(1024 * 64)
                    if not chunk:
                        break
                    fp.write(chunk)

        try:
            _download_once(url)
        except Exception as first_err:
            # 仅对网易云尝试自动刷新一次
            if entry.best_choice.source == "netease":
                try:
                    from musicdl import musicdl  # 局部导入，避免无关环境报错
                    from musicdl.modules.utils.data import SongInfo  # noqa: F401 (type hint)

                    orig_suffix = _netease_suffix(url)
                    keyword = f"{entry.song_name or entry.file_name or ''} {entry.singers or ''}".strip() or (entry.song_name or entry.file_name or "")
                    mc = musicdl.MusicClient(
                        music_sources=["NeteaseMusicClient"],
                        init_music_clients_cfg={
                            "NeteaseMusicClient": {"work_dir": _DOWNLOAD_DIR},
                        },
                    )
                    search_results = mc.search(keyword=keyword)
                    cand_list = search_results.get("NeteaseMusicClient") or []
                    refreshed_url = None
                    candidate_urls: list[str] = []
                    for si in cand_list:
                        new_url = getattr(si, "download_url", None)
                        if not new_url:
                            continue
                        candidate_urls.append(str(new_url))
                        if _netease_suffix(new_url) == orig_suffix:
                            refreshed_url = new_url
                            break
                    if refreshed_url:
                        try:
                            _download_once(refreshed_url)
                            # 成功后，更新 raw 里的 download_url，方便下次直接用新的
                            entry.best_choice.raw["download_url"] = str(refreshed_url)
                            with _download_lock:
                                lib2 = load_library(library_id)
                                if lib2:
                                    save_library(lib2)
                        except Exception as second_err:
                            _mark_entry_error(
                                library_id,
                                entry.id,
                                f"download failed after refresh: {second_err}",
                            )
                            return
                    else:
                        # 没有找到尾缀匹配的网易云链接，详细记录候选 URL 便于排查
                        joined = "; ".join(candidate_urls[:5])
                        more = " (and more)" if len(candidate_urls) > 5 else ""
                        msg = (
                            "download failed and no refreshed Netease link matched suffix "
                            f"{orig_suffix}; original={url}; candidates={joined}{more}"
                        )
                        _mark_entry_error(library_id, entry.id, msg)
                        return
                except Exception as refresh_err:
                    _mark_entry_error(
                        library_id,
                        entry.id,
                        f"download failed and refresh error: {refresh_err}",
                    )
                    return
            else:
                _mark_entry_error(library_id, entry.id, f"download failed: {first_err}")
                return

        if not os.path.exists(target):
            _mark_entry_error(library_id, entry.id, "download did not produce file")
            return

        # Update entry & progress
        with _download_lock:
            lib_local = load_library(library_id)
            if not lib_local:
                return
            for e in lib_local.songs:
                if e.id == entry.id:
                    e.file_path = target
                    e.file_name = os.path.basename(target)
                    e.song_name = song_name
                    e.singers = singers
                    e.status = "downloaded"
                    e.downloaded_at = datetime.utcnow().isoformat() + "Z"
                    e.error_message = None
                    break
            lib_local.download_task.completed_count += 1
            lib_local.download_task.current_index = lib_local.download_task.completed_count
            save_library(lib_local)

    max_workers = min(3, len(to_download))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_process_one, idx, entry) for idx, entry in to_download]
        for _ in as_completed(futures):
            if _download_stop.is_set():
                break

    lib = load_library(library_id)
    if lib:
        lib.download_task.status = "idle"
        lib.download_task.current_song_name = None
        save_library(lib)
    with _download_lock:
        if _download_library_id == library_id:
            _download_library_id = None


def download_control(library_id: str, action: str) -> dict:
    global _download_library_id
    lib = load_library(library_id)
    if not lib:
        return {"ok": False, "error": "library not found"}
    if action == "start" or action == "continue":
        with _download_lock:
            if _download_library_id and _download_library_id != library_id:
                return {"ok": False, "error": "another download is running"}
            _download_library_id = library_id
            _download_paused.clear()
            _download_stop.clear()
        # total = count of songs with best_choice not yet downloaded
        total = sum(1 for s in lib.songs if s.best_choice and s.best_choice.raw and not s.downloaded_at)
        if total == 0:
            # No tasks to download; do not start worker
            return {"ok": False, "error": "没有可下载的最佳匹配，请先为歌曲选择最佳结果"}
        lib.download_task.status = "running"
        lib.download_task.total = total
        lib.download_task.completed_count = 0
        lib.download_task.current_index = 0
        save_library(lib)
        t = threading.Thread(target=_run_download_worker, args=(library_id,), daemon=True)
        t.start()
        return {"ok": True, "download_task": lib.download_task.model_dump()}
    if action == "pause":
        _download_paused.set()
        return {"ok": True, "download_task": lib.download_task.model_dump()}
    return {"ok": False, "error": "invalid action"}


def is_download_running_for(library_id: str) -> bool:
    """是否正有下载任务在该库上运行（用于纠正重启后库文件里仍为 running 的脏状态）"""
    return _download_library_id == library_id


def get_download_status(library_id: str) -> Optional[dict]:
    lib = load_library(library_id)
    if not lib:
        return None
    return lib.download_task.model_dump()
