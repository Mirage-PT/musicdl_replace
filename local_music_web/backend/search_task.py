# Search task: sequential search using musicdl (QQ + Netease, 3 each), sort by match, save to library
import sys
import os
import threading
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# Ensure project root is on path so we can import musicdl
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from .library import load_library, save_library
from .models import (
    LibraryData,
    SongEntry,
    SearchResultBySource,
    SearchResultItem,
    SearchTaskState,
)


def _song_info_to_item(si: "SongInfo") -> SearchResultItem:
    return SearchResultItem(
        song_name=si.song_name or "",
        singers=si.singers or "",
        album=si.album or "",
        duration=si.duration or "",
        file_size=si.file_size or "",
        ext=(si.ext or "mp3").lstrip("."),
        download_url=getattr(si, "download_url", None),
        raw=si.todict() if hasattr(si, "todict") else {},
    )


def _sort_search_results(items: list, keyword: str, singers: str) -> list:
    """Sort: exact match (song name + singer) first, then song name match."""
    kw_lower = (keyword or "").strip().lower()
    sing_lower = (singers or "").strip().lower()
    def score(item):
        name = (item.song_name or "").strip().lower()
        sing = (item.singers or "").strip().lower()
        exact = 2 if name == kw_lower and sing == sing_lower else 0
        name_ok = 1 if kw_lower in name or name in kw_lower else 0
        return (-exact, -name_ok, name)
    return sorted(items, key=score)


# Global task state for one running search
_search_lock = threading.Lock()
_search_library_id: Optional[str] = None
_search_paused = threading.Event()  # set = paused, clear = running
_search_stop = threading.Event()    # set = stop requested


def _run_search_worker(library_id: str) -> None:
    global _search_library_id
    from musicdl import musicdl
    from musicdl.modules.utils.data import SongInfo

    lib = load_library(library_id)
    if not lib or lib.search_task.status != "running":
        with _search_lock:
            _search_library_id = None
        return

    songs = lib.songs
    total = len(songs)

    # 构建需要搜索的索引列表（跳过已搜索/已选择/已下载）
    pending_indices = [
        i for i, e in enumerate(songs)
        if e.status not in ("searched", "selected", "downloaded")
    ]
    if not pending_indices:
        lib.search_task.status = "idle"
        lib.search_task.current_index = total
        save_library(lib)
        with _search_lock:
            if _search_library_id == library_id:
                _search_library_id = None
        return

    # 用 current_index 记录已完成的数量，而不是当前下标，便于多线程
    lib.search_task.current_index = total - len(pending_indices)
    save_library(lib)

    io_lock = threading.Lock()

    def process_index(idx: int) -> None:
        nonlocal lib
        from musicdl import musicdl as _musicdl_local

        # 每个 worker 自己持有一个 MusicClient，避免并发共享实例
        client = _musicdl_local.MusicClient(
            music_sources=["QQMusicClient", "NeteaseMusicClient"],
            init_music_clients_cfg={
                "QQMusicClient": {"search_size_per_source": 3, "work_dir": lib.folder_path, "disable_print": True},
                "NeteaseMusicClient": {"search_size_per_source": 3, "work_dir": lib.folder_path, "disable_print": True},
            },
        )

        while _search_paused.is_set() and not _search_stop.is_set():
            import time
            time.sleep(0.3)
        if _search_stop.is_set():
            return

        with io_lock:
            # 可能在等待期间状态已被更新
            if idx >= len(lib.songs):
                return
            entry = lib.songs[idx]
            if entry.status in ("searched", "selected", "downloaded"):
                lib.search_task.current_index += 1
                save_library(lib)
                return
            name_part = (entry.song_name or entry.file_name or "").strip()
            singer_part = (entry.singers or "").strip()

        keyword = f"{name_part} {singer_part}".strip() if singer_part else name_part
        if not keyword:
            with io_lock:
                entry = lib.songs[idx]
                entry.status = "searched"
                entry.search_result = []
                lib.search_task.current_index += 1
                save_library(lib)
            return

        try:
            raw_results = client.search(keyword=keyword)
        except Exception as e:
            with io_lock:
                entry = lib.songs[idx]
                entry.status = "error"
                entry.error_message = str(e)
                lib.search_task.current_index += 1
                save_library(lib)
            return

        qq_list = raw_results.get("QQMusicClient") or []
        netease_list = raw_results.get("NeteaseMusicClient") or []
        qq_items = [_song_info_to_item(si) for si in (qq_list[:3] if isinstance(qq_list, list) else [])]
        netease_items = [_song_info_to_item(si) for si in (netease_list[:3] if isinstance(netease_list, list) else [])]
        # Ensure we have SongInfo for conversion
        for i, si in enumerate(qq_list[:3] if isinstance(qq_list, list) else []):
            if i < len(qq_items) and hasattr(si, "todict"):
                qq_items[i].raw = si.todict()
        for i, si in enumerate(netease_list[:3] if isinstance(netease_list, list) else []):
            if i < len(netease_items) and hasattr(si, "todict"):
                netease_items[i].raw = si.todict()
        qq_items_sorted = _sort_search_results(qq_items, keyword, singer_part)
        netease_items_sorted = _sort_search_results(netease_items, keyword, singer_part)

        with io_lock:
            # 重新取 entry 防止中途被替换
            if idx >= len(lib.songs):
                return
            entry = lib.songs[idx]
            entry.search_result = [
                SearchResultBySource(source="qq", items=qq_items_sorted),
                SearchResultBySource(source="netease", items=netease_items_sorted),
            ]
            # 若用户在搜索过程中已经为该歌曲选择了最佳结果，则保持 selected 状态
            if entry.best_choice is not None:
                entry.status = "selected"
            else:
                entry.status = "searched"
            entry.error_message = None
            lib.search_task.current_index += 1
            save_library(lib)

    max_workers = min(4, len(pending_indices))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_index, i) for i in pending_indices]
        for _ in as_completed(futures):
            if _search_stop.is_set():
                break

    lib = load_library(library_id)
    if lib:
        lib.search_task.status = "idle"
        save_library(lib)
    with _search_lock:
        if _search_library_id == library_id:
            _search_library_id = None


def search_control(library_id: str, action: str) -> dict:
    """Start / pause / continue search. Returns updated task state."""
    global _search_library_id
    lib = load_library(library_id)
    if not lib:
        return {"ok": False, "error": "library not found"}
    if action == "start":
        with _search_lock:
            if _search_library_id and _search_library_id != library_id:
                return {"ok": False, "error": "another search is running"}
            _search_library_id = library_id
            _search_paused.clear()
            _search_stop.clear()
        lib.search_task.status = "running"
        lib.search_task.current_index = 0
        save_library(lib)
        t = threading.Thread(target=_run_search_worker, args=(library_id,), daemon=True)
        t.start()
        return {"ok": True, "search_task": lib.search_task.model_dump()}
    if action == "pause":
        _search_paused.set()
        lib.search_task.status = "paused"
        save_library(lib)
        return {"ok": True, "search_task": lib.search_task.model_dump()}
    if action == "continue":
        with _search_lock:
            if _search_library_id and _search_library_id != library_id:
                return {"ok": False, "error": "another search is running"}
            if _search_library_id != library_id:
                _search_library_id = library_id
                _search_paused.clear()
                _search_stop.clear()
                lib.search_task.status = "running"
                save_library(lib)
                t = threading.Thread(target=_run_search_worker, args=(library_id,), daemon=True)
                t.start()
            else:
                _search_paused.clear()
        lib2 = load_library(library_id)
        if lib2:
            lib2.search_task.status = "running"
            save_library(lib2)
        return {"ok": True, "search_task": load_library(library_id).search_task.model_dump()}
    if action == "stop":
        _search_stop.set()
        lib = load_library(library_id)
        if lib:
            lib.search_task.status = "idle"
            save_library(lib)
        lib = load_library(library_id)
        return {"ok": True, "search_task": lib.search_task.model_dump() if lib else None}
    return {"ok": False, "error": "invalid action"}


def is_search_running_for(library_id: str) -> bool:
    """是否正有搜索任务在该库上运行（用于纠正重启后库文件里仍为 running 的脏状态）"""
    return _search_library_id == library_id


def get_search_status(library_id: str) -> Optional[dict]:
    lib = load_library(library_id)
    if not lib:
        return None
    return lib.search_task.model_dump()
